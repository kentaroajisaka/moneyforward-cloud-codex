# 勘定科目・補助科目・税区分

## 勘定科目

### mfc_ca_getAccounts

#### パラメータ

| 名前 | 型 | 必須 | 説明 |
|------|-----|------|------|
| access_token | string | Yes | アクセストークン |
| available | boolean | No | 利用可能な科目のみ取得するフィルタ |

#### レスポンス構造

**⚠️ 2026-04-19 実測による修正**: OpenAPI 仕様と実 API レスポンスに差分あり。以下は 2 法人（サンプル法人A・サンプル法人B）で全件確認した実測値。

```typescript
{
  accounts: [{
    id: string;                     // 勘定科目ID（URL エンコード済）
    name: string;                   // 科目名
    search_key?: string;            // 検索キー（科目コード相当）
    account_group: 'ASSET' | 'LIABILITY' | 'CAPITAL' | 'REVENUE' | 'EXPENSE';
    category?: string;              // 約 50 種類（下記参照）
    financial_statement_type: 'BALANCE_SHEET' | 'PROFIT_LOSS' | 'COST_REPORT';
    available: boolean;             // 利用可能フラグ
    tax_id?: string;                // デフォルト税区分ID
    sub_accounts?: [{               // 補助科目（親科目に埋め込まれる）
      id: string;
      account_id: string;           // 親科目 ID
      name: string;
      search_key: string | null;
      tax_id?: string;
    }];
  }]
}
```

**⚠️ 実 API レスポンスに存在しないキー**（旧ドキュメント記載）:
- `code` ← 存在しない。`search_key` が代替
- `account_category` ← 存在しない。`account_group` + `category` の組合せで代用
- `sub_category` ← 存在しない。`category` を使う
- `fs_type` (bs/pl/cr) ← 存在しない。**`financial_statement_type` で判定**（'BALANCE_SHEET' / 'PROFIT_LOSS' / 'COST_REPORT'）
- `display_order` ← 存在しない。並び順は**配列順序**が唯一の信頼できる情報
- `sub_accounts[].display_order` ← 存在しない

### `financial_statement_type` の 3 値（重要）

| 値 | 意味 |
|---|---|
| `BALANCE_SHEET` | BS（貸借対照表）科目 |
| `PROFIT_LOSS` | PL（損益計算書）科目 |
| `COST_REPORT` | **CR（製造原価報告書）科目**。製造業のみ出現 |

**CR 判定のベストプラクティス**（重要）:
- ✅ `financial_statement_type === 'COST_REPORT'` で判定する（全社共通の標準値）
- ❌ 科目名の `(製)` サフィックス等のヒューリスティックは**禁止**（会社依存、再現性なし）
- ❌ `account_group` は CR 科目も `EXPENSE` なので区別不可

### `category` の実測値（約 50 種類）

**BS 系**: `CASH_AND_DEPOSITS, TRADE_RECEIVABLES, INVENTORIES, MARKETABLE_SECURITIES, OTHER_CURRENT_ASSETS, PROPERTY_PLANT_AND_EQUIPMENT, INTANGIBLE_ASSETS, INVESTMENTS_AND_OTHER_ASSETS, DEFERRED_ASSETS, TRADE_PAYABLES, OTHER_CURRENT_LIABILITIES, NON_CURRENT_LIABILITIES, CAPITAL_STOCK, LEGAL_CAPITAL_SURPLUS, OTHER_CAPITAL_SURPLUS, LEGAL_RETAINED_EARNINGS, APPROPRIATED_RETAINED_EARNINGS, RETAINED_EARNINGS_BROUGHT_FORWARD, TREASURY_STOCK, SUBSCRIPTION_RIGHTS_TO_SHARES, VALUATION_AND_TRANSLATION_ADJUSTMENTS, SUNDRIES` 他

**PL 系**: `NET_SALES, COST_OF_PURCHASED_GOODS, BEGINNING_INVENTORY, ENDING_INVENTORY, SELLING_GENERAL_AND_ADMINISTRATIVE_EXPENSES, NON_OPERATING_INCOME, NON_OPERATING_EXPENSES, EXTRAORDINARY_INCOME, EXTRAORDINARY_LOSSES, CORPORATE_INCOME_TAXES_CURRENT, CORPORATE_INCOME_TAXES_DEFERRED, TRANSFERS_TO_OTHER_ACCOUNTS`

**CR 系**（製造業のみ）:
- `MANUFACTURING_EXPENSES` — 製造経費（減価償却費(製)、水道光熱費(製) 等）
- `LABOR_COSTS` — 労務費
- `COST_OF_MATERIALS` — 材料費
- `BEGINNING_MATERIALS` / `ENDING_MATERIALS` — 材料棚卸
- `BEGINNING_WORK_IN_PROCESS` / `ENDING_WORK_IN_PROCESS` — 仕掛品棚卸
- `TRANSFERS_TO_OTHER_ACCOUNTS`（CR 側） — 他勘定振替

### `sub_accounts` は親 account に埋め込まれる

`getAccounts` の各科目の `sub_accounts[]` 配列に補助科目が同梱される。別途 `getSubAccounts` を呼ぶ必要は**多くの場合不要**（特定科目の補助科目だけ絞り込み取得したい時のみ使う）。

---

## 補助科目

### mfc_ca_getSubAccounts

#### パラメータ

| 名前 | 型 | 必須 | 説明 |
|------|-----|------|------|
| access_token | string | Yes | アクセストークン |
| account_id | string | No | 勘定科目IDで絞り込み |

#### 用途

- 仕訳登録時に `sub_account_id` を指定するために事前取得する
- `account_id` を指定すると、その科目に紐づく補助科目のみ返る
- 補助科目なしの仕訳は `sub_account_id` を省略すればよい

---

## 税区分

### mfc_ca_getTaxes

#### パラメータ

| 名前 | 型 | 必須 | 説明 |
|------|-----|------|------|
| access_token | string | Yes | アクセストークン |
| available | boolean | No | 利用可能な税区分のみ取得するフィルタ |

#### レスポンス構造

```typescript
{
  taxes: [{
    id: string;              // 税区分ID
    name: string;            // 名称
    abbreviation?: string;   // 略称（例: '課仕 10%'）
    short_name?: string;
    search_key?: string;
    tax_rate?: number;       // 税率
    rate?: number;
    available?: boolean;
  }]
}
```

---

## IDの扱い ★重要

- 全てのID（`account_id`, `sub_account_id`, `tax_id`, `department_id`）は**URLエンコード済みの文字列**
- 仕訳登録・更新時は**エンコード済みのまま渡す**こと
- デコードしてから渡すとエラーになる

---

## 制約

- 勘定科目・補助科目・税区分の**登録・編集はMCPではできない**
- MFクラウド会計の画面から設定する必要がある
