"""
MFデータ連携 → 登録済み一覧 → 明細一覧の画面コピペをパースする。

入力: MFクラウド会計 > データ連携 > 登録済み一覧 > 各サービスの明細一覧画面のテキストコピペ
出力: JSON（取引明細のリスト + 集計）

明細一覧画面の特徴:
- 残高照合と違い「相手勘定科目」「補助科目」が画面に表示されない
- ステータス・取引No・カタカナ摘要・金額（±）のみ取得可能
- → JSON突合（journals JSONとの突合）が必須
- 銀行・カードどちらも同じUI構造で取れる（カード画面では「残高」が「-円」になる）

使い方:
    python3 parse_meisai_list.py --journals <journals.json> <file1.txt> [<file2.txt> ...] > output.json

各取引は3行で構成される（タブ区切り）:
  行1: 日付 \t 内容(カタカナ) \t 金額(±円) \t 残高 \t 連携サービス名
  行2: 口座名（連携サービス名の続き）
  行3: ステータス \t 取引No \t (空)
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

YEN_RE = re.compile(r"^(-?[\d,]+)円$")
DATE_RE = re.compile(r"^\d{4}/\d{1,2}/\d{1,2}$")


def parse_yen(s):
    if not s or s == "-円":
        return None
    m = YEN_RE.match(s.strip())
    if m:
        return int(m.group(1).replace(",", ""))
    return None


def _strip_leading_tab(line):
    """対象外行（先頭TAB）を通常行と同じ形に正規化。"""
    return line.lstrip("\t") if line.startswith("\t") and len(line) > 1 and DATE_RE.match(line.lstrip("\t").split("\t")[0].strip() or "") else line


def _detect_format(lines, start_idx):
    """ヘッダー直後の最初の取引行を見て、1行形式（手動管理）か3行形式（自動取得）かを判定。
    1行形式: 1行に 日付/内容/金額/残高/サービス名/ステータス/取引No が全部入る（7列以上）
    3行形式: 1行目はサービス名で切れる（5列程度）、2行目に口座名、3行目にステータス・取引No
    """
    for j in range(start_idx, min(start_idx + 20, len(lines))):
        line = _strip_leading_tab(lines[j])
        cols = line.split("\t")
        if cols and DATE_RE.match(cols[0].strip()):
            # 6列目以降に「入力済み」「未入力」「対象外」が入っていれば1行形式
            if len(cols) >= 6 and cols[5].strip() in ("入力済み", "未入力", "対象外"):
                return "one_line"
            return "three_line"
    return "three_line"  # fallback


def parse_file(path):
    """明細一覧テキスト1ファイルをパース。取引のリストを返す。
    自動取得（3行/取引）と手動管理（1行/取引）の両方に対応。
    """
    text = Path(path).read_text(encoding="utf-8")
    lines = text.split("\n")

    transactions = []
    i = 0
    # ヘッダー行を探してその次から処理開始
    while i < len(lines):
        if lines[i].startswith("\t日付\t内容"):
            i += 1
            break
        i += 1

    fmt = _detect_format(lines, i)

    if fmt == "one_line":
        # 手動管理形式: 1行で1取引
        while i < len(lines):
            line = _strip_leading_tab(lines[i])
            cols = line.split("\t")
            if cols and DATE_RE.match(cols[0].strip()):
                tx = {
                    "date": cols[0].strip(),
                    "katakana": cols[1].strip() if len(cols) > 1 else "",
                    "amount": parse_yen(cols[2]) if len(cols) > 2 else None,
                    "direction": "",  # 後で設定
                    "zandaka": parse_yen(cols[3]) if len(cols) > 3 else None,
                    "service_name": cols[4].strip() if len(cols) > 4 else "",
                    "account_name": "",  # 手動管理は口座名フィールドなし
                    "status": cols[5].strip() if len(cols) > 5 else "",
                    "torihiki_no": cols[6].strip() if len(cols) > 6 else "",
                }
                tx["direction"] = "入金" if (tx["amount"] or 0) > 0 else "出金"
                transactions.append(tx)
            i += 1
    else:
        # 自動取得形式: 3行で1取引
        while i < len(lines) - 2:
            line1 = lines[i]
            cols1 = line1.split("\t")
            if cols1 and DATE_RE.match(cols1[0].strip()):
                date = cols1[0].strip()
                content = cols1[1].strip() if len(cols1) > 1 else ""
                amount = parse_yen(cols1[2]) if len(cols1) > 2 else None
                zandaka = parse_yen(cols1[3]) if len(cols1) > 3 else None
                service_name = cols1[4].strip() if len(cols1) > 4 else ""

                account_name = lines[i + 1].strip()

                line3 = lines[i + 2]
                cols3 = line3.split("\t")
                status = cols3[0].strip() if len(cols3) > 0 else ""
                torihiki_no = cols3[1].strip() if len(cols3) > 1 else ""

                tx = {
                    "date": date,
                    "katakana": content,
                    "amount": amount,
                    "direction": "入金" if (amount or 0) > 0 else "出金",
                    "zandaka": zandaka,
                    "service_name": service_name,
                    "account_name": account_name,
                    "status": status,
                    "torihiki_no": torihiki_no,
                }
                transactions.append(tx)
                i += 3
            else:
                i += 1

    return transactions


def normalize_katakana(s):
    """カタカナ摘要を正規化（プレフィックス・末尾の番号等を除去）。"""
    s = re.sub(r"^(振込入金|入金|出金)\s*", "", s)
    # ETC等の数値サフィックス・接尾辞は残す（金額帯と合わせて取引先を特定する手がかり）
    return s.strip()


def load_journals_index(journals_path):
    data = json.loads(Path(journals_path).read_text(encoding="utf-8"))
    journals = data.get("journals", [])
    index = {}
    for j in journals:
        num = str(j.get("number", "")).strip()
        if num:
            index[num] = j
    return index


def extract_journal_detail(journal):
    """1つのbranchにdebitor/creditor両方入る場合があるので、両方linesに追加する。"""
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
    enriched = []
    for tx in transactions:
        info = dict(tx)
        if journals_index and tx.get("torihiki_no"):
            j = journals_index.get(tx["torihiki_no"])
            if j:
                info["journal_detail"] = extract_journal_detail(j)
        enriched.append(info)

    # 通帳科目（普通預金/未払金/カード等）以外の代表行を返す
    # 入金（amount > 0）→ 通帳科目は借方、相手は貸方
    # 出金（amount < 0）→ 通帳科目は貸方、相手は借方
    # → 通帳の反対側の科目を優先して選ぶ
    bank_card_keywords = ["普通預金", "当座預金", "現金", "未払金"]

    def pick_representative_line(tx):
        jd = tx.get("journal_detail")
        if not jd:
            return None
        is_nyukin = (tx.get("amount") or 0) > 0
        target_side = "貸方" if is_nyukin else "借方"
        # まず「通帳の反対側」かつ「通帳系科目以外」を優先
        primary = [
            line for line in jd["lines"]
            if line["side"] == target_side
            and not any(k in line["account_name"] for k in bank_card_keywords)
        ]
        if primary:
            return primary[0]
        # フォールバック1: 反対側になくても通帳系以外の行
        non_bank = [
            line for line in jd["lines"]
            if not any(k in line["account_name"] for k in bank_card_keywords)
        ]
        if non_bank:
            return non_bank[0]
        # フォールバック2: 全部通帳系（口座間振替等）→1行目を返す
        return jd["lines"][0] if jd["lines"] else None

    groups = defaultdict(list)
    for tx in enriched:
        if tx["status"] != "入力済み":
            continue
        rep = pick_representative_line(tx)
        if rep:
            kamoku = rep["account_name"]
            hojo = rep["sub_account_name"]
            dept = rep["department_name"]
            tax = rep["tax_name"]
            invoice_kind = rep["invoice_kind"]
        else:
            kamoku = ""
            hojo = ""
            dept = ""
            tax = ""
            invoice_kind = ""

        key = (
            normalize_katakana(tx["katakana"]),
            kamoku,
            hojo,
            dept,
            tax,
        )
        groups[key].append({
            **tx, "_rep": rep, "_kamoku": kamoku, "_hojo": hojo,
            "_dept": dept, "_tax": tax, "_invoice_kind": invoice_kind,
        })

    aggregated = []
    for (katakana_norm, kamoku, hojo, dept, tax), txs in groups.items():
        amounts = [abs(tx["amount"]) for tx in txs if tx["amount"] is not None]
        amounts = [a for a in amounts if a > 0]
        is_nyukin = (txs[0].get("amount") or 0) > 0

        compound_sample = None
        if txs[0].get("journal_detail") and len(txs[0]["journal_detail"]["lines"]) > 2:
            compound_sample = {
                "torihiki_no": txs[0]["torihiki_no"],
                "lines": txs[0]["journal_detail"]["lines"],
            }

        aggregated.append({
            "katakana_normalized": katakana_norm,
            "katakana_samples": list(set(tx["katakana"] for tx in txs))[:3],
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
            "is_compound": compound_sample is not None,
            "compound_sample": compound_sample,
            "torihiki_no_samples": list(set(tx["torihiki_no"] for tx in txs if tx["torihiki_no"]))[:3],
        })

    unprocessed = [
        {
            "date": tx["date"],
            "katakana": tx["katakana"],
            "amount": tx["amount"],
            "direction": "入金" if (tx["amount"] or 0) > 0 else "出金",
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
    parser.add_argument("files", nargs="+", help="明細一覧テキストファイル（複数可、サービスごと）")
    parser.add_argument("--journals", help="MF仕訳JSONファイル（突合に使用）")
    args = parser.parse_args()

    journals_index = None
    if args.journals:
        journals_index = load_journals_index(args.journals)
        print(f"# Loaded {len(journals_index)} journals from {args.journals}", file=sys.stderr)

    result = {"accounts": [], "has_journal_match": journals_index is not None}
    for path in args.files:
        service_name = Path(path).stem
        transactions = parse_file(path)
        agg = aggregate(transactions, journals_index)
        result["accounts"].append({
            "account_name": service_name,
            "source_file": path,
            **agg,
        })
        print(f"# {service_name}: {agg['total_transactions']}件取引、JSON突合 {agg['journal_match_count']}件", file=sys.stderr)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
