#!/usr/bin/env python3
"""
仕訳データを pandas DataFrame に展開するローダー + 実質取引先抽出。
2つの入力形式に対応：
  1. MFC CA API の canonical JSON（journals_FY20XX.json）← 推奨・全フィールドあり
  2. MFCクラウド会計からエクスポートした CSV（cp932 or utf-8-sig）← 後方互換

Usage:
    from load_journals import load_df, enrich_partners, build_transaction_view
    df = load_df("/path/to/journals_FY2024.json")
    df = enrich_partners(df)              # 行ビュー: 実質取引先列を追加
    txn_df = build_transaction_view(df)   # 取引ビュー: 取引No単位で集約
"""

import json
import os
import re
import sys

try:
    import pandas as pd
except ImportError:
    print("pandas が必要です: pip install pandas", file=sys.stderr)
    sys.exit(1)

# MF公式API（alpha/beta）で実際に返る journal_type のラベル辞書。
# OpenAPI 仕様書記載の17種類に対応（SKILL.md 冒頭「仕訳の登録経路」16カテゴリ + JOURNAL_TYPE_NORMAL）。
# 注意: 公式APIでは BANK_IMPORT / CREDIT_CARD / MANUAL / TRANSFER / OPENING_BALANCE / CLOSING は返らない。
#       これらは旧自前MCP（mf-accounting）経由で返っていた非公式な値で、公式API移行後は使用しない。
ENTERED_BY_LABEL = {
    # 自動生成系
    "JOURNAL_TYPE_BILLING":        "MFクラウド請求書連携",
    "JOURNAL_TYPE_PAYROLL":        "MFクラウド給与連携",
    "JOURNAL_TYPE_EXPENSE":        "MFクラウド経費連携",
    "JOURNAL_TYPE_DEBT":           "MFクラウド債務支払連携",
    "JOURNAL_TYPE_STREAMED":       "STREAMED連携",
    "JOURNAL_TYPE_MOBILE_APP":     "モバイルアプリ",
    "JOURNAL_TYPE_ME":             "MF ME",
    "JOURNAL_TYPE_AI_OCR":         "AI-OCR",
    "JOURNAL_TYPE_E_INVOICE":      "デジタルインボイス",
    "JOURNAL_TYPE_EXTERNAL":       "外部API連携",
    "JOURNAL_TYPE_HOME_DEVOTE":    "家事按分",
    "JOURNAL_TYPE_DEPRECIATION":   "償却仕訳",
    "JOURNAL_TYPE_IMPORT":         "CSVインポート",
    "JOURNAL_TYPE_DATA_LINKAGE":   "データ連携（自動取得）",  # 2026-04時点では実データに出てこないが enum には存在
    # 手動系・開始系
    "JOURNAL_TYPE_NORMAL":         "手入力/データ連携",  # APIでは区別不可。補助科目マッチングで判定
    "JOURNAL_TYPE_OPENING":        "開始残高",
    "JOURNAL_TYPE_NONE":           "なし",
}

INVOICE_KIND_LABEL = {
    "INVOICE_KIND_NOT_TARGET": "対象外",
    "INVOICE_KIND_TAXABLE":    "課税",
    "INVOICE_KIND_EXEMPT":     "非課税",
    "INVOICE_KIND_ZERO_RATED": "ゼロ税率",
}


def _flatten_journals(journals):
    rows = []
    for j in journals:
        entered_by_raw = j.get("entered_by", "")
        for b in j.get("branches", []):
            deb = b.get("debitor") or {}
            cred = b.get("creditor") or {}
            rows.append({
                "取引No":           j.get("number", ""),
                "取引日":           j.get("transaction_date", ""),
                "journal_type":     j.get("journal_type", ""),
                "entered_by":       ENTERED_BY_LABEL.get(entered_by_raw, entered_by_raw),
                "is_realized":      j.get("is_realized", True),
                "memo":             j.get("memo", "") or "",
                "term_period":      j.get("term_period", ""),
                "借方勘定科目":     deb.get("account_name", "") or "",
                "借方補助科目":     deb.get("sub_account_name", "") or "",
                "借方部門":         deb.get("department_name", "") or "",
                "借方取引先":       deb.get("trade_partner_name", "") or "",
                "借方金額":         int(deb.get("value", 0) or 0),
                "借方税区分":       deb.get("tax_name", "") or "",
                "借方税額":         int(deb.get("tax_value", 0) or 0),
                "借方invoice_kind": INVOICE_KIND_LABEL.get(
                    deb.get("invoice_kind", ""), deb.get("invoice_kind", "")),
                "貸方勘定科目":     cred.get("account_name", "") or "",
                "貸方補助科目":     cred.get("sub_account_name", "") or "",
                "貸方部門":         cred.get("department_name", "") or "",
                "貸方取引先":       cred.get("trade_partner_name", "") or "",
                "貸方金額":         int(cred.get("value", 0) or 0),
                "貸方税区分":       cred.get("tax_name", "") or "",
                "貸方税額":         int(cred.get("tax_value", 0) or 0),
                "貸方invoice_kind": INVOICE_KIND_LABEL.get(
                    cred.get("invoice_kind", ""), cred.get("invoice_kind", "")),
                "摘要":             b.get("remark", "") or "",
            })
    return rows


def load_df(path: str) -> pd.DataFrame:
    """パスの拡張子でJSON/CSVを判別しDataFrameを返す。"""
    ext = os.path.splitext(path)[1].lower()

    if ext == ".json":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        rows = _flatten_journals(data.get("journals", []))
        df = pd.DataFrame(rows)
        df["取引日"] = pd.to_datetime(df["取引日"], errors="coerce")
        return df

    elif ext == ".csv":
        for enc in ("utf-8-sig", "cp932", "utf-8"):
            try:
                df = pd.read_csv(path, encoding=enc, dtype=str)
                break
            except UnicodeDecodeError:
                continue
        for col in df.columns:
            if "金額" in col:
                df[col] = pd.to_numeric(
                    df[col].str.replace(",", "", regex=False), errors="coerce"
                ).fillna(0).astype(int)
        if "取引日" in df.columns:
            df["取引日"] = pd.to_datetime(df["取引日"], errors="coerce")
        # カラム名を正規化: 「借方金額(円)」→「借方金額」（JSON形式と統一）
        df.columns = [col.replace("(円)", "") for col in df.columns]
        return df

    else:
        raise ValueError(f"サポートされていない形式です: {path}")


def apply_tax_inclusive(df: pd.DataFrame) -> pd.DataFrame:
    """
    税込経理の会社向けに、借方金額・貸方金額を value + tax_value に補正する。

    MF APIの仕訳データは常に value（税抜本体）と tax_value（税額）に分かれている。
    - 税抜経理: value のままでOK（税額は仮払/仮受消費税として別行で計上される）
    - 税込経理: value + tax_value が帳簿上の金額（仮払/仮受消費税の行はない）

    この関数は税込経理の場合にのみ呼び出す。
    借方税額・貸方税額列がない場合（CSV入力時等）は何もしない。
    """
    modified = False
    for side in ('借方', '貸方'):
        amt_col = f'{side}金額'
        tax_col = f'{side}税額'
        if amt_col in df.columns and tax_col in df.columns:
            df[amt_col] = df[amt_col] + df[tax_col]
            modified = True

    if modified:
        print("税込補正適用済み: 借方金額・貸方金額に税額を加算しました", file=sys.stderr)

    return df


# ---------------------------------------------------------------------------
# 実質取引先の抽出
# ---------------------------------------------------------------------------
# MFクラウド会計では「取引先」フィールドを運用していない会社が多い。
# 実務では補助科目に取引先名を入れて運用するのが一般的。
# このモジュールは以下の優先順位で実質的な取引先を特定する:
#   1. 相手科目の補助科目（売掛金/買掛金等の補助科目 = 最も信頼性が高い）
#   2. 自科目の補助科目
#   3. 取引先フィールド（使っていれば）
#   4. 摘要からの抽出（補助科目辞書マッチ → 法人名正規表現）
# ---------------------------------------------------------------------------

# 法人格パターン（前置・後置の両方に対応）
_CORP_PREFIXES = (
    r'株式会社|有限会社|合同会社|合資会社|合名会社|'
    r'一般社団法人|一般財団法人|公益社団法人|公益財団法人|'
    r'特定非営利活動法人|NPO法人|'
    r'医療法人|医療法人社団|医療法人財団|社会医療法人|'
    r'社会福祉法人|学校法人|宗教法人|'
    r'独立行政法人|国立研究開発法人|地方独立行政法人'
)
_CORP_ABBREVS = r'\(株\)|\(有\)|\(合\)|\(医\)|\(福\)|\(学\)'

_RE_CORP_NAME = re.compile(
    r'(?:'
    # パターン1: 法人格（正式名称）＋名前
    r'(?:' + _CORP_PREFIXES + r')[\s　]*[\w\u3000-\u9FFF\uFF00-\uFFEF]+'
    r'|'
    # パターン2: 名前＋法人格（正式名称）
    r'[\w\u3000-\u9FFF\uFF00-\uFFEF]+[\s　]*(?:' + _CORP_PREFIXES + r')'
    r'|'
    # パターン3: 略称（(株)〇〇 / 〇〇(株)）
    r'(?:' + _CORP_ABBREVS + r')[\s　]*[\w\u3000-\u9FFF\uFF00-\uFFEF]+'
    r'|'
    r'[\w\u3000-\u9FFF\uFF00-\uFFEF]+[\s　]*(?:' + _CORP_ABBREVS + r')'
    r')'
)

# 摘要から除外する汎用語（補助科目の辞書マッチ用。取引先名ではない頻出トークン）
# 注意: 摘要からの取引先抽出では汎用語除外は行わない（Claudeの解釈フェーズで判断する）
_REMARK_NOISE = {
    '振込', '振替', '入金', '出金', '支払', '請求', '売上', '仕入',
    '手数料', '月分', '年分', '源泉', '所得税', '消費税',
    '普通預金', '当座預金', '現金', '小口現金',
}

# 債権債務科目（相手科目の補助科目が取引先名である可能性が高い科目）
_RECEIVABLE_PAYABLE = {
    '売掛金', '買掛金', '未収入金', '未収金', '未払金', '未払費用',
    '前受金', '前払金', '前払費用', '立替金', '仮払金', '仮受金',
    '預り金', '受取手形', '支払手形', '長期未払金',
}


def _build_partner_dict(df: pd.DataFrame) -> set:
    """
    補助科目から取引先名の辞書を構築する。
    債権債務科目の補助科目 + 全補助科目のユニーク値を収集。
    """
    names = set()
    for side in ('借方', '貸方'):
        acct_col = f'{side}勘定科目'
        sub_col = f'{side}補助科目'
        if acct_col in df.columns and sub_col in df.columns:
            # 債権債務科目の補助科目（最も信頼性が高い）
            mask = df[acct_col].isin(_RECEIVABLE_PAYABLE)
            names |= set(df.loc[mask, sub_col].dropna().unique())
            # 全補助科目も収集（銀行口座名等のノイズを含むが辞書マッチで有用）
            names |= set(df[sub_col].dropna().unique())
    names.discard('')
    # 短すぎる名前（1文字）や汎用語を除外
    names = {n for n in names if len(n) > 1 and n not in _REMARK_NOISE}
    return names


def _extract_from_remark(remark: str, known_partners: set) -> str:
    """
    摘要テキストから取引先名を抽出する。
    1. 既知の取引先名（補助科目辞書）で部分一致マッチ
    2. 法人名の正規表現パターンマッチ
    3. 短い摘要（15文字以下）で汎用語でなければ取引先候補として採用
       - スペース区切りがある場合は最初のトークンを取引先名とする
       - 「〇〇商事　○月分」→「〇〇商事」（最初のトークンを取引先名として採用）
       - 「電力料」→ 汎用語なので除外
    """
    if not remark or not remark.strip():
        return ''
    remark = remark.strip()

    # 1. 既知の取引先名で辞書マッチ（長い名前から優先）
    for name in sorted(known_partners, key=len, reverse=True):
        if name in remark:
            return name

    # 2. 法人名パターンマッチ
    m = _RE_CORP_NAME.search(remark)
    if m:
        return m.group().strip()

    # 3. 短い摘要からの取引先候補抽出
    #    取引先名か取引内容かの判断はClaude側で行う。ここでは広めに拾う。
    if len(remark) <= 20:
        # スペース（全角・半角）で分割し、最初の意味のあるトークンを取得
        tokens = re.split(r'[\s　/／・]+', remark)
        tokens = [t.strip() for t in tokens if t.strip()]
        if not tokens:
            return ''

        candidate = tokens[0]

        # 最低限の除外: 数字のみ、1文字
        if len(candidate) <= 1:
            return ''
        if re.match(r'^[\d,./-]+$', candidate):
            return ''

        return candidate

    return ''


def _resolve_partner(row, side: str, known_partners: set) -> str:
    """
    1行の仕訳から実質的な取引先を特定する。

    優先順位:
      1. 相手科目が債権債務科目の場合、その補助科目
      2. 自科目の補助科目（勘定科目名と異なる場合）
      3. 取引先フィールド
      4. 摘要からの抽出
    """
    other = '貸方' if side == '借方' else '借方'

    # 1. 相手科目が債権債務科目 → その補助科目が取引先
    other_acct = row.get(f'{other}勘定科目', '')
    other_sub = row.get(f'{other}補助科目', '')
    if other_acct in _RECEIVABLE_PAYABLE and other_sub:
        return other_sub

    # 2. 自科目の補助科目（科目名そのものでない場合）
    my_sub = row.get(f'{side}補助科目', '')
    my_acct = row.get(f'{side}勘定科目', '')
    if my_sub and my_sub != my_acct:
        return my_sub

    # 3. 取引先フィールド
    partner = row.get(f'{side}取引先', '')
    if partner:
        return partner

    # 4. 摘要から抽出
    remark = row.get('摘要', '')
    return _extract_from_remark(remark, known_partners)


def enrich_partners(df: pd.DataFrame) -> pd.DataFrame:
    """
    DataFrameに実質取引先列（借方_実質取引先 / 貸方_実質取引先）を追加する。

    Usage:
        df = load_df("journals.json")
        df = enrich_partners(df)
        # → df['借方_実質取引先'], df['貸方_実質取引先'] が使える
    """
    known = _build_partner_dict(df)

    df['借方_実質取引先'] = df.apply(
        lambda r: _resolve_partner(r, '借方', known), axis=1)
    df['貸方_実質取引先'] = df.apply(
        lambda r: _resolve_partner(r, '貸方', known), axis=1)

    return df


# ---------------------------------------------------------------------------
# 取引ビュー（取引No単位の集約）
# ---------------------------------------------------------------------------
# 複合仕訳（給与支払い、売上+消費税 等）では1取引が複数行に分かれる。
# 行ビュー（df）は科目別の残高計算・口座別集計に適するが、
# 取引先の特定・取引回数のカウント・定期取引パターンの検出では
# 取引No単位で見ないと正確な結果が得られない。
#
# build_transaction_view() は取引No単位で以下を集約する:
#   - 実質取引先: 全行から最も信頼性の高い取引先名を1つ選ぶ
#   - 借方科目群/貸方科目群: 全行の科目を集約（主科目＋サブ科目）
#   - 合計金額: 借方合計（=貸方合計）
#   - 部門: 全行から部門を集約
#   - 複合仕訳テンプレート: 全行の借方/貸方パターンを保持
# ---------------------------------------------------------------------------

# 預金・現金等の「口座系」科目（取引先ではなく資金の出入口）
_FUND_ACCOUNTS = {
    '普通預金', '当座預金', '定期預金', '現金', '小口現金',
    '受取手形', '支払手形', '資金移動',
}

# 税金・経過勘定等の「付随科目」（取引の本質ではなく付随する行）
_TAX_TRANSIT_ACCOUNTS = {
    '仮受消費税', '仮払消費税', '仮受消費税等', '仮払消費税等',
    '預り金',  # 源泉・住民税の預り
}


def _find_best_partner_in_group(group: pd.DataFrame, known_partners: set) -> str:
    """
    取引No単位のグループから最も信頼性の高い実質取引先を1つ返す。

    優先順位:
      1. 債権債務科目（売掛金・買掛金等）の補助科目
      2. 取引先フィールド（どれか1行にでもあれば）
      3. 費用/収益科目の補助科目（口座名・税金科目を除外）
      4. 摘要からの抽出
    """
    # 1. 債権債務科目の補助科目を全行からスキャン
    for _, row in group.iterrows():
        for side in ('借方', '貸方'):
            acct = row.get(f'{side}勘定科目', '')
            sub = row.get(f'{side}補助科目', '')
            if acct in _RECEIVABLE_PAYABLE and sub:
                return sub

    # 2. 取引先フィールド
    for _, row in group.iterrows():
        for side in ('借方', '貸方'):
            tp = row.get(f'{side}取引先', '')
            if tp:
                return tp

    # 3. 費用/収益科目の補助科目（口座名・税金科目を除外）
    for _, row in group.iterrows():
        for side in ('借方', '貸方'):
            acct = row.get(f'{side}勘定科目', '')
            sub = row.get(f'{side}補助科目', '')
            if sub and acct not in _FUND_ACCOUNTS and acct not in _TAX_TRANSIT_ACCOUNTS:
                if sub != acct:  # 補助科目が勘定科目名そのものでない
                    return sub

    # 4. 摘要から抽出（最初の非空摘要を使う）
    for _, row in group.iterrows():
        remark = row.get('摘要', '')
        if remark:
            result = _extract_from_remark(remark, known_partners)
            if result:
                return result

    return ''


def _find_dept_in_group(group: pd.DataFrame) -> str:
    """取引No単位のグループから部門を特定する。複数あればカンマ区切り。"""
    depts = set()
    for _, row in group.iterrows():
        for side in ('借方', '貸方'):
            d = row.get(f'{side}部門', '')
            if d:
                depts.add(d)
    if len(depts) == 0:
        return ''
    if len(depts) == 1:
        return depts.pop()
    return ', '.join(sorted(depts))


def _classify_accounts(group: pd.DataFrame, side: str) -> dict:
    """
    取引No単位で借方または貸方の科目を分類する。
    Returns: {
        'main_account': 金額最大の科目名,
        'main_sub': その補助科目,
        'main_amount': その金額,
        'all_accounts': [(科目, 補助, 金額), ...] 全行分
    }
    """
    acct_col = f'{side}勘定科目'
    sub_col = f'{side}補助科目'
    amt_col = f'{side}金額'

    entries = []
    for _, row in group.iterrows():
        acct = row.get(acct_col, '')
        sub = row.get(sub_col, '')
        amt = row.get(amt_col, 0)
        if acct and amt > 0:
            entries.append((acct, sub, amt))

    if not entries:
        return {
            'main_account': '',
            'main_sub': '',
            'main_amount': 0,
            'all_accounts': [],
        }

    # 金額最大の行を主科目とする（ただし税金・預り金は除外して選ぶ）
    non_tax = [e for e in entries if e[0] not in _TAX_TRANSIT_ACCOUNTS]
    main = max(non_tax, key=lambda x: x[2]) if non_tax else max(entries, key=lambda x: x[2])

    return {
        'main_account': main[0],
        'main_sub': main[1],
        'main_amount': main[2],
        'all_accounts': entries,
    }


def build_transaction_view(df: pd.DataFrame) -> pd.DataFrame:
    """
    行ビュー（enrich_partners済み）を取引No単位で集約した取引ビューを返す。

    取引ビューの列:
      取引No, 取引日, 行数,
      借方主科目, 借方主補助, 貸方主科目, 貸方主補助,
      借方科目一覧, 貸方科目一覧,  (文字列: "科目1/科目2/...")
      合計金額,  (借方合計)
      実質取引先, 取引先ソース,
      部門,
      摘要, entered_by (JSONのみ)

    Usage:
        df = load_df("journals.json")
        df = enrich_partners(df)
        txn_df = build_transaction_view(df)
    """
    known = _build_partner_dict(df)
    txns = []

    for txn_no, group in df.groupby('取引No', sort=False):
        dr = _classify_accounts(group, '借方')
        cr = _classify_accounts(group, '貸方')

        partner = _find_best_partner_in_group(group, known)

        # 取引先がどの優先順位で特定されたか判別
        partner_source = ''
        if partner:
            # 債権債務科目の補助科目か？
            for _, row in group.iterrows():
                for side in ('借方', '貸方'):
                    acct = row.get(f'{side}勘定科目', '')
                    sub = row.get(f'{side}補助科目', '')
                    if acct in _RECEIVABLE_PAYABLE and sub == partner:
                        partner_source = f'{acct}の補助科目'
                        break
                if partner_source:
                    break
            if not partner_source:
                for _, row in group.iterrows():
                    for side in ('借方', '貸方'):
                        if row.get(f'{side}取引先', '') == partner:
                            partner_source = '取引先フィールド'
                            break
                    if partner_source:
                        break
            if not partner_source:
                for _, row in group.iterrows():
                    for side in ('借方', '貸方'):
                        acct = row.get(f'{side}勘定科目', '')
                        sub = row.get(f'{side}補助科目', '')
                        if sub == partner and acct not in _FUND_ACCOUNTS:
                            partner_source = f'{acct}の補助科目'
                            break
                    if partner_source:
                        break
            if not partner_source:
                partner_source = '摘要から抽出'

        # 借方科目一覧・貸方科目一覧（ユニークな科目名をスラッシュ区切り）
        dr_accts = '/'.join(dict.fromkeys(a[0] for a in dr['all_accounts']))
        cr_accts = '/'.join(dict.fromkeys(a[0] for a in cr['all_accounts']))

        # 摘要: 全行の摘要を結合（重複除去）
        remarks = list(dict.fromkeys(
            r for r in group['摘要'] if r and str(r).strip()))
        remark = remarks[0] if remarks else ''

        row_data = {
            '取引No': txn_no,
            '取引日': group['取引日'].iloc[0],
            '行数': len(group),
            '借方主科目': dr['main_account'],
            '借方主補助': dr['main_sub'],
            '貸方主科目': cr['main_account'],
            '貸方主補助': cr['main_sub'],
            '借方科目一覧': dr_accts,
            '貸方科目一覧': cr_accts,
            '合計金額': group['借方金額'].sum(),
            '実質取引先': partner,
            '取引先ソース': partner_source,
            '部門': _find_dept_in_group(group),
            '摘要': remark,
        }

        # JSON時のみの列
        if 'entered_by' in group.columns:
            row_data['entered_by'] = group['entered_by'].iloc[0]
        if 'is_realized' in group.columns:
            row_data['is_realized'] = group['is_realized'].iloc[0]

        txns.append(row_data)

    txn_df = pd.DataFrame(txns)
    if '取引日' in txn_df.columns:
        txn_df['取引日'] = pd.to_datetime(txn_df['取引日'], errors='coerce')
    return txn_df


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python load_journals.py <path.json|path.csv>")
        sys.exit(1)
    df = load_df(sys.argv[1])
    df = enrich_partners(df)
    txn_df = build_transaction_view(df)

    print(f"行ビュー: {len(df)} 行")
    print(f"取引ビュー: {len(txn_df)} 取引")
    print(f"  うち複合仕訳: {(txn_df['行数'] > 1).sum()} 件")

    # 実質取引先の抽出結果サマリー
    filled = (txn_df['実質取引先'] != '').sum()
    total = len(txn_df)
    print(f"  取引先特定: {filled}/{total} ({filled/total*100:.1f}%)")
    print(f"  特定元内訳:")
    print(txn_df[txn_df['実質取引先'] != '']['取引先ソース'].value_counts().to_string())
