"""
MF残高照合画面のテキストコピペをパースして、
通帳カタカナ摘要 → 仕訳科目 の逆引きマップ用データを構造化する。

入力: MFクラウド会計 > 取引管理 > 残高照合 の画面を全選択コピーしたテキスト
出力: JSON（取引明細のリスト + 集計）

使い方:
    # 残高照合のみ
    python3 parse_balance_match.py <input_file> [<input_file2> ...] > output.json

    # 仕訳JSONと突合（推奨）: 取引Noで突合して税区分・部門・複合仕訳構造を含める
    python3 parse_balance_match.py --journals <journals.json> <input_file> [<input_file2> ...] > output.json

各取引は通常2行で構成される:
  1行目: 取引日 / 通帳摘要 / 入金 / 出金 / 残高 / ステータス / 操作 / 取引No / 相手勘定科目
  2行目: 相手補助科目 / 摘要(MF) / 入金 / 出金 / 残高

未入力の取引は1行のみ:
  取引日 / 通帳摘要 / 入金 / 出金 / 残高 / 未入力 / 仕訳登録

複数月のデータが連続している場合、月ごとにヘッダーで区切られている。

注意: ファイル形式が想定と異なる（タブ区切りでない、列がズレている、画像など）場合は、
このスクリプトでは処理できない。Claude本体に直接読ませること。
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


YEN_RE = re.compile(r"^([\d,]+)円$")
DATE_RE = re.compile(r"^\d{4}/\d{1,2}/\d{1,2}$")


def parse_yen(s):
    if not s or s == "-円":
        return None
    m = YEN_RE.match(s.strip())
    if m:
        return int(m.group(1).replace(",", ""))
    return None


def is_date(s):
    return bool(DATE_RE.match(s.strip()))


def parse_file(path):
    """残高照合テキスト1ファイルをパース。取引のリストを返す。"""
    text = Path(path).read_text(encoding="utf-8")
    lines = text.split("\n")

    transactions = []
    i = 0
    while i < len(lines):
        line = lines[i]
        line_stripped = re.sub(r"^\d+\t", "", line)
        cols = line_stripped.split("\t")

        if cols and is_date(cols[0]):
            date = cols[0]
            tsucho_tekiyo = cols[1] if len(cols) > 1 else ""
            nyukin = parse_yen(cols[2]) if len(cols) > 2 else None
            shukkin = parse_yen(cols[3]) if len(cols) > 3 else None
            zandaka = parse_yen(cols[4]) if len(cols) > 4 else None
            status = cols[5] if len(cols) > 5 else ""
            torihiki_no = cols[7] if len(cols) > 7 else ""
            aite_kamoku = cols[8] if len(cols) > 8 else ""

            tx = {
                "date": date,
                "tsucho_tekiyo": tsucho_tekiyo.strip(),
                "nyukin": nyukin,
                "shukkin": shukkin,
                "zandaka": zandaka,
                "status": status.strip(),
                "torihiki_no": torihiki_no.strip(),
                "aite_kamoku": aite_kamoku.strip(),
                "aite_hojo": "",
                "mf_tekiyo": "",
            }

            if "入力済み" in status and i + 1 < len(lines):
                next_line = re.sub(r"^\d+\t", "", lines[i + 1])
                next_cols = next_line.split("\t")
                if next_cols and not is_date(next_cols[0]):
                    tx["aite_hojo"] = next_cols[0].strip() if len(next_cols) > 0 else ""
                    tx["mf_tekiyo"] = next_cols[1].strip() if len(next_cols) > 1 else ""
                    i += 1

            transactions.append(tx)
        i += 1

    return transactions


def normalize_katakana(s):
    """通帳カタカナから「入金」「出金」「振込入金」プレフィックスと
    日付プレフィックス（例: 2- 2、2-19 など）を除去して正規化する。"""
    s = re.sub(r"^(振込入金|入金|出金)\s*", "", s)
    s = re.sub(r"^\d+-\s*\d+\s+", "", s)
    return s.strip()


def load_journals_index(journals_path):
    """journals JSONを読み込み、number（取引No）→ 仕訳全体 の辞書を作る。"""
    data = json.loads(Path(journals_path).read_text(encoding="utf-8"))
    journals = data.get("journals", [])
    index = {}
    for j in journals:
        num = str(j.get("number", "")).strip()
        if num:
            index[num] = j
    return index


def extract_journal_detail(journal):
    """仕訳JSONから引き継ぎシート用の情報を抽出。
    1つのbranchにdebitor/creditor両方入る場合があるので両方linesに追加する。"""
    branches = journal.get("branches", [])
    detail = {
        "transaction_date": journal.get("transaction_date"),
        "memo": journal.get("memo", ""),
        "journal_type": journal.get("journal_type", ""),
        "lines": [],
    }
    for b in branches:
        for side_label, key in [("借方", "debitor"), ("貸方", "creditor")]:
            side_data = b.get(key)
            if not side_data:
                continue
            detail["lines"].append({
                "side": side_label,
                "account_name": side_data.get("account_name", ""),
                "sub_account_name": side_data.get("sub_account_name") or "",
                "department_name": side_data.get("department_name") or "",
                "tax_name": side_data.get("tax_name") or "",
                "tax_long_name": side_data.get("tax_long_name") or "",
                "invoice_kind": side_data.get("invoice_kind") or "",
                "trade_partner_name": side_data.get("trade_partner_name") or "",
                "value": side_data.get("value", 0),
                "tax_value": side_data.get("tax_value", 0),
                "remark": b.get("remark", ""),
            })
    return detail


def aggregate(transactions, journals_index=None):
    """通帳カタカナ + 勘定科目 + 補助科目 + 部門 + 税区分 でグループ化する。
    journals_indexがあれば、税区分・部門・複合仕訳構造を含めて集計する。"""

    # journals_indexがあれば、各取引に仕訳詳細を付与
    enriched = []
    for tx in transactions:
        info = dict(tx)
        if journals_index and tx.get("torihiki_no"):
            j = journals_index.get(tx["torihiki_no"])
            if j:
                info["journal_detail"] = extract_journal_detail(j)
        enriched.append(info)

    # 「相手側（通帳カタカナの裏で動く相手科目）」の代表行を抽出する関数
    # 残高照合画面に出てくる「相手勘定科目」は1つだけだが、実際は複合仕訳のことが多い
    def pick_representative_line(tx):
        """通帳科目（普通預金・現金等）以外の代表行を返す。
        入金なら通帳は借方 → 相手は貸方優先
        出金なら通帳は貸方 → 相手は借方優先
        これで売掛金回収の複合仕訳でも正しく相手を取れる。"""
        jd = tx.get("journal_detail")
        if not jd:
            return None
        is_nyukin = tx.get("nyukin") is not None
        target_side = "貸方" if is_nyukin else "借方"
        bank_keywords = ["普通預金", "当座預金", "現金"]
        primary = [
            line for line in jd["lines"]
            if line["side"] == target_side
            and not any(k in line["account_name"] for k in bank_keywords)
        ]
        if primary:
            return primary[0]
        non_bank = [
            line for line in jd["lines"]
            if not any(k in line["account_name"] for k in bank_keywords)
        ]
        if non_bank:
            return non_bank[0]
        return jd["lines"][0] if jd["lines"] else None

    # グループキー: (正規化カタカナ, 勘定科目, 補助科目, 部門, 税区分)
    groups = defaultdict(list)
    for tx in enriched:
        if tx["status"] != "入力済み":
            continue

        rep = pick_representative_line(tx)
        if rep:
            kamoku = rep["account_name"]
            hojo = rep["sub_account_name"] or tx.get("aite_hojo", "")
            dept = rep["department_name"]
            tax = rep["tax_name"]
            invoice_kind = rep["invoice_kind"]
        else:
            kamoku = tx["aite_kamoku"]
            hojo = tx["aite_hojo"]
            dept = ""
            tax = ""
            invoice_kind = ""

        key = (
            normalize_katakana(tx["tsucho_tekiyo"]),
            kamoku,
            hojo,
            dept,
            tax,
        )
        groups[key].append({**tx, "_rep": rep, "_kamoku": kamoku, "_hojo": hojo,
                            "_dept": dept, "_tax": tax, "_invoice_kind": invoice_kind})

    aggregated = []
    for (katakana_norm, kamoku, hojo, dept, tax), txs in groups.items():
        amounts = [tx["shukkin"] or tx["nyukin"] or 0 for tx in txs]
        amounts = [a for a in amounts if a > 0]
        is_nyukin = txs[0]["nyukin"] is not None

        # 複合仕訳の構造サンプル（最初の取引から）
        compound_sample = None
        if txs[0].get("journal_detail") and len(txs[0]["journal_detail"]["lines"]) > 2:
            compound_sample = {
                "torihiki_no": txs[0]["torihiki_no"],
                "lines": txs[0]["journal_detail"]["lines"],
            }

        aggregated.append({
            "katakana_normalized": katakana_norm,
            "katakana_samples": list(set(tx["tsucho_tekiyo"] for tx in txs))[:3],
            "kamoku": kamoku,
            "hojo": hojo,
            "department": dept,
            "tax_name": tax,
            "invoice_kind": txs[0].get("_invoice_kind", ""),
            "direction": "入金" if is_nyukin else "出金",
            "count": len(txs),
            "min_amount": min(amounts) if amounts else 0,
            "max_amount": max(amounts) if amounts else 0,
            "is_constant": len(set(amounts)) == 1 if amounts else False,
            "mf_tekiyo_samples": list(set(tx["mf_tekiyo"] for tx in txs if tx["mf_tekiyo"]))[:3],
            "is_compound": compound_sample is not None,
            "compound_sample": compound_sample,
            "torihiki_no_samples": list(set(tx["torihiki_no"] for tx in txs if tx["torihiki_no"]))[:3],
        })

    unprocessed = [
        {
            "date": tx["date"],
            "katakana": tx["tsucho_tekiyo"],
            "amount": tx["shukkin"] or tx["nyukin"],
            "direction": "入金" if tx["nyukin"] else "出金",
        }
        for tx in transactions if tx["status"] != "入力済み"
    ]

    return {
        "total_transactions": len(transactions),
        "input_count": sum(1 for tx in transactions if tx["status"] == "入力済み"),
        "unprocessed_count": len(unprocessed),
        "journal_match_count": sum(1 for tx in enriched if tx.get("journal_detail")),
        "aggregated": sorted(aggregated, key=lambda x: (-x["count"], x["katakana_normalized"])),
        "unprocessed": unprocessed,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", help="残高照合テキストファイル（複数可、口座ごと）")
    parser.add_argument("--journals", help="MF仕訳JSONファイル（突合に使用）")
    args = parser.parse_args()

    journals_index = None
    if args.journals:
        journals_index = load_journals_index(args.journals)
        print(f"# Loaded {len(journals_index)} journals from {args.journals}", file=sys.stderr)

    result = {"accounts": [], "has_journal_match": journals_index is not None}
    for path in args.files:
        account_name = Path(path).stem
        transactions = parse_file(path)
        agg = aggregate(transactions, journals_index)
        result["accounts"].append({
            "account_name": account_name,
            "source_file": path,
            **agg,
        })

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
