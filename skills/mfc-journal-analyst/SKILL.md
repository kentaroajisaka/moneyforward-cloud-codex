---
name: mfc-journal-analyst
metadata:
  version: 2.0.0
description: |
  マネーフォワードクラウド会計（MFC CA）から仕訳を取得・分析し、
  2種類のレポートを生成するスキル：
  (A) 総合分析レポート: ビジネスモデル・主要取引先・定期取引・支払回収サイト・給与・部門・入力元分析
  (B) 入力担当者向け引き継ぎシート: 記帳代行の8ステップに沿った引き継ぎ資料

  実質取引先は補助科目→取引先フィールド→摘要の優先順位で自動抽出する。
  部門分析にも対応（取引先→部門の対応表、科目別の部門付与ルール等）。

  以下のようなリクエストで必ずこのスキルを使うこと：
  - 「MFC」「マネーフォワード」「MF」「クラウド会計」＋ 分析・調査・まとめ・教えての意図
  - 「〇〇社のビジネスモデルを分析したい」「〇〇社の仕訳の流れを調べたい」
  - 「〇〇社のお金の流れを見たい」「〇〇社の引き継ぎ資料を作りたい」（会計文脈で）
  - 「記帳代行の引き継ぎ」「入力担当者向け」「記帳の手順書」
  - 「クラウド会計の情報を使って〜」「MFのデータを見て〜」と言われたとき
  - マネーフォワードクラウド会計からエクスポートしたCSVまたはJSONが渡されたとき
    （他の会計ソフトのCSVには対応していない。MF形式か確認すること）
---

# MFC Journal Analyst

マネーフォワードクラウド会計の仕訳データを取得・分析し、ビジネス実態を読み解いたレポートを生成する。

スクリプトはこのSKILL.mdと同じディレクトリの `scripts/` にある。
実行時は `<skill_dir>` をこのスキルの絶対パスに置き換えること。

## CodexプラグインでのMCP名

このスキルを `moneyforward-cloud-mcp` プラグインから使う場合、MCPサーバー名は以下の2つ。

- `mf-official-beta`: 通常はこちらを優先。PKCE + localhostコールバックで認証する。
- `mf-official-alpha`: 複数法人を同時に扱う場合や、認証コード貼り付け型が必要な場合に使う。

Claude時代の古い記述に `mcp__mfc_ca__...` が出てきた場合は、Codexでは現在有効なサーバーのツールに読み替えること。

- beta版: `mcp__mf-official-beta__authenticate`, `mcp__mf-official-beta__mfc_ca_getJournals` 等
- alpha版: `mcp__mf-official-alpha__mfc_ca_authorize`, `mcp__mf-official-alpha__mfc_ca_exchange`, `mcp__mf-official-alpha__mfc_ca_getJournals` 等

以降の手順では便宜上 `mfc_ca_*` とサフィックスだけを書く。実行時は `mf-official-beta` または `mf-official-alpha` の実ツール名を使う。

---

## 鉄則：「先に全部読む、後で答える」

**回答を書く前に必ずPythonで全仕訳を集計・分類してから回答する。**

仕訳データは数千行に及ぶことが多く、目で追って推測するとミスが起きる。
特に「この会社は〇〇事業をしている」「この取引先は〇〇だ」という判断は、
摘要・補助科目・取引先列をすべてデータとして読んでから行うこと。

**やってはいけないこと：**
- 数件だけ見て全体を類推する
- 会社名や勘定科目名だけで取引の実態を推測する（摘要を必ず読む）
- 外国人名・海外地名だけで取引の実態を決めつける（摘要から必ず確認する）
- **補助科目・摘要・相手科目・貸借ペア・連携サービス名・口座名で分かることをユーザーに聞く**（例: 「未払金の内訳」「借入金の借入先」「カードの引落口座」は補助科目・摘要・相手科目を集計すれば全部分かる。聞く前に自分で調べる）
- **スキル内のテンプレを勝手に省略・要約・短縮する**（「冗長」「ユーザーが知っているから不要」等の自己判断は禁止。**テンプレはリテラル（一字一句）で出力する**。省略するのはユーザーが明示的に「それはいらん」と言った場合のみ）

---

## 用語定義：「入力ソース」「入力方法」「証憑」を厳密に区別する

このスキルで頻出する3つの用語を以下の通り厳密に区別する。混同すると手順3の対話が崩壊する。

| 用語 | 定義 | 例 |
|---|---|---|
| **入力ソース** | 仕訳が MFにどの経路で入ったかの**カテゴリ**（大分類） | データ連携 / 手入力 / MF給与連携 / CSVインポート / 外部ツール連携 / 経費精算 |
| **入力方法** | 具体的な操作手段（MFのどの画面、どのボタン等）| MFの「手動で仕訳」画面 / 「手動で取引」画面 / CSVアップロード / API直叩き |
| **証憑** | 仕訳を起票する際に**元データとして参照した資料** | 通帳・明細書・請求書・領収書・手書き現金出納帳・タイムカード・勤怠データ 等 |

**重要な関係**:
- **入力ソース** は仕訳データの `entered_by`・補助科目・連携サービス名から**機械的に推定できる**
- **入力方法** は API/仕訳データでは**推定できない**（同じ「手入力」でもユーザーによって画面や手順が違う）→ **聞かない**（引き継ぎ書の骨格には不要）
- **証憑** は API/仕訳データでは**推定できない** → 手順3で必ずユーザーに聞く

**このスキルで対話する対象は「入力ソース（確認）」と「証憑（深掘り）」の2つのみ**。入力方法は聞かない（ユーザーの認知負荷を上げるだけで引き継ぎ書の精度に寄与しない）。

**「仕訳の登録経路」（入力ソース）の全カテゴリ（MF公式API `journal_type` + 実務慣習に基づく 16種）**:

| # | 登録経路 | 判定元 |
|---|---|---|
| 1 | **データ連携（自動取得）** | 補助科目が自動取得連携サービス名（銀行・カード・電子マネー等） |
| 2 | **データ連携（手動管理）** | 補助科目が手動管理連携サービス名（現金出納帳・手動CSV口座）※ 実際の入力手段は画面手入力 or CSVアップロードで分かれる・要ユーザー確認 |
| 3 | **MFクラウド給与連携** | `entered_by == JOURNAL_TYPE_PAYROLL` |
| 4 | **CSVインポート** | `entered_by == JOURNAL_TYPE_IMPORT` |
| 5 | **MFクラウド経費連携** | `entered_by == JOURNAL_TYPE_EXPENSE` |
| 6 | **MFクラウド請求書連携** | `entered_by == JOURNAL_TYPE_BILLING` |
| 7 | **MFクラウド債務支払連携** | `entered_by == JOURNAL_TYPE_DEBT` |
| 8 | **STREAMED連携** | `entered_by == JOURNAL_TYPE_STREAMED` |
| 9 | **モバイルアプリ** | `entered_by == JOURNAL_TYPE_MOBILE_APP` |
| 10 | **AI-OCR** | `entered_by == JOURNAL_TYPE_AI_OCR` |
| 11 | **デジタルインボイス** | `entered_by == JOURNAL_TYPE_E_INVOICE` |
| 12 | **外部API連携** | `entered_by == JOURNAL_TYPE_EXTERNAL`（ETC連携・POS連携・サードパーティーツール等） |
| 13 | **家事按分** | `entered_by == JOURNAL_TYPE_HOME_DEVOTE` |
| 14 | **償却仕訳** | `entered_by == JOURNAL_TYPE_DEPRECIATION` |
| 15 | **開始残高** | `entered_by == JOURNAL_TYPE_OPENING` |
| 16 | **手入力** | 上記いずれにも該当しない（`JOURNAL_TYPE_NORMAL` かつ補助科目が連携サービスに紐づかない） |

**重要な注意**:
- 2026-04時点では `JOURNAL_TYPE_DATA_LINKAGE` は OpenAPI の enum にはあるが**実データには出てこない**。データ連携の仕訳は `JOURNAL_TYPE_NORMAL` に入って返る。
- そのため「データ連携 vs 手入力」の区別は **補助科目と連携サービス名のマッチング**で行う。
- 「データ連携（手動管理）」は補助科目ベースで識別できるが、**実際の入力手段（画面手入力 or CSVアップロード）はユーザーに聞かないと分からない**。

「現金出納帳（手書き）を見て手入力」「月次請求書を見て手入力」等は全部「**手入力**」のサブカテゴリで、**違いは証憑で区別**される（分類を増やさない）。

**「フェーズ」の正式名称（全SKILL.md・全成果物で統一）**:

引き継ぎ書 Step 5（月次入力フロー）および手順5.5 の網羅性検証で使う「月次作業フェーズ」は **フェーズ1〜6** で統一する。過去の生成実績で「フェーズA〜F」「月次作業①〜⑥」等の異表記があったら全部「フェーズ1〜6」に書き換えること。

- フェーズ1: データ連携の仕訳候補処理
- フェーズ2: 月次補助元帳から手起票
- フェーズ3: 給与・社保（MF給与連携）
- フェーズ4: 不定期の手起票
- フェーズ5: 年次・決算整理（振替含む）
- フェーズ6: 残高チェック

※「Phase」（Phase 1/Phase 2/Phase 3/Phase 4A/Phase 4B）はスキル内部の実行フェーズを指す別概念。読者は混乱しやすいので、最終成果物（引き継ぎ書）では「Phase」ではなく「フェーズ1〜6」のみを使う。

---

## 鉄則：「API取得結果 ≠ 実運用」必ずユーザーに確認する

MFの各種マスタ API（`getDepartments`・`getConnectedAccounts`・`getAccounts`・`getSubAccounts`・`getTaxes`・`getTradePartners`等）で取得した結果は **「MFに登録されている内容」** であって **「実際に運用されている内容」ではない**。

頻繁に起きるズレ:
- 登録はあるが実運用では使っていない（形骸化）
- 過去は使ってたが今は一部に統合
- API の仕様上一部しか返らない（例: `getConnectedAccounts` は手動管理側のみ）
- MF画面と API が一致しない（登録漏れ・表示漏れ）

**対応ルール**:
1. API 取得後、**結果をそのままユーザーに提示**する（件数とリスト）
2. **「これは実運用と合っていますか？」** と確認する
3. 0件 と N件 で質問文面を使い分ける:
   - 0件 → 「0件で合ってますか？」
   - N件 → 「〇件取れました: [一覧]。現在も全部稼働中ですか？形骸化・統合はありますか？」
4. 実運用情報（形骸化・統合等）をメタデータとして保存し、以降の集計・対話で使う

これを守らないと、「登録部門3件」と思い込んで粒度を BS×補助×部門 にして対話したら、実はもう部門運用してなくて空振り、というような事故が起きる。

---

## 環境チェック（起動時に最初に実行）

### Python コマンドの特定

以下の順で試し、成功した方を `PYTHON` として記録する。
どちらも失敗したらユーザーに「Pythonをインストールしてください（https://www.python.org/）」と伝えて終了。

```
python3 --version
```
```
python --version
```

### pandas の確認・インストール

```
{PYTHON} -c "import pandas; print(pandas.__version__)"
```

失敗した場合（pandas 未インストール）:
```
{PYTHON} -m pip install --user pandas
```

それも失敗した場合（社内ポリシー等でpipがブロックされている）:
- 「pandas のインストールに失敗しました」とユーザーに伝える
- **フォールバック分析モード**（後述）で続行する

---


## 事前告知

環境チェック完了後、状態確認に入る前に必ず以下をユーザーに確認する：

> このスキルは仕訳データの**総合分析**を行います。通常のタスクと比較してトークンを多く消費します。
>
> 1. **総合分析レポート**（ビジネスモデル把握・決算前の確認・引き継ぎ資料作成などに）
> 2. **入力担当者向け引き継ぎシート**（記帳代行の8ステップに沿った引き継ぎ資料）
> 3. **両方**
> 4. **特定科目・部分的な分析のみをスキルなしで行う**（売上だけ・特定取引先だけなど）

**「1」の場合**：Phase 4A（総合分析レポート）を生成する。
**「2」の場合**：Phase 4B（入力担当者向け引き継ぎシート）を生成する。
**「3」の場合**：Phase 4A・4Bの両方を生成する。
**「4」の場合**：スキルを終了し、ユーザーの意図をあらためて聞いた上でMCP tools を使って直接対応する。

**引き継ぎシート（2 or 3）生成に必要な情報**: データ連携の状況＋明細一覧テキストは **Phase 2-1 で作業フォルダを作成した後に** 一括で依頼する（事前告知の時点では質問しない）。
フローの詳細は Phase 2-1c を参照。

---

## 起動時: 状態確認

### パターンA: CSVまたはJSONが直接渡された場合
→ Phase 1〜2をスキップして **Phase 3へ**。
ただし初めて渡されたCSVの場合は「マネーフォワードクラウド会計からのエクスポートデータですか？」と確認する。

### パターンB: カレントディレクトリに既存の作業フォルダがある場合

カレント直下のサブフォルダに `.mfc_token.json` または `journals_FY*.json` があるか確認（クロスプラットフォーム対応）:

```
{PYTHON} -c "import os, glob; dirs=[d for d in os.listdir('.') if os.path.isdir(d) and (os.path.exists(os.path.join(d,'.mfc_token.json')) or glob.glob(os.path.join(d,'journals_FY*.json')))]; print('\n'.join(dirs))"
```

見つかった場合は「`{code}_{name}/` のデータが見つかりました。このデータで分析しますか？」とユーザーに確認する。
- Yes → `journals_FY*.json` があれば **Phase 3へ**。alpha版の `.mfc_token.json` だけがある場合はトークンの有効期限を確認し、有効なら **Phase 2-3へ**、期限切れなら **Phase 1へ**
- No → **Phase 1へ**（別の事業者として新規取得）

### パターンC: 何もない場合
→ **Phase 1（認証）から開始**

---

## Phase 1: 認証

Codexでは **beta版を優先** する。beta版で認証できない、または複数法人を同時に保持したい場合だけ alpha版を使う。

### beta版（推奨）

1. `mf-official-beta` の `authenticate` を呼び出す
2. 認証URLが生成されたら、ユーザーにブラウザで開いて事業者を選択・許可してもらう
3. localhostコールバックまたは `complete_authentication` フォールバックで認証を完了する
4. 認証完了後は `mf-official-beta` の `mfc_ca_currentOffice` / `mfc_ca_getJournals` 等を使う
5. beta版では `access_token` をユーザーに貼らせたり、手動で `.mfc_token.json` に保存したりしない。トークンはリモートMCP側に任せる

### alpha版（必要時のみ）

トークンはまだ保存しない。メモリ上に持つだけ。

1. `mf-official-alpha` の `mfc_ca_authorize` でURLを生成しユーザーに提示
2. ユーザーがURLにアクセスし、認証後に表示される値を貼り付けてもらう
   **⚠ この貼り付けられた値は「認証コード」であり、「アクセストークン」ではない。**
   そのまま使用せず、必ず次のステップで exchange に渡すこと。
3. `mf-official-alpha` の `mfc_ca_exchange` に認証コードを渡してアクセストークンを取得する
   → `access_token` と有効期限（`expires_in: 3600秒`）をメモリに保持

---

## Phase 2: 事業所情報取得 & 仕訳ダウンロード

### 2-1. 事業所情報取得 & 作業フォルダ作成

選択したサーバー（通常は `mf-official-beta`）の `mfc_ca_currentOffice` を呼び出す。

**作業フォルダ名**: `{code}_{name}/`
- スペース → `_`、スラッシュ・特殊文字は除去
- 例: `1234-5678_株式会社サンプル/`

```
{PYTHON} -c "import os; os.makedirs('{code}_{name}', exist_ok=True)"
```

**alpha版でアクセストークンが明示的に返っている場合のみ、トークンをここで保存**:
```json
// {code}_{name}/.mfc_token.json
{
  "access_token": "...",
  "expires_at": "（現在時刻 + 3500秒のISO 8601）"
}
```

beta版ではトークンを保存しない。作業フォルダの再利用判定は `journals_FY{fiscal_year}.json` 等の分析データを優先する。

**対象期の特定**（デフォルト: 前期）:
- `accounting_periods[0]` = 当期、`accounting_periods[1]` = 前期
- `start_date`, `end_date`, `fiscal_year` を記録する

### 2-1b. データ連携状況の取得（手動管理側のみ・API実測）

`mfc_ca_getConnectedAccounts` を呼び出す。

**重要な API 仕様（OpenAPIに明記）**:
> 連携サービスを取得します。**明細を手動管理する連携サービスのみが返却されます。**

つまり:
- ✅ 返る: 手動CSVインポート口座、現金出納帳（`id` と `name` のみ）
- ❌ 返らない: 銀行・カード・電子マネー等の **自動取得連携サービス**
- ❌ 返らない: 残高・最終更新日・未仕訳件数等のステータス
- ❌ 返らない: 取引明細（明細取得APIは存在しない）

取得結果は `{code}_{name}/.connected_accounts_manual.json` に保存。自動取得側は次の 2-1c でユーザーから聞く。

### 2-1b-2. 部門マスタの取得（粒度決定用）

`mfc_ca_getDepartments` を呼び出して部門マスタを取得する。

**目的**: 入力ソースの粒度（BS×補助 か BS×補助×部門 か）を **Phase 3 を待たずに早期決定** するため。

**必ず意識すべき鉄則: API結果 ≠ 実運用**

API で取れた部門マスタは「MFに登録されている部門」であって、「実際に仕訳で運用している部門」ではない。
以下の5パターンがあり、**API 取得結果だけで粒度を判断してはいけない**。

| # | APIの結果 | 実運用 | 対応 |
|---|---|---|---|
| 1 | 0件 | 部門運用なし | 粒度は BS×補助 で確定 |
| 2 | N件 | N件全部を現在も運用中 | 粒度は BS×補助×部門 |
| 3 | N件 | **設定はあるが形骸化（付与していない）** | 粒度は BS×補助、部門情報は参考扱い |
| 4 | N件 | **過去は使ってたが今は1部門に統合** | 粒度は BS×補助、現在稼働部門だけ記録 |
| 5 | N件 | API 結果と MFの画面が不一致 | 画面スクショで突合して確認 |

**ユーザーへの確認の仕方（結果に応じて分岐）**:

```
【APIが空（0件）の場合】
部門マスタをAPIで取得しました。結果: 0件

これで合っていますか？
- 合っている（部門マスタに登録ゼロ）
- 違う（MF画面上には部門があるが取れていない）

【APIがN件ある場合】
部門マスタをAPIで取得しました。結果: N件
- 営業部
- 管理部
- 製造部

これは現在の実運用と合っていますか？以下のどれに該当しますか？
- (A) 全部現在も稼働中で、仕訳に部門付与している
- (B) 登録はあるが実運用では使っていない（形骸化）
- (C) 過去は使ってたが今は1部門（例: 本社）に統合
- (D) 一部の部門だけ稼働中
- (E) MF画面と一致しない（登録漏れ等）
```

ユーザー確認後、`{code}_{name}/.departments.json` に **APIの結果 + 実運用の判定** を保存。
実運用情報は Phase 3 の 2-11 部門分析（付与率）とも照合する。

### 2-1c. 引き継ぎシート（2 or 3）専用: データ連携補完＆明細一覧テキスト依頼

引き継ぎシート生成時のみ実行。総合分析レポートのみ（選択肢1）ならスキップ。

**手順**:

1. **作業フォルダ内に `追加資料/` サブフォルダを作成し、Finderで開く**（macOSの場合）:

   ```
   {PYTHON} -c "import os; os.makedirs('{code}_{name}/追加資料', exist_ok=True)"
   open {code}_{name}/追加資料
   ```

   Windows/Linuxの場合はフォルダパスをユーザーに伝えるだけでOK。

2. **ユーザーへ一括依頼**（以下の文面を提示）:

   > 引き継ぎ書の精度を上げるため、以下を `追加資料/` フォルダ（Finder で開いています）に入れてください。
   >
   > **① 登録済み一覧画面のスクリーンショット**（必須）
   > MF > データ連携 > 登録済み一覧 の画面全体を1枚撮影してください。
   > → 手動管理（現金出納帳・CSV）・自動取得（銀行・カード・電子マネー）両方が1画面で把握できます。
   >
   > **② 各サービスの明細一覧テキスト**（任意・推奨）
   > ①の画面で各サービスの「**明細一覧**」列の「**閲覧**」をクリックし、以下の手順でテキスト化してください。
   > サービスごとに別ファイルで保存します。
   >
   > 【取得手順】
   > 1. 「明細一覧」列の「閲覧」をクリック
   > 2. Cmd+A（Mac）/ Ctrl+A（Windows）で画面全選択 → コピー
   > 3. メモ帳等に貼付 → `追加資料/` フォルダに保存
   >
   > 【対象】手動管理・自動取得 **どちらも対象**（多いほど精度UP）
   > 【ファイル名】サービス名がわかれば何でもOK（例: `現金出納帳.txt`, `【法人】◯◯銀行.txt`, `代表_〇〇カード.txt`）
   > 【期間】1〜2ヶ月分で十分
   >
   > 全部保存したら「入れました」と返信してください。
   > ※ 画面のナビゲーション等が含まれていても、パーサーが明細部分のみを自動抽出します。

3. **ユーザー返信後の処理**:

   **a. スクショの読み取り**
   - Claudeがスクショを読み取り、以下を抽出:
     - 手動管理テーブル: サービス名一覧
     - 自動取得テーブル: サービス名一覧＋残高＋最終取得日時＋未仕訳件数
   - 抽出結果を `{code}_{name}/.connected_accounts_all.json` に保存

   **b. API結果とのクロスチェック（抜け漏れ防止）**
   - Phase 2-1b で取得した `.connected_accounts_manual.json`（API）と、スクショの手動管理テーブルを突合
   - **完全一致しない場合は警告**:
     - API にあるがスクショにないサービス → ユーザーに「スクショに映ってない」と確認
     - スクショにあるが API にないサービス → スキルのAPI仕様認識が古い可能性、ユーザーに確認
   - 一致する場合のみ次に進む

   **c. 明細一覧テキストの処理**
   - `{code}_{name}/追加資料/` 内のテキストファイルを `ls`
   - 各ファイルを `parse_meisai_list.py` でパース（1行/3行形式は自動判別）
   - サービス名（ファイル名）と a. の一覧を突合して、**貼り忘れ**があればユーザーに確認
   - テキストがない場合は Step 9 をスキップし、Step 1-8 のみで引き継ぎ書を生成

### 2-1d. 連携サービス名と補助科目のマッチング率検証（二重記帳防止の前提保証）

**目的**: 手順5の「16カテゴリ排他」は**補助科目名と連携サービス名の文字列マッチング**に依存する。補助科目がユーザーによってリネームされていると「自動取得連携なのに手入力判定」になり、二重記帳防止の前提が崩れる。Phase 3 の前に事前検出する。

**手順**:
```python
# 仕訳データの補助科目一覧を集める（Phase 3 の前、ファイルからjournals JSONを読む時点で可）
subs = set()
for j in journals:
    for b in j.get('branches', []):
        for side in ['debitor', 'creditor']:
            sd = b.get(side) or {}
            s = sd.get('sub_account_name') or ''
            if s: subs.add(s)

# 連携サービス名
with open(f'{code}_{name}/.connected_accounts_all.json') as f:
    ca = json.load(f)
auto_names = {s['name'] for s in ca.get('auto_fetch', [])}
manual_names = {s['name'] for s in ca.get('manual_managed', [])}
all_service_names = auto_names | manual_names

# マッチング検証
matched = subs & all_service_names
unmatched_services = all_service_names - subs  # 連携登録されているのに補助科目にない → リネーム疑い
suspicious_subs = set()  # 銀行名・カード名を含むが連携名と一致しない補助科目
keywords = ['銀行', 'カード', 'GMO', 'Suica', 'PASMO', '電子マネー']
for s in subs - all_service_names:
    if any(kw in s for kw in keywords):
        suspicious_subs.add(s)

print(f"連携サービス: {len(all_service_names)} / 補助科目とマッチ: {len(matched)}")
if unmatched_services:
    print(f"⚠ 連携登録あるが補助科目に見当たらない（{len(unmatched_services)}件）: {unmatched_services}")
if suspicious_subs:
    print(f"⚠ 銀行/カード系だが連携名と一致しない補助科目（{len(suspicious_subs)}件）: {suspicious_subs}")
```

**ユーザーへ確認**（不一致が検出されたら）:
```
以下の連携サービス名と補助科目が一致しません。リネームしていますか？

| 連携サービス名 | 補助科目（候補） |
|---|---|
| 【法人】〇〇銀行 | 本社口座（リネーム後） |
| △△カード | △△カードメイン（リネーム後） |

- リネームしている → 別名として登録（以降 `auto_services` に補助科目名も追加して判定）
- 別サービス → 連携サービス側に漏れがある可能性。要調査
```

マッチング結果は `{code}_{name}/.service_alias_map.json` に保存し、手順5の `classify_route()` 判定で `auto_services` / `manual_services` の別名リストとして使う。

### 2-2. キャッシュ確認

`{code}_{name}/journals_FY{fiscal_year}.json` が存在すれば **Phase 3へスキップ**。

### 2-3. 全件取得

選択したサーバー（通常は `mf-official-beta`）の `mfc_ca_getJournals` を **per_page=10000** で呼び出す:

```
per_page=10000, start_date=..., end_date=..., page=1
```

- 10,000件以下（大半の法人）は **1回で全件取得完了**。レスポンスは自動でファイルに保存される
- 10,000件超の場合のみ page=2 で追加取得し、merge_journals.py で結合

### 2-4. JSON保存

1ページで全件取得できた場合: 自動保存されたファイルをそのまま `{code}_{name}/journals_FY{fiscal_year}.json` としてコピー。

複数ページの場合:
```
{PYTHON} <skill_dir>/scripts/merge_journals.py \
    <tool_result_p1> <tool_result_p2> ... \
    {code}_{name}/journals_FY{fiscal_year}.json
```

### 2-5. 経理方式・課税方式の取得（getTermSettings 一発）

仕訳データの金額補正に必要。`mfc_ca_getTermSettings` を1回呼ぶだけで、税込/税抜・簡易/本則・都道府県・端数処理がまとめて取れる。

```
mfc_ca_getTermSettings
```

レスポンス例:
```json
{
  "term_settings": [
    {
      "accounting_method": "TAX_INCLUDED",    // 税込経理
      "tax_method": "SIMPLE",                 // 簡易課税
      "business_types": ["OTHER"],            // 業種区分（簡易課税時）
      "prefecture": "鹿児島県",
      "purchases_rounding_method": "ROUND_DOWN",
      "sales_rounding_method": "ROUND_DOWN",
      "fiscal_year": 2025,
      "start_date": "2025-06-06",
      "end_date": "2026-05-31"
    }
  ]
}
```

**対象期のレコードを抽出して判定:**
- `accounting_method == "TAX_INCLUDED"` → **税込経理**（`is_tax_inclusive = True`）
- `accounting_method == "TAX_EXCLUDED"` → **税抜経理（内税）**（`is_tax_inclusive = False`）
- `accounting_method == "TAX_EXCLUDED_SEPARATE"`（推定）→ **税抜経理（別記）**

判定結果を `{code}_{name}/.tax_method.json` に保存する:

```json
{
  "is_tax_inclusive": true,
  "accounting_method": "TAX_INCLUDED",
  "tax_method": "SIMPLE",
  "business_types": ["OTHER"],
  "prefecture": "鹿児島県"
}
```

**なぜ必要か**:
MF APIの仕訳データは常に `value`（税抜本体）と `tax_value`（税額）に分かれている。
- 税抜経理: `value` のままでOK（税額は仮払/仮受消費税として別行で計上）
- 税込経理: `value + tax_value` が帳簿上の正しい金額（仮払/仮受消費税の行はない）

税込経理の会社で補正しないと、全金額が消費税分だけ過少になる。

**副次的に取れる情報の活用:**
- `tax_method`（SIMPLE / GENERAL / EXEMPT）→ 引き継ぎ書の「簡易課税 / 本則課税 / 免税」欄に自動記載
- `business_types`（簡易課税の業種区分）→ 売上高の補助科目設計（三種・四種 等）の解釈材料
- `prefecture`（都道府県）→ 償却資産税・事業税の管轄確認
- `purchases_rounding_method` / `sales_rounding_method`（端数処理）→ 消費税計算の妥当性確認

---

## Phase 3: 分析

### 3-1. データ読み込み

pandasが利用可能な場合（通常モード）:

```python
import sys
sys.path.insert(0, "<skill_dir>/scripts")
from load_journals import load_df, enrich_partners, build_transaction_view, apply_tax_inclusive

df = load_df("<data_path>")           # .json or .csv を自動判別（カラム名は統一済み）

# 税込経理の場合は金額を補正（Phase 2-5 の判定結果に基づく）
if is_tax_inclusive:
    df = apply_tax_inclusive(df)       # 借方金額・貸方金額に税額を加算

df = enrich_partners(df)              # 行ビュー: 実質取引先列を追加
txn_df = build_transaction_view(df)   # 取引ビュー: 取引No単位で集約
```

**2つのビュー（重要）**:
複合仕訳（給与・売上+消費税等）では1取引が複数行に分かれる。用途に応じて使い分ける:
- **行ビュー（df）**: BS科目の残高計算、口座別集計、部門×科目の対応、入力元分析
- **取引ビュー（txn_df）**: 売上先・仕入先の集計、取引回数カウント、定期取引パターン、複合仕訳テンプレート

取引ビューの主な列: `取引No`, `取引日`, `行数`, `借方主科目`, `貸方主科目`, `合計金額`, `実質取引先`, `取引先ソース`, `部���`, `摘要`, `entered_by`(JSONのみ)

**JSON入力時のみ使える追加列**:
`entered_by`（入力元）、`is_realized`（確定済み）、`借方税額`/`貸方税額`、`借方invoice_kind`/`貸方invoice_kind`

**entered_by の値についての重要な注意（MF公式API）**:
MF公式API（alpha版・beta版）では、自前MCPとは異なる `entered_by` 値が返る:
- `JOURNAL_TYPE_IMPORT` = **CSVインポート**（売上台帳等の一括投入）
- `JOURNAL_TYPE_NORMAL` = **手入力 + データ連携（口座連携）**。APIでは両者を区別できない
- `JOURNAL_TYPE_OPENING` = 開始残高
- `JOURNAL_TYPE_EXPENSE` = 経費精算

**`JOURNAL_TYPE_NORMAL` にはデータ連携（口座連携）の仕訳が含まれる。**
`JOURNAL_TYPE_BANK_IMPORT` や `JOURNAL_TYPE_CREDIT_CARD` は公式APIでは返ってこない。
入力元分析で「口座連携0件」と誤判定しないこと。データ連携の有無はMFの設定画面（データ連携 > 連携サービス）で確認する必要がある。

**実質取��先の特定ロジック**:
MFクラウド会計では「取引先」フィールドを運用していない会社が大半。実務では補助科目で取引先を管理する。
取引ビューでは取引No単位で全行をスキャンし、以下の優先順位で最も信頼性の高い取引先を1つ選ぶ:
1. 債権債務科目（売掛金・買掛金等）の補助科目
2. 取引先フィールド（どれか1行にでもあれば）
3. 費用/収益科目の補助科目（口座名・税金科目を除外）
4. 摘要からの抽出（補助科目辞書マッチ → 法人名正規表現）

---

### フォールバック分析モード（pandas 不使用時）

pandasのインストールが失敗した場合はこのモードで動作する。
Claudeが直接データを読み込んでコンテキスト内で分析を行う。

- **JSONの場合**: ファイルを読み込み `journals` 配列を直接解析する
- **CSVの場合**: Readツールでファイルを読み込む
- 件数が多い場合（500件超）: 「{N}件中先頭500件をサンプリングして分析します」とユーザーに伝える
- 集計はClaudeが推論で行うため、通常モードより精度が落ちる可能性があることを明記する
- 実質取引先の抽出・取引No単位の集約はClaudeが手動で適用する（補助科目→取引先→摘要の優先順位で判断、複合仕訳は取引No単位でまとめて解釈）

---

### 3-2. 集計セット（全部実行してから解釈する）

ユーザーの質問内容にかかわらず、以下を全部実行してから回答を組み立てる。
（全部やっても数秒で終わる。飛ばすと回答精度が落ちる。）

**重要: 2つのビューを使い分ける。**
- 取引先の集計・取引回数・定期パターン → **取引ビュー（txn_df）**
- BS残高・口座別・部門×科目・入力元 → **行ビュー（df）**

---

**2-1. 実質取引先の抽出精度確認（取引ビュー）**

最初に抽出精度を確認し、問題があれば後続の解釈で考慮する。

```python
filled = (txn_df['実質取引先'] != '').sum()
total = len(txn_df)
print(f"取引ビュー: {filled}/{total} 取引で取引先特定 ({filled/total*100:.1f}%)")
print(f"  うち複合仕訳: {(txn_df['行数'] > 1).sum()} 件")

print("\n取引先の特定元:")
print(txn_df[txn_df['実質取引先'] != '']['取引先ソース'].value_counts())
```

---

**2-2. 売上・収益の全体像（取引ビュー）**

```python
# 貸方主科目が売上系の取引を集計（複合仕訳でも1取引=1行で正確にカウント）
sales_keywords = ['売上', '収益', '収入']
sales_mask = txn_df['貸方主科目'].str.contains('|'.join(sales_keywords), na=False)
sales_txn = txn_df[sales_mask]

if not sales_txn.empty:
    for acct in sales_txn['貸方主科目'].unique():
        acct_sales = sales_txn[sales_txn['貸方主科目'] == acct]
        print(f"\n=== {acct}（取引ビュー）===")
        print(acct_sales.groupby(['実質取引先', '取引先ソース'])['合計金額']
              .agg(['sum', 'count']).sort_values('sum', ascending=False))
```

---

**2-3. 売掛金の発生と回収**

```python
urikake_hatsu = df[df['借方勘定科目'] == '売掛金']
if not urikake_hatsu.empty:
    print("=== 売掛金 発生（借方）===")
    print(urikake_hatsu.groupby('借方補助科目')['借方金額'].agg(['sum', 'count']).sort_values('sum', ascending=False))

urikake_kaishu = df[df['貸方勘定科目'] == '売掛金']
if not urikake_kaishu.empty:
    print("\n=== 売掛金 回収（貸方）===")
    print(urikake_kaishu.groupby('貸方補助科目')['貸方金額'].agg(['sum', 'count']).sort_values('sum', ascending=False))
    print("\n=== 回収口座 ===")
    print(urikake_kaishu.groupby(['貸方補助科目', '借方勘定科目', '借方補助科目'])['貸方金額'].agg(['sum', 'count']))
```

---

**2-4. 仕入・外注・専門家報酬（取引ビュー）**

```python
for acct_name, label in [('仕入高', '仕入先'), ('業務委託料', '外注先'),
                          ('支払報酬', '専門家・顧問'), ('支払手数料', 'SaaS等')]:
    acct_txn = txn_df[txn_df['借方主科目'] == acct_name]
    if not acct_txn.empty:
        print(f"\n=== {label}（{acct_name}）===")
        print(acct_txn.groupby(['実質取引先', '取引先ソース', '部門'])['合計金額']
              .agg(['sum', 'count']).sort_values('sum', ascending=False))
        # 取引先不明の取引
        unknown = acct_txn[acct_txn['実質取引先'] == '']
        if not unknown.empty:
            print(f"\n  取引先不明（{len(unknown)}件、摘要を確認）:")
            print(unknown[['取引日', '合計金額', '摘要']].sort_values('取引日').to_string())
```

---

**2-5. 取引先がある支払い一覧（取引ビュー）**

```python
has_partner = txn_df[txn_df['実質取引先'] != '']
print(has_partner.groupby(['実質取引先', '借方主科目'])['合計金額']
      .agg(['sum', 'count']).sort_values('sum', ascending=False))
```

---

**2-6. 口座と資金の流れ**

```python
for acct in ['普通預金', '当座預金']:
    dr = df[df['借方勘定科目'] == acct]
    cr = df[df['貸方勘定科目'] == acct]
    if not dr.empty or not cr.empty:
        print(f"\n=== {acct} ===")
        if not dr.empty:
            print("入金口座:", dr['借方補助科目'].value_counts().to_string())
        if not cr.empty:
            print("出金口座:", cr['貸方補助科目'].value_counts().to_string())

# 資金移動勘定（口座間振替）
shikini = df[(df['借方勘定科目'] == '資金移動') | (df['貸方勘定科目'] == '資金移動')]
if not shikini.empty:
    print("\n=== 資金移動 ===")
    print(shikini[['取引日', '借方勘定科目', '借方補助科目', '貸方勘定科目', '貸方補助科目', '摘要']].to_string())
```

---

**2-6b. 現金・小口現金の入出金パターン（行ビュー）**

```python
for acct in ['現金', '小口現金']:
    dr = df[df['借方勘定科目'] == acct]
    cr = df[df['貸方勘定科目'] == acct]
    if not dr.empty or not cr.empty:
        print(f"\n=== {acct} ===")
        if not dr.empty:
            print(f"入金: {len(dr)}件, 合計{dr['借方金額'].sum():,.0f}円")
            print(dr.groupby('貸方勘定科目')['借方金額'].agg(['count', 'sum']).sort_values('sum', ascending=False))
        if not cr.empty:
            print(f"\n出金: {len(cr)}件, 合計{cr['貸方金額'].sum():,.0f}円")
            print(cr.groupby('借方勘定科目')['貸方金額'].agg(['count', 'sum']).sort_values('sum', ascending=False))
```

---

**2-6c. BS科目の期末残高算出（行ビュー）**

```python
# BS科目の残高 = 借方合計 - 貸方合計（資産科目）/ 貸方合計 - 借方合計（負債・純資産科目）
bs_accounts = set()
for col in ['借方勘定科目', '貸方勘定科目']:
    bs_accounts |= set(df[col].unique())

# 資産系キーワード
asset_keywords = ['現金', '預金', '売掛', '未収', '前払', '立替', '仮払', '棚卸', '商品',
                  '製品', '原材料', '仕掛', '貸付', '有価証券', '建物', '車両', '工具',
                  '土地', '機械', 'ソフトウェア', '敷金', '保証金', '投資', '固定資産']
liability_keywords = ['買掛', '未払', '前受', '仮受', '預り', '借入', '社債', '引当',
                      '資本', '利益剰余', '繰越']

print("=== 主要BS科目の残高 ===")
for acct in sorted(bs_accounts):
    dr_sum = df[df['借方勘定科目'] == acct]['借方金額'].sum()
    cr_sum = df[df['貸方勘定科目'] == acct]['貸方金額'].sum()
    if dr_sum == 0 and cr_sum == 0:
        continue
    is_asset = any(kw in acct for kw in asset_keywords)
    is_liability = any(kw in acct for kw in liability_keywords)
    if is_asset:
        balance = dr_sum - cr_sum
    elif is_liability:
        balance = cr_sum - dr_sum
    else:
        balance = dr_sum - cr_sum  # 不明な場合は資産扱い
    if abs(balance) >= 1000:  # 1,000円以上の残高のみ表示
        side_label = '(資産)' if is_asset else '(負債等)' if is_liability else '(?)'
        print(f"  {acct} {side_label}: {balance:>15,.0f}円")
```

---

**2-6d. 回収・支払サイト推定（行ビュー + 取引ビュー）**

```python
# 売掛金の発生月と回収月を突合して回収サイトを推定
urikake_dr = df[df['借方勘定科目'] == '売掛金']  # 発生
urikake_cr = df[df['貸方勘定科目'] == '売掛金']  # 回収

if not urikake_dr.empty and not urikake_cr.empty:
    print("=== 売掛金 回収サイト推定 ===")
    for sub in urikake_dr['借方補助科目'].unique():
        if not sub:
            continue
        dr_months = urikake_dr[urikake_dr['借方補助科目'] == sub]['取引日'].dt.to_period('M')
        cr_months = urikake_cr[urikake_cr['貸方補助科目'] == sub]['取引日'].dt.to_period('M')
        if dr_months.empty or cr_months.empty:
            continue
        # 発生月と回収月のペアリング（近い月同士を対応付け）
        dr_list = sorted(dr_months.unique())
        cr_list = sorted(cr_months.unique())
        diffs = []
        for cm in cr_list:
            # この回収月に最も近い（かつ前の）発生月を探す
            candidates = [dm for dm in dr_list if dm <= cm]
            if candidates:
                diff = (cm - candidates[-1]).n  # 月数差
                diffs.append(diff)
        if diffs:
            avg_site = sum(diffs) / len(diffs)
            print(f"  {sub}: 平均約{avg_site:.1f}ヶ月（{len(diffs)}件の回収から推定）")

# 買掛金の支払サイトも同様に推定
kaikake_dr = df[df['借方勘定科目'] == '買掛金']  # 支払
kaikake_cr = df[df['貸方勘定科目'] == '買掛金']  # 発生

if not kaikake_cr.empty and not kaikake_dr.empty:
    print("\n=== 買掛金 支払サイト推定 ===")
    for sub in kaikake_cr['貸方補助科目'].unique():
        if not sub:
            continue
        cr_months = kaikake_cr[kaikake_cr['貸方補助科目'] == sub]['取引日'].dt.to_period('M')
        dr_months = kaikake_dr[kaikake_dr['借方補助科目'] == sub]['取引日'].dt.to_period('M')
        if cr_months.empty or dr_months.empty:
            continue
        cr_list = sorted(cr_months.unique())
        dr_list = sorted(dr_months.unique())
        diffs = []
        for pm in dr_list:
            candidates = [cm for cm in cr_list if cm <= pm]
            if candidates:
                diff = (pm - candidates[-1]).n
                diffs.append(diff)
        if diffs:
            avg_site = sum(diffs) / len(diffs)
            print(f"  {sub}: 平均約{avg_site:.1f}ヶ月（{len(diffs)}件の支払から推定）")
```

---

**2-6e. 給与の複合仕訳テンプレート再現（行ビュー + 取引ビュー）**

```python
# 取引ビューで給与系取引を特定し、行ビューに戻って全行展開
kyuyo_keywords = ['給料', '給与', '賃金', '役員報酬', '賞与', '退職']
kyuyo_txn = txn_df[txn_df['借方主科目'].str.contains('|'.join(kyuyo_keywords), na=False)]

if not kyuyo_txn.empty:
    # 代表的な1件（最新の給与仕訳）の全行を表示
    sample_no = kyuyo_txn.sort_values('取引日', ascending=False)['取引No'].iloc[0]
    sample = df[df['取引No'] == sample_no]
    print(f"=== 給与仕訳テンプレート（取引No.{sample_no}）===")
    print(sample[['借方勘定科目', '借方補助科目', '借方部門', '借方金額',
                  '貸方勘定科目', '貸方補助科目', '貸方部門', '貸方金額', '摘要']].to_string())

    # 給与仕訳のパターンが複数あるか確認（複合仕訳の行数が異なるもの）
    kyuyo_patterns = kyuyo_txn.groupby('行数').size()
    if len(kyuyo_patterns) > 1:
        print(f"\n⚠ 給与仕訳のパターンが複数あります（行数別: {kyuyo_patterns.to_dict()}）")
        # 行数が異なるパターンごとにサンプルを1件ずつ表示
        for n_lines in kyuyo_patterns.index:
            if n_lines != sample.shape[0]:  # 最初に表示したものと異なるパターン
                alt_no = kyuyo_txn[kyuyo_txn['行数'] == n_lines].sort_values('取引日', ascending=False)['取引No'].iloc[0]
                alt = df[df['取引No'] == alt_no]
                print(f"\n--- パターン2（{n_lines}行、取引No.{alt_no}）---")
                print(alt[['借方勘定科目', '借方補助科目', '借方金額',
                           '貸方勘定科目', '貸方補助科目', '貸方金額']].to_string())
                break  # 2パターン目まで
```

---

**2-7. 中間勘定・特殊科目の用途確認**

```python
special_accts = ['マネフォ未払金', '前受金', '仮受金', '立替金', '未払金', '未払費用',
                 '仮払金', '前払金', '前払費用']
for acct in special_accts:
    mask = (df['借方勘定科目'] == acct) | (df['貸方勘定科目'] == acct)
    if mask.any():
        sub = df[mask]
        print(f"\n=== {acct}（{mask.sum()}件）===")
        dr = sub[sub['借方勘定科目'] == acct]
        cr = sub[sub['貸方勘定科目'] == acct]
        if not dr.empty:
            print("借方（発生）パターン:")
            print(dr.groupby(['貸方勘定科目', '貸方_実質取引先']).size().sort_values(ascending=False).head(10))
        if not cr.empty:
            print("貸方（消込）パターン:")
            print(cr.groupby(['借方勘定科目', '借方_実質取引先']).size().sort_values(ascending=False).head(10))
```

---

**2-8. 入力元分析（JSONのみ）**

**注意**: MF公式APIでは `JOURNAL_TYPE_NORMAL`（= 手入力/データ連携）に口座連携の仕訳が含まれる。
APIだけでは手入力とデータ連携を区別できない。データ連携の有無は事前告知で確認済みの情報を使う。

```python
if 'entered_by' in df.columns:
    print("=== 入力元別 件数・金額 ===")
    print(df.groupby('entered_by')['借方金額'].agg(['count', 'sum']).sort_values('count', ascending=False))

    print("\n=== 入力元別 x 借方勘定科目 ===")
    print(df.groupby(['entered_by', '借方勘定科目']).size().unstack('entered_by', fill_value=0))

    # JOURNAL_TYPE_NORMAL の中身を確認（手入力とデータ連携が混在している可能性）
    normal = df[df['entered_by'] == '手入力/データ連携']
    if not normal.empty:
        print(f"\n=== 手入力/データ連携（JOURNAL_TYPE_NORMAL）: {len(normal)}件 ===")
        print("※ この中にはデータ連携（口座連携）の仕訳が含まれている可能性あり")
        print(normal.groupby('借方勘定科目').size().sort_values(ascending=False).head(10).to_string())
```

---

**2-9. 給与・人件費**

給与は `entered_by` や `journal_type` ではなく **勘定科目名** で検出する。

```python
kyuyo_keywords = ['給料', '給与', '賃金', '役員報酬', '賞与', '退職']
kyuyo_mask = df['借方勘定科目'].str.contains('|'.join(kyuyo_keywords), na=False)
kyuyo = df[kyuyo_mask]

if not kyuyo.empty:
    print("=== 給与系科目一覧 ===")
    print(kyuyo['借方勘定科目'].value_counts())

    print("\n=== 月別給与合計 ===")
    kyuyo_copy = kyuyo.copy()
    kyuyo_copy['月'] = kyuyo_copy['取引日'].dt.to_period('M')
    print(kyuyo_copy.groupby(['借方勘定科目', '月'])['借方金額'].sum().unstack('月').fillna(0).to_string())

    months = kyuyo['取引日'].dt.to_period('M').nunique()
    print(f"\n=== 年間合計: {kyuyo['借方金額'].sum():,.0f}円 ===")
    if months > 0:
        print(f"月平均: {kyuyo['借方金額'].sum() / months:,.0f}円（{months}ヶ月）")

    print("\n=== 支払方法（貸方）===")
    print(kyuyo.groupby(['貸方勘定科目', '貸方補助科目'])['借方金額'].agg(['sum', 'count']))
```

**注意**: 給与は必ず勘定科目名で検出する。入力方法による判定は行わない。

---

**2-10. 定期取引パターン（取引ビュー）**

```python
txn_copy = txn_df.copy()
txn_copy['月'] = txn_copy['取引日'].dt.to_period('M')

# 給与系は取引ビューから除外（複合仕訳で1取引先に全額集約されてし��うため）
# 給与は集計2-9, 2-6eで行ビューから個別��分析する
kyuyo_kw = '給料|給与|賃金|役員報酬|賞与|退職'
txn_no_kyuyo = txn_copy[~txn_copy['借方主科目'].str.contains(kyuyo_kw, na=False)]

grp = (txn_no_kyuyo[txn_no_kyuyo['実質取引先'] != '']
       .groupby(['実質取引先', '借方主科目', '月'])['合計金額'].sum()
       .unstack('月'))
print("=== 定期取引パターン（取引ビュー、給与除く）===")
for idx, row in grp[grp.count(axis=1) >= 6].iterrows():
    vals = row.dropna()
    if len(vals) > 0 and vals.mean() > 0:
        spread = (vals.max() - vals.min()) / vals.mean() if vals.mean() > 0 else 999
        regularity = '定額' if spread < 0.05 else '概ね定額' if spread < 0.2 else '変動あり'
        # 貸方主科目（相手科���）も取得
        mask = (txn_df['実質取引先'] == idx[0]) & (txn_df['借方主科目'] == idx[1])
        cr = txn_df[mask].groupby(['貸方主科目','貸方主補助']).size().sort_values(ascending=False)
        cr_str = ' / '.join([f"{a}({b})" if b else a for (a,b), _ in cr.head(2).items()])
        print(f"  {idx}: {len(vals)}ヶ月, avg={vals.mean():,.0f}円, {regularity}, 貸方: {cr_str}")
```

---

**2-11. 部門分析**

```python
has_dept_dr = (df['借方部門'] != '').sum()
has_dept_cr = (df['貸方部門'] != '').sum()
print(f"部門あり仕訳: 借方 {has_dept_dr}/{len(df)} 件, 貸方 {has_dept_cr}/{len(df)} 件")

if has_dept_dr > 0 or has_dept_cr > 0:
    print("\n=== 借方部門一覧 ===")
    print(df[df['借方部門'] != ''].groupby('借方部門')['借方金額'].agg(['count', 'sum']).sort_values('sum', ascending=False))
    print("\n=== 貸方部門一覧 ===")
    print(df[df['貸方部門'] != ''].groupby('貸方部門')['貸方金額'].agg(['count', 'sum']).sort_values('sum', ascending=False))

    # 部門 x 勘定科目
    print("\n=== 部門 x 借方勘定科目 ===")
    dept_acct = df[df['借方部門'] != ''].groupby(['借方部門', '借方勘定科目'])['借方金額'].agg(['count', 'sum'])
    print(dept_acct.sort_values('sum', ascending=False).head(30))

    # 実質取引先 x 部門の対応（取引ビューで正確にカウント）
    print("\n=== 実質取引先 x 部門の対応（取引ビュー）===")
    partner_dept_txn = txn_df[(txn_df['実質取引先'] != '') & (txn_df['部門'] != '')]
    if not partner_dept_txn.empty:
        cross = partner_dept_txn.groupby(['実質取引先', '部門']).size().unstack(fill_value=0)
        multi_dept = cross[cross.astype(bool).sum(axis=1) > 1]
        if not multi_dept.empty:
            print("複数部門にまたがる取引先:")
            print(multi_dept)
        single_dept = cross[cross.astype(bool).sum(axis=1) == 1]
        if not single_dept.empty:
            print("\n固定部門の取引先:")
            for partner in single_dept.index:
                dept = single_dept.loc[partner].idxmax()
                print(f"  {partner} -> {dept}")

    # 科目別の部門付与状況
    print("\n=== 科目別の部門付与状況 ===")
    for acct in df['借方勘定科目'].unique():
        acct_df = df[df['借方勘定科目'] == acct]
        has = (acct_df['借方部門'] != '').sum()
        total = len(acct_df)
        if total >= 3:
            rate = has / total * 100
            if 0 < rate < 100:
                print(f"  {acct}: {has}/{total} ({rate:.0f}%) <- 部門の付与にムラあり")
            elif rate == 100:
                print(f"  {acct}: 全件部門あり")
```

---

**2-12. 入力担当者向け：入力元 x 勘定科目の対応マップ（JSONのみ）**

**注意**: MF公式APIでは `JOURNAL_TYPE_NORMAL`（手入力/データ連携）に口座連携の仕訳が含まれる。
「自動連携 vs 手入力」の正確な区分はAPIからは得られない。
事前告知で確認したデータ連携情報と合わせて解釈すること。

```python
if 'entered_by' in df.columns:
    print("=== 入力元 x 勘定科目の対応マップ ===")
    entry_map = df.groupby(['entered_by', '借方勘定科目']).agg(
        件数=('借方金額', 'count'),
        合計=('借方金額', 'sum')
    ).reset_index()
    print(entry_map.sort_values(['entered_by', '件数'], ascending=[True, False]).to_string(index=False))

    # インポート・経費精算・給与等の特殊入力元があれば別途表示
    special = entry_map[~entry_map['entered_by'].isin(['手入力/データ連携'])]
    if not special.empty:
        print("\n--- 特殊入力元（インポート・経費精算・給与等）---")
        print(special.sort_values('件数', ascending=False).to_string(index=False))
```

---

**2-13. 入力担当者向け：摘要パターン分析**

```python
print("=== 科目別 頻出摘要パターン ===")
for acct in df['借方勘定科目'].value_counts().head(15).index:
    acct_df = df[df['借方勘定科目'] == acct]
    remarks = acct_df['摘要'].value_counts().head(5)
    if not remarks.empty:
        print(f"\n{acct}:")
        for remark, cnt in remarks.items():
            if remark:
                print(f"  [{cnt}件] {remark}")
```

---

**2-14. 入力担当者向け：年次・不定期の大口取引（取引ビュー）**

```python
txn_copy2 = txn_df.copy()
txn_copy2['月'] = txn_copy2['取引日'].dt.to_period('M')

print("=== 年次・不定期の大口取引（取引ビュー）===")
for acct in txn_copy2['借方主科目'].unique():
    acct_df = txn_copy2[txn_copy2['借方主科目'] == acct]
    month_count = acct_df['月'].nunique()
    total_amt = acct_df['合計金額'].sum()
    if 1 <= month_count <= 3 and total_amt >= 100000:
        print(f"\n{acct}: {month_count}回/年, 合計{total_amt:,.0f}円")
        print(acct_df[['取引日', '実質取引先', '合計金額', '行数', '摘要']].to_string())
```

---

### 3-3. 摘要で実態を確認する

集計だけでは分からない「なぜその取引があるか」は摘要から読む。

特に以下のケースは摘要精読が必須：
- **実質取引先が空の仕訳** → 補助科目にも取引先にも摘要にも手がかりがない。全件確認
- **外国人名・海外地名が出てくる場合** → 顧客？現地スタッフ？業務委託先？を摘要から判断
- **金額が突出して大きい取引** → 何の取引か摘要・対応する全仕訳行を確認
- **聞いたことない勘定科目** → その科目の借方・貸方パターンと摘要を全件確認
- **同じ取引Noで複数行** → 複合仕訳なので取引No単位で全行セットで見る

```python
# ある取引Noの全行を見る（複合仕訳の全貌把握）
txn = df[df['取引No'] == 対象のNo]
print(txn[['借方勘定科目', '借方補助科目', '借方部門', '借方金額',
           '貸方勘定科目', '貸方補助科目', '貸方部門', '貸方金額', '摘要']].to_string())
```

---

## Phase 4A: 総合分析レポート生成・保存

事前告知で「1」または「3」が選ばれた場合に生成する。
以下の構成でマークダウンを生成し `{code}_{name}/analysis_FY{fiscal_year}.md` に保存する。

**文体の原則**：基本は箇条書き・テーブル。長い文章は避け、読み手がすぐ把握できる粒度で書く。

```markdown
# {事業者名} FY{year} 仕訳分析レポート
生成日: {today} / 対象期間: {start} 〜 {end} / 仕訳件数: {N}件

## 1. ビジネスモデル概況

**主事業**：〇〇業界向けに△△サービスを提供（1行で）

**事業区分**
- 国内事業：〇〇・△△向けに月次で提供
- 海外事業：〇〇向けの案件（摘要・通貨・取引先から判断）

**売上規模サマリー**（年度別テーブル）

**入力元内訳**（JSONのみ）
- entered_by別の件数を記載（JOURNAL_TYPE_NORMAL / PAYROLL / IMPORT / EXPENSE 等）
- ⚠️ JOURNAL_TYPE_NORMALにはデータ連携（口座連携）の仕訳が含まれる可能性あり。「手入力〇件」と断言しないこと
- データ連携の有無は事前告知で確認した情報を使う

## 2. 売上先まとめ

| 取引先（実質） | 特定元 | 累計売上 | 取引回数 | 部門 | 特記 |
|------------|------|--------|--------|-----|-----|
| 株式会社〇〇 | 売掛金補助 | 2,400万円 | 30回 | 営業1課 | 月次請求 |

（「特定元」列で、取引先名がどこから取得されたか明示する: 売掛金補助/売上補助/摘要 等）

## 3. 仕入・外注・専門家報酬まとめ

### 原価仕入先（仕入高）
| 取引先（実質） | 累計仕入 | 取引回数 | 支払方法 | 部門 | 特記 |
|------------|--------|--------|--------|-----|-----|

### 外注委託先（業務委託料）
| 取引先（実質） | 累計金額 | 取引回数 | 支払方法 | 部門 | 特記 |
|------------|--------|--------|--------|-----|-----|

### 専門家・顧問（支払報酬）
| 取引先（実質） | 累計金額 | 取引回数 | 特記 |
|------------|--------|--------|-----|

### SaaSツール・クラウドサービス（支払手数料）
| 取引先（実質） | 累計金額 | 取引回数 | 特記 |
|------------|--------|--------|-----|

## 4. 支払・回収サイト

### 売上先 回収サイト
| 取引先 | 売上計上 | 入金タイミング | 平均サイト | 特記 |
|------|--------|------------|--------|-----|

### 仕入先・外注先 支払サイト
| 取引先 | 計上タイミング | 支払タイミング | 平均サイト | 特記 |
|------|------------|------------|--------|-----|

### 給与・経費の支払サイト
（例：月末費用計上 → 翌月〇日に銀行振込）

## 5. 口座の役割分担

（各口座の入出金パターン、口座間資金移動の目的）

## 6. 中間勘定・特殊科目の用途

（中間勘定が1件でも存在する場合は必ず記載。他のセクションに埋めない。）

**〇〇勘定**
- 役割：
- 発生パターン：
- 消し込みパターン：
- 件数・金額規模：

## 7. 定期取引パターン

## 8. 給与・人件費

## 9. 部門分析

（部門設定がある場合のみ記載）

**部門一覧**
| 部門名 | 用途（推定） | 仕訳件数 | 年間金額 |
|-------|------------|---------|---------|

**部門付与ルールまとめ**
- 部門必須の科目: 売上高、仕入高、...
- 部門なしの科目（全社共通経費）: 支払利息、租税公課、...
- 取引先→部門の固定対応: 〇〇商事→営業1課、...
- 複数部門にまたがる取引先: △△物産（営業1課/営業2課）← 要確認
```

---

## Phase 4B: 入力担当者向け引き継ぎシート生成・保存

事前告知で「2」または「3」が選ばれた場合に生成する。
以下の構成でマークダウンを生成し `{code}_{name}/handover_FY{fiscal_year}.md` に保存する。

**文体の原則**：入力担当者が「明日からこれを見て記帳できる」ことを目指す。

**設計思想（最重要）**：
引き継ぎ書の中心は **BS科目**。PL科目は必ずいずれかのBS科目（現金・預金・売掛金・買掛金・未払金・預り金 等）とペアになるため、BS全科目について「どの証憑・どのソースから入力するか」を1対1で対応づければ、仕訳は漏れない構造になる。

**原則:**
- Step 4 = BS全科目の入力ソース一覧（これが引き継ぎ書の骨格）
- 月次入力フロー = Step 4 を上から順になぞる構造
- Step 2（証憑）は Step 4 のBS科目に対応づける

**鉄則：粒度を絶対に崩すな**

- **入力ソース = BS科目（補助科目）× 部門 × 発生/消込** の単位で1対1に対応する
  - 部門運用なし: `BS科目 × 補助科目 × 発生/消込`
  - 部門運用あり: `BS科目 × 補助科目 × 部門 × 発生/消込`
  - 補助科目がない BS科目は `BS科目 × 発生/消込`（+部門）
- **発生/消込で登録経路が異なるケースが多数ある**:
  - 売掛金/〇〇商事: 発生=手入力（請求書起票）、消込=データ連携（入金自動取得）
  - 買掛金/〇〇商会: 発生=手入力（請求書到着）、消込=データ連携（振込自動取得）
  - 未払金/カード: 発生=データ連携（カード自動取得）、消込=データ連携（引落自動取得）← 同じ経路
  - 未払費用/給与: 発生=MF給与連携、消込=データ連携（振込自動取得）
- **部門運用の有無は Phase 3 の 2-11 部門分析で確認する**（部門付与率 > 0 なら部門運用あり）
- カバー率検証もこの粒度で実施する
- **手順3のユーザー対話も同じ粒度で行う**
  - ❌ NG: 「銀行系」「カード系」「売上系」とまとめて聞く（粒度が崩れる）
  - ❌ NG: 「普通預金（GMO・鹿児島）」と複数補助をまとめて聞く
  - ✅ OK: 「普通預金/〇〇銀行」だけで1問、「普通預金/△△銀行」だけで1問
- 手順2で推定したBS×補助一覧を、手順3でそのまま順番に1つずつ聞く
- **粒度を崩すと、手順2の推定・手順3の対話・手順5のカバー率の3者が不整合になり、引き継ぎ書の信頼性が崩壊する**

**鉄則：1ターン1項目**

- ユーザーへの質問は **1ターンにつき1項目** だけ
- 複数項目を同時に聞くとユーザーの認知負荷が上がり、回答漏れ・雑な回答を招く
- 返信を受けたら次の項目に進む（順次）

**鉄則：証憑情報なしでは引き継ぎ書を書いてはいけない**

- 証憑（名称）が空欄のまま引き継ぎ書を出してはいけない。証憑なしの科目は「証憑なし」と明示的に記録する
- 新任者が「どこから何を見て入力すればいいか」分からなければ引き継ぎ書として機能しない
- 手順3の証憑部分を省略・短縮するくらいなら、その科目を「証憑情報未確認」として明記すること

**情報ソースの優先順位**:
1. 仕訳データ（Phase 3の集計結果）← 自動で取得可能
2. 証憑フォルダの構成（ユーザーがスクリーンショットやフォルダ一覧を提供した場合）
3. データ連携情報（Phase 2-1b + 2-1c で取得）:
   - 手動管理側: `getConnectedAccounts` API から取得済み（`.connected_accounts_manual.json`）
   - 自動取得側: ユーザーからの申告（`.connected_accounts_auto.json`）
   - 明細一覧テキスト: `追加資料/` 内のファイル（parse_meisai_list.py で解析）
4. ユーザーへの質問（上記で不足する場合のみ）

**証憑情報がある場合とない場合で品質が大きく変わる。**
証憑フォルダの構成がわかっている場合は、「証憑→仕訳の対応マップ」と「月次作業フロー」を
具体的に記載できる。わからない場合はチェックリスト形式で確認項目を提示する。

---

### Phase 4B の実行手順（BS科目ベースの対話型生成）

引き継ぎ書は **Step 4（BS科目別入力ソース一覧）** が骨格。以下の順序で対話的に確定させる。
機械推定で全部埋めず、**ユーザーとの対話で各BS科目の入力ソースを1件ずつ確定**させる。

#### 手順1. BS科目の洗い出し（補助科目別内訳まで必ず出す）

仕訳データから使われている全BS科目を抽出する（資産・負債・純資産）。
補助科目があるものは**必ず補助科目ごとに分解**する。

**各 BS科目 × 補助科目 について以下を必ず算出する（手順3に進む前に全部揃える）**:

| 項目 | 目的 |
|---|---|
| 借方・貸方の発生件数・金額 | 主要な流れを把握 |
| 相手科目TOP3（借方・貸方別） | 「どこから来てどこへ行くか」を自分で把握 |
| 月別発生月数 | 月次/不定期の判断 |
| 摘要頻出語TOP5（全角・半角両方） | 借入先・取引先・口座名等をユーザーに聞く前に特定 |
| 連携サービス名との紐付き | 銀行名・カード名の補助科目を `.connected_accounts_all.json` と突合 |

**重要**: この手順で出した**補助科目名・相手科目・摘要**で分かることは**絶対にユーザーに聞かない**。
例:
- 補助科目「〇〇カード一般」→ どのカードか補助科目名で明白
- 補助科目「〇〇公庫（XXX万円）」→ 借入先は補助科目名に書いてある
- 相手科目「普通預金/〇〇銀行」が常に対応 → 引落口座は分かる

分からないことだけ手順3でユーザーに聞く。

#### 手順2. 入力ソースの推定

各BS科目について、仕訳データ・Phase 2-1b/cで取得したデータ連携情報（手動管理側=API、自動取得側=ユーザー申告）をもとに **入力ソースを大分類で** 推定する。

**入力ソースの大分類（これ以上細かくしない。詳細は手順3の証憑で聞く）**:

| カテゴリ | 判断元 |
|---|---|
| **データ連携** | Phase 2-1b/c で銀行・カード・電子マネー等の自動連携サービスに紐付く補助科目 |
| **MF給与連携** | `entered_by == JOURNAL_TYPE_PAYROLL` が多い |
| **CSVインポート** | `entered_by == JOURNAL_TYPE_IMPORT` が多い |
| **外部ツール連携** | `entered_by == JOURNAL_TYPE_EXTERNAL` が多い |
| **経費精算** | `entered_by == JOURNAL_TYPE_EXPENSE` が多い |
| **手入力** | 上記に該当しない、または `entered_by == JOURNAL_TYPE_NORMAL` でデータ連携もない場合 |
| **不明** | 判断元なし → 手順3でユーザー確認必須 |

**重要**: 「月次請求書を見て手起票」「現金出納帳（手書き）を見て手入力」「個人立替精算書を見て手入力」等のサブカテゴリはすべて「**手入力**」の中の細かい違い。これは**証憑**（何を元データとして見たか）で区別されるため、**手順3で証憑として聞く**（ここで推定しない）。

#### 手順3. 【対話】入力ソース確認＋証憑深掘り（1ターン1科目・最重要）

**推定できた全BS×補助について、1つずつ「入力ソース」と「証憑」をまとめて対話確定させる。1科目=1ターン**で聞き、入力ソースと証憑は**同じターンに含める**（分けるとユーザー体験が悪化し、思考が途切れる）。

**手順3 の完了条件（全部✅になってから手順4へ）**:
- [ ] 全BS×補助について、入力ソース（大分類）がユーザー確認済み
- [ ] 全BS×補助について、証憑の名称が分かっている（保管場所・形式・頻度・担当者は不要）
- [ ] 「証憑なし」の科目はその旨が明示的に記録されている（空欄は不可）
- [ ] 返信が曖昧な項目は再質問して確定させた

**会計用語の取り扱い（最重要）：**
- 借貸の向きを絶対に間違えない：資産（借方残）の発生は借方、消込は貸方／負債（貸方残）は逆
  - 例: 売掛金は資産 → 発生=借方、消込=貸方
  - 例: 買掛金は負債 → 発生=貸方、消込=借方
- 誤った向きを書くとユーザーの信頼を失う

**ユーザー向け会話のルール：**
- 内部用語を見せない：「機械推定」「カバー率」「フェーズN」「手順N」「Step N」は NG
- 「機械推定」→「仕訳データから読み取ると」、「カバー率検証」→「月次の仕訳が漏れなく拾えるか確認」等に置換
- **専門用語はOK。ただし「造語」「曖昧な使い方」は禁止**
  - 専門用語は会計業務者であれば通じる（例: 仕訳・元帳・消込・試算表・補助科目・税区分・振替・売掛・買掛 等）
  - NGなのは Claudeが文脈で勝手に作った語・既存用語の意味不明な使い方
    - 悪例: 「振込明細」と私が書いた → 銀行業界では「振込人が受け取る控え」の意味で、入金側の記録に使うのは誤用
  - **迷ったら MF公式画面やMFサポートで使われている用語**を使う（MFに合わせる）
  - ユーザーが「◯◯ってなに？」と聞き返したら、それは**会話が止まる = スキルの失敗**。次から使わない

**手順3 の進め方（1ターン1組で順番に・部門差は先にまとめて確認）：**

手順2 で推定した **BS×補助×部門** のリストを、**上から1つずつ** ユーザーに確認する。一度に複数の組み合わせを聞くことは禁止。

**粒度の扱い（部門運用あり事業者）**:
- 対話の最小単位は **BS×補助×部門**
- ただし、同じ BS×補助 が複数部門にまたがる場合、**最初に「部門差があるか」を聞いて認知負荷を削減**:
  - 部門差なし → そのBS×補助全体として1ターンで確認
  - 部門差あり → 部門別に個別対話（N部門ならNターン）
- 部門運用なし事業者（`.departments.json` で確認）は単純に BS×補助 のループでOK

**冒頭（1ターン目）のみ、全体像を提示して同意を得る**:

```
これから各BS科目（補助科目・部門）について、1つずつ「入力ソース」と「証憑」を確認していきます。
仕訳データから推定した一覧はこちらです:

| # | BS科目 | 補助科目 | 部門 | 入力ソース（推定・発生/消込） | 判断元 |
|---|---|---|---|---|---|
| 1 | 普通預金 | 〇〇銀行 | 全部門共通 | 発生/消込ともデータ連携 | 連携サービス登録あり |
| 2 | 普通預金 | △△銀行 | 全部門共通 | 同上 | 同上 |
| 3 | 未払金 | ××カード | 営業部/管理部/製造部 で利用 | 発生=データ連携、消込=データ連携 | 同上（まず部門差の有無を確認） |
| ... | ... | ... | ... | ... | ... |

この順番で1つずつ確認させてください。まずは1番目から。
```

**2ターン目以降（個別確認）テンプレ — 入力ソース確認＋証憑深掘りを同じターンで**:

発生・消込の両方が起きる科目（売掛金・買掛金・未払金・未払費用・預り金・借入金 等）は**発生と消込の両方**を聞く。BS科目が片方向のみ（資本金の貸方発生のみ等）なら片方でOK。

**部門差確認ブロック（複数部門にまたがる補助科目の場合のみ）**:
```
【#/N】未払金 / 〇〇カード

この補助科目は 営業部・管理部・製造部 の3部門で仕訳が発生しています。
部門ごとに入力ソース・証憑は違いますか？
- 全部門同じ → 続けて登録経路＋証憑を1回で確認します
- 部門ごとに違う → 部門別に個別確認します（次ターン以降3回）
```

ユーザーが「全部門同じ」と回答したら、通常の1ターンテンプレで続行。
「部門ごとに違う」と回答したら、部門1→部門2→部門3 と順次個別対話。

```
【1/N】売掛金 / 〇〇商事

【仕訳の登録経路】2種類を個別に推定:

(a) 発生時（売上計上）: 手入力
  判断元: 借方発生7件、相手=売上高、entered_by=NORMAL、補助科目が取引先名

(b) 消込時（回収）: データ連携（自動取得）
  判断元: 貸方消込6件、相手=普通預金/〇〇銀行（自動取得連携サービス）

この推定で合っていますか？
- 両方OK: 「OK」
- 違う: (a)/(b) それぞれを以下のTOP3候補から選ぶか、自由記述で修正:
  よくある候補: 【1】データ連携（自動取得）/【2】データ連携（手動管理）/【16】手入力
  ※ その他の選択肢（給与連携・CSVインポート・家事按分・償却・開始残高 等、全16カテゴリ）は
     SKILL.md冒頭「仕訳の登録経路」を参照。該当する番号 or 自由記述で回答OK。

【証憑】証憑を使っていれば**名称だけ**教えてください（例: 紙の請求書・通帳・領収書・手書き出納帳・チャット指示）。なければ「なし」でOK
※ 保管場所・保管形式・見る頻度・担当者・特記事項は**聞かない**（ユーザーの認知負荷を下げるため。名称だけで Step 2・Step 4 に反映できる）

※ 回答例: 「OK。紙請求書」/「OK。証憑なし」/「(a)は2Bに修正。現金出納帳」等
```

**選択肢提示の原則**（毎回全16個並べない・認知負荷軽減）:
- **冒頭1ターン目**（全体像提示時）は全16カテゴリを一度だけ提示する
- **2ターン目以降の個別確認**ではTOP3候補のみ提示し、「その他は冒頭の用語定義表を参照」と案内
- ユーザーの自由記述での回答（「MFクラウド経費で」等）も受け付ける

返信を受けたら次の項目（2/N）に進む、という順次対話。

**Claude側の動作ルール（最重要）：**
- **1ターンにつき1科目のみ質問**（禁止: 複数科目をまとめて質問、「系」でグループ化）
- **入力ソース確認と証憑深掘りは同じターンで聞く**（別ターンに分けない）
- この段階で聞くのは **推定できた科目のみ**（推定できなかった科目は質問しない）
- ユーザー返信後、すぐ次の科目に進む。曖昧な返信は確認し直す
- **確定していない項目があれば、手順4に進まない**
- 推定できなかった科目（使われ方が不明瞭なもの）は **手順6で拾う**。ここでは聞かない

---

#### 手順4. 月次フロー生成（登録経路16カテゴリ ＋ 月次作業フェーズ）

**最重要原則：各仕訳は「登録経路16カテゴリ」のいずれか1つに排他的に分類される**（二重記帳の構造的防止）

引き継ぎ書は2軸で構成する。**両者は別概念**：
- **軸A: 登録経路（16カテゴリ）** … 仕訳がMFに入る経路。SKILL.md冒頭の「用語定義：仕訳の登録経路」の16カテゴリをそのまま使う。機械判定用。
- **軸B: 月次作業フェーズ（6）** … 担当者視点の作業タイミング。引き継ぎ書 Step 5 に記載。

---

### 軸A. 登録経路（16カテゴリ・機械判定用・排他）

SKILL.md冒頭で定義した16カテゴリを **そのまま流用**する（ここで再定義しない）:

1. データ連携（自動取得）
2. データ連携（手動管理）
3. MFクラウド給与連携
4. CSVインポート
5. MFクラウド経費連携
6. MFクラウド請求書連携
7. MFクラウド債務支払連携
8. STREAMED連携
9. モバイルアプリ
10. AI-OCR
11. デジタルインボイス
12. 外部API連携
13. 家事按分
14. 償却仕訳
15. 開始残高
16. 手入力

機械判定ルール:
- `entered_by == JOURNAL_TYPE_OPENING` → **15. 開始残高**
- `entered_by ∈ {PAYROLL, IMPORT, EXPENSE, BILLING, DEBT, STREAMED, MOBILE_APP, AI_OCR, E_INVOICE, EXTERNAL, HOME_DEVOTE, DEPRECIATION}` → それぞれ 3/4/5/6/7/8/9/10/11/12/13/14
- `entered_by == JOURNAL_TYPE_NORMAL`:
  - 借方 or 貸方の補助科目が **自動取得連携サービス** に紐づく → **1. データ連携（自動取得）**
  - 補助科目が **手動管理連携サービス** に紐づく → **2. データ連携（手動管理）**
  - 上記以外 → **16. 手入力**

### 軸B. 月次作業フェーズ（担当者視点・引き継ぎ書 Step 5 に記載）

作業タイミングで6フェーズに分割。各登録経路はフェーズに対応づけられる：

| フェーズ | 定義 | 対応する登録経路（16カテゴリから） |
|---|---|---|
| **フェーズ1**. データ連携の仕訳候補処理 | 画面のルーチン | 1. データ連携（自動取得） |
| **フェーズ2**. 月次補助元帳から手起票 | 売掛発生・買掛発生・現金出納帳・社保計上 等 | 2. データ連携（手動管理）、4. CSVインポート（月次分）、16. 手入力（月次定期分） |
| **フェーズ3**. 給与・社保（MF給与連携） | 月次の給与取込 | 3. MFクラウド給与連携（+ 関連する16. 手入力） |
| **フェーズ4**. 不定期の手起票 | 振替・中間勘定精算・都度取引 | 16. 手入力（不定期分） |
| **フェーズ5**. 年次・決算整理 | 決算整理仕訳 | 13. 家事按分、14. 償却仕訳、16. 手入力（年次分） |
| **フェーズ6**. 残高チェック | 起票なし | — |

※ その他の登録経路（5. 経費連携、6. 請求書連携、7. 債務支払連携、8. STREAMED、9. モバイルアプリ、10. AI-OCR、11. デジタルインボイス、12. 外部API連携）は**使っている場合のみ**、作業タイミングに応じてフェーズ1/3/4等に追加する。

**運用上の注意**:
- **自動生成系の登録経路（1, 3, 5〜14）の対象仕訳を手入力で先行入力すると二重記帳が発生する**
- 引き継ぎ書に明記: 「**自動生成されるはずの仕訳は連携の仕訳候補画面から登録する。連携前に手入力しない**」

#### 手順5. 登録経路排他性チェック（必須）

**この手順は「排他性（重複0）」をチェックするだけ**。カバー率としては意味を持たない（16カテゴリに catch-all である「16. 手入力」が含まれるため、カバー率は定義上常に100%になる）。真のカバー率検証は次の手順5.5 で行う。

軸A（登録経路16カテゴリ）で全仕訳を機械分類し、**各仕訳がちょうど1つに該当する**ことを保証する。

```python
def classify_route(journal_row, auto_services, manual_services):
    """各仕訳を登録経路16カテゴリのいずれかに分類。複数該当 or 非該当はエラー。"""
    eb = journal_row.get('entered_by', '')
    JT = 'JOURNAL_TYPE_'

    if eb == f'{JT}OPENING':       return '15. 開始残高'
    if eb == f'{JT}PAYROLL':       return '3. MFクラウド給与連携'
    if eb == f'{JT}IMPORT':        return '4. CSVインポート'
    if eb == f'{JT}EXPENSE':       return '5. MFクラウド経費連携'
    if eb == f'{JT}BILLING':       return '6. MFクラウド請求書連携'
    if eb == f'{JT}DEBT':          return '7. MFクラウド債務支払連携'
    if eb == f'{JT}STREAMED':      return '8. STREAMED連携'
    if eb == f'{JT}MOBILE_APP':    return '9. モバイルアプリ'
    if eb == f'{JT}AI_OCR':        return '10. AI-OCR'
    if eb == f'{JT}E_INVOICE':     return '11. デジタルインボイス'
    if eb == f'{JT}EXTERNAL':      return '12. 外部API連携'
    if eb == f'{JT}HOME_DEVOTE':   return '13. 家事按分'
    if eb == f'{JT}DEPRECIATION':  return '14. 償却仕訳'

    if eb == f'{JT}NORMAL':
        subs = journal_row['補助科目一覧']
        if any(s in auto_services for s in subs):
            return '1. データ連携（自動取得）'
        if any(s in manual_services for s in subs):
            return '2. データ連携（手動管理）'
        return '16. 手入力'

    return 'UNCLASSIFIED'  # エラー

# カバー率検証
from collections import Counter
classifications = [classify_route(j, auto_services, manual_services) for j in journals]
counts = Counter(classifications)
total = len(journals)
unclassified = counts.pop('UNCLASSIFIED', 0)
assert unclassified == 0, f"分類漏れ: {unclassified}件"
for cat, n in sorted(counts.items()):
    print(f"{cat}: {n}件 ({n/total*100:.1f}%)")
```

**必須チェック**（この手順は「排他性」のみ検証。カバー率の語は手順5.5でのみ使う）:
| チェック項目 | 合格基準 |
|---|---|
| 分類到達率 | 100%（全仕訳が16カテゴリのいずれかに該当・catch-all有りなので自明） |
| 排他性（重複0） | 0件（同じ仕訳が複数カテゴリに該当しない） |
| UNCLASSIFIED | 0件 |
| 「16. 手入力」の月次定期/不定期/年次 の内訳 | Python で月別発生回数・摘要キーワードから判定し、フェーズ2/4/5 に振り分け可能か確認 |

**失敗時の対応**:
- 分類漏れ → Step 4 のBS科目に漏れあり or 補助科目名と連携サービスのマッチング不備。手順1に戻る
- 判定ロジックの見直し（補助科目と連携サービスのマッチング失敗等）

**軸Bとのクロス検証**:
- 軸Aの16カテゴリを軸B（Step 5の6フェーズ）にマッピング（手順4の対応表参照）
- 16カテゴリが排他なら、フェーズ1〜5も排他（フェーズ6は起票なし）
- これにより **同じ仕訳が複数フェーズに現れることはない**（二重記帳が構造的に防がれる）
- ただし「16. 手入力」は**月次定期/不定期/年次** の3分岐が必要（Python で判定）

#### 手順5.5. 月次入力フロー網羅性検証（真のカバー率・必須）

**これが本当の意味での「カバー率検証」**。引き継ぎ書の**月次入力フロー（Step 5「毎月やる定期仕訳」セクション内のフェーズ1〜5）**に列挙したBS×補助×部門×発生/消込 の具体項目が、全仕訳を説明できるか判定する。

**分母・分子の定義**:
- 分母: **全仕訳件数**（開始仕訳は除外、`entered_by == JOURNAL_TYPE_OPENING`）
- 分子: **仕訳パターンが月次入力フローの具体項目にマッチする仕訳件数**

**「マッチする」とは**:
- 仕訳の **借方側 と 貸方側 の両方** について、それぞれのBS科目×補助×部門×発生/消込 ペアが月次入力フロー（Step 5）のフェーズ1〜5 の具体項目として **明示されている**こと
- PL科目は相方のBS科目でカバーされるのでOK
- PL-PL振替の場合は Step 5 フェーズ5 に**明示的にパターン記載**されていること

**実装**:

```python
# 仕訳パターンの集計（部門ありの場合 部門も含める）
patterns = df.groupby([
    '借方勘定科目','借方補助科目','借方部門',
    '貸方勘定科目','貸方補助科目','貸方部門',
]).size().reset_index(name='件数')

# 月次入力フロー（Step 5）の具体項目リスト（対話で積み上げたもの）
step5_items = load_step5_items()  # 構造: list of {bs_account, sub, dept, side(発生/消込), phase}

def is_covered(pattern, step5_items):
    """借方 BS × 貸方 BS 両方が step5_items でカバーされているか"""
    dr_bs = (pattern['借方勘定科目'], pattern['借方補助科目'], pattern['借方部門'])
    cr_bs = (pattern['貸方勘定科目'], pattern['貸方補助科目'], pattern['貸方部門'])
    # 資産の借方＝発生、貸方＝消込 等、側 を判定
    dr_side = '発生' if is_asset(pattern['借方勘定科目']) else '消込'
    cr_side = '消込' if is_asset(pattern['貸方勘定科目']) else '発生'
    dr_covered = any(matches(item, dr_bs, dr_side) for item in step5_items)
    cr_covered = any(matches(item, cr_bs, cr_side) for item in step5_items)
    return dr_covered and cr_covered

# カバー率計算
covered = 0
uncovered_patterns = []
for _, row in patterns.iterrows():
    if is_covered(row, step5_items):
        covered += row['件数']
    else:
        uncovered_patterns.append(row)

total = len(df[df['entered_by'] != 'JOURNAL_TYPE_OPENING'])
coverage = covered / total * 100
print(f"カバー率: {coverage:.1f}% ({covered}/{total}件)")
print(f"漏れパターン: {len(uncovered_patterns)}件")
```

**合格基準**:
| カバー率 | 判定 |
|---|---|
| ≥99% | OK、引き継ぎ書完成へ |
| 95〜99% | 漏れパターンを手順6でユーザーに確認・Step 5 に追加 |
| <95% | Step 4 の不完全 → 手順1に戻って再抽出・手順3の対話不足を補完 |

**失敗時の対応**:
- 漏れパターンを全部列挙し、**手順6（漏れパターン対話）**でユーザーに「毎月/不定期/年次/振替/スキップ」を分類させて Step 5 に追加

---

#### 手順6. 【2回目の対話】漏れパターンの分類と運用確認

手順5のカバー率検証で漏れたパターンについて、ユーザーに分類と運用を尋ねる。
**ここで手順3で聞かなかった科目（現金・仮払金・立替金・役員借入金等）もまとめて確認される**。

**ユーザー向け会話のルール（再掲）：**
- 内部用語（「カバー率」「フェーズN」「スキップ」等）を質問文には出さない
- 代わりに：「月次で繰り返すもの / たまに発生するもの / 年1回 / 振替 / このシートには書かない」のような自然な言葉で選択肢を提示

**質問テンプレ：**

```
以下の仕訳パターンが未分類です。それぞれ「毎月」「不定期」「年次」「振替」「スキップ」
のどれに分類すべきか教えてください。

| # | 仕訳パターン | 発生状況 | 推奨分類 |
|---|---|---|---|
| 1 | 借) 接待交際費 / 貸) 立替金 | 9ヶ月中7ヶ月 | 毎月 |
| 2 | 借) 未払金 / 貸) 雑収入 | 9ヶ月で1件 | 不定期 |
| 3 | 借) 立替金 / 貸) 接待交際費 | 9ヶ月で1件 | 不定期 |

分類の選択肢: 毎月 / 不定期 / 年次 / 振替 / スキップ

---

**回答方法：**

**パターンA：全部推奨通りで問題ない場合**
返信は「OK」とだけ入力してください。

**パターンB：推奨を変更したい行がある場合**

例1：
「#2 はカードのポイント還元。たまたま今回1件だけど実は月1くらい出るはず」
とあなたが判断するなら、返信は「2番 毎月」とお送りください。

例2：
「#3 は社員が個人立替した経費を翌月現金精算する業務。実は月1〜2回ある」
とあなたが判断するなら、返信は「3番 毎月」とお送りください。
このとき、誰が何をしている業務か（例：社員が立替→代表が月末現金精算）を
一言添えていただけると、引き継ぎ書の補足に反映できます。

例3：
複数変更したい場合、返信は以下のようにお送りください：
  2番 毎月
  3番 毎月（社員の立替精算）

---

送信してから気づいたら、追加で「あと #1 は振替に変更」のように送っていただいてOKです。
すべてのパターンが分類できるまで、こちらからも追加確認させていただきます。
```

**Claude側の動作ルール：**
- 全パターンの分類が確定するまで、引き継ぎ書の最終生成に進まない
- 不足行があれば該当行だけ抜き出して丁寧に再質問：
  ```
  ありがとうございます。#2, #3 の分類はわかりました。
  残り #1「借) 接待交際費 / 貸) 立替金」（9ヶ月中7ヶ月、推奨=毎月）について、
  推奨通り「毎月」で進めてよろしいでしょうか？
  問題なければ返信は「1番 OK」、変更なら「1番 不定期」のようにお送りください。
  ```
- 推奨を変更した項目で現場知識が取れていなければ深掘り：
  ```
  #3 を「毎月」にしていただきありがとうございます。
  差し支えなければ、具体的にどういう業務か一言教えていただけますか？
  例：「社員が個人立替→月末に現金精算」「代表がカードのポイントを雑収入へ振替」など。
  聞かない方がよければ「省略」とお送りください。
  ```

#### 漏れパターンの反映先決定ロジック

ユーザー回答に基づき、以下のように反映する：

**「毎月」と回答された場合：**
1. 仕訳の借方・貸方から **動くBS科目** を特定
   - 借) PL / 貸) BS → 貸方のBS科目
   - 借) BS / 貸) PL → 借方のBS科目
   - 借) BS / 貸) BS（通帳系含む）→ 通帳系（普通預金・現金・未払金）でない方
   - 借) PL / 貸) PL → 振替（フェーズ5に誘導、選択肢4を推奨）
2. 特定したBS科目を Step 4 に追加（既にあれば頻度を「月次」に更新）
3. 月次フローのフェーズ2（月次の補助元帳・証憑から入力するBS科目）に追記
4. ユーザーから現場知識が取れていれば「補足」セクションに追加

**「不定期」と回答された場合：**
1. 同様にBS科目を特定
2. Step 4 に追加（頻度を「不定期」で）
3. 月次フローのフェーズ4（不定期発生のBS科目）に追記

**「年次」と回答された場合：**
1. Step 7（年次・不定期の大口取引）に追加

**「振替」と回答された場合：**
1. 月次フローのフェーズ5（振替仕訳）に具体例として追記

**「スキップ」と回答された場合：**
1. 引き継ぎ書には載せない（稀なので都度対応）

#### 手順7. 引き継ぎ書の最終生成

手順3〜6で確定した情報をもとに、以下の構成のマークダウンを `{code}_{name}/handover_FY{fiscal_year}.md` に保存する。

---

```markdown
# 記帳代行 引き継ぎシート

**事業者:** {事業者名}（コード {code}）
**業種:** （仕訳データから推定した業種。摘要・売上科目・原価科目から判断）
**対象期間:** FY{year}（{start} 〜 {end}）
**決算月:** {end_monthの月}
**経理方式:** 税込経理 / 税抜経理（Phase 2-5の判定結果）
**部門設定:** あり（{部門数}部門）/ なし
**作成日:** {today}

---

## Step 1. 全体像をつかむ

### 事業の概要
（仕訳データから読み取ったビジネスモデルを1-2段落で記述。
業種、主な売上、主な仕入先、農場・店舗等の拠点構成、関係法人があれば記載）

### 関係法人（仕訳データから検出された場合）
| 法人名 | 関係 | 会計上の役割 |
|--------|------|-------------|

### 数値サマリー
| 項目 | 金額・件数 |
|------|-----------|
| 売上高 | 約〇億円 |
| 仕訳件数 | {N}件 / {行数}行 |
| 入力元: JOURNAL_TYPE_NORMAL | 〇件 |
| 入力元: JOURNAL_TYPE_IMPORT | 〇件（ある場合） |
| ...（その他の入力元） | |

> **注意:** MF公式APIでは `JOURNAL_TYPE_NORMAL` にデータ連携（口座連携）の仕訳が含まれる（APIでは手入力と区別できない）。

### データ連携（口座連携）の状況
（Phase 2-1b + 2-1c で確認した情報。手動管理側=API、自動取得側=ユーザー申告）

| データ連携名 | 種別 | MF科目（補助科目） |
|---|---|---|

### 売上構造
| 科目 | 年間売上 | 主な入金経路 |
|------|---------|------------|

---

## Step 2. 証憑の入手先と届くタイミング

Step 4（BS科目別入力ソース一覧）と対応させて記載する。

### 月次で届く証憑

| 証憑 | タイミング | 対応BS科目（Step 4） |
|------|---------|-------------------|
| 売上請求書（発行控え） | 月次 | 売掛金(補助) |
| 仕入・外注請求書 | 月次 | 買掛金(補助) |
| クレジットカード明細 | 月次 → 翌月引落 | 未払金(カード) |
| 銀行通帳 | データ連携 or 月次 | 普通預金(補助) |
| 現金出納帳+領収書 | 月次 | 現金 |
| 給与明細（MF給与連携） | 月次 | 未払費用(給与)・預り金 |
| 社保納付書 | 月次 | 未払費用(社保)・法定福利費 |
| 源泉所得税・住民税納付書 | 月次 | 預り金（納付消込） |
| 借入返済予定表 | 月次 | 長期借入金(補助) |

### 不定期で届く証憑

| 証憑 | タイミング | 対応BS科目 |
|------|---------|---------|
| 個人立替精算書 | 立替発生時 | 立替金 |
| 仮払精算書 | 仮払発生時 | 仮払金 |
| 借用書・返済記録 | 借入時 | 役員借入金・短期借入金 |
| 契約書・手付金領収書 | 取引時 | 前払金・前受金 |
| 固定資産取得の見積書・請求書 | 取得時 | 建物・車両・工具・ソフトウェア等 |

**証憑フォルダの構成がわからない場合:**
以下のチェックリストで前任者に確認する。
- [ ] 証憑の保管場所（BOX / Google Drive / メール / 郵送 / 持参）
- [ ] 受領タイミング（月1回まとめて / 随時）
- [ ] 証憑の整理ルール
- [ ] 電子帳簿保存法の対応状況

---

## Step 3. 証憑 → 仕訳の対応マップ

証憑ごとに具体的な仕訳パターンを記載する。
仕訳データの集計結果と、証憑フォルダの情報を組み合わせて作成する。

### 3-1. 売上の計上
（売上科目・売掛金の発生パターン。どの証憑から売上を計上するか。）

**ソース証憑:** 〇〇
**仕訳パターン:**
```
(借方) 売掛金(〇〇) / (貸方) 売上高
```

### 3-2. 売掛金の回収
| 補助科目 | 年間発生額 | 回収先口座 | ソース証憑 |
|---------|----------|----------|-----------|

### 3-3. 仕入・外注の計上
| 証憑 | 仕訳パターン |
|------|------------|

### 3-4. 通帳 → 預金仕訳
| 通帳 | 対応するMF科目（補助科目） | 主な内容 |
|------|------------------------|---------|

### 3-5. 現金・小口現金 → 経費仕訳
（現金出納帳のソースと主な科目）

### 3-6. 給与 → 複合仕訳
（給与仕訳の全行パターン。最新月のサンプルを取引No単位で展開）

**注意: 給与の複合仕訳は取引ビューではなく行ビューで個別に集計すること。**

---

## ★ 月次入力の作業フロー（BS科目ベース）

> **設計思想:** 月次入力は **BS科目ごとの入力ソース** を上から順に処理すれば漏れない。
> 各BS科目の入力ソースは Step 4（BS科目別入力ソース一覧）に明示。
> PL科目は必ずBS科目とペアで発生するため、BSを全部拾えば自動的にPLも拾える。

### フェーズ1 データ連携の未仕訳を処理（画面のルーチン作業）

データ連携している全口座・全カード・全電子マネーについて、MFの未仕訳画面を処理する。
Step 9（通帳カタカナ→仕訳の逆引きマップ）を参照しながら処理する。

- [ ] 1-1. 普通預金 / 〇〇銀行（データ連携）→ Step 9-A 参照
- [ ] 1-2. 普通預金 / △△銀行（データ連携）→ Step 9-B 参照
- [ ] 1-3. 未払金 / 〇〇カード（データ連携）→ Step 9-C 参照
- [ ] 1-4. 仮払金 / Suica 等（電子マネー連携）→ Step 9-D 参照

### フェーズ2 補助元帳・証憑から入力するBS科目

- [ ] 2-1. **売掛金**（補助科目: 〇〇・△△・…）: 月次請求書から起票。回収はフェーズ1の銀行連携で消込
- [ ] 2-2. **買掛金**（補助科目: 〇〇・△△・…）: 月次仕入請求書から起票。支払はフェーズ1の銀行連携で消込
- [ ] 2-3. **現金**（残高管理あり・手入力の場合）: 現金出納帳と領収書を突合して月次入力
  - 相手科目の上位を明示（接待交際費、旅費交通費、地代家賃、備品・消耗品費 等）

### フェーズ3 給与・社保（MF給与連携）

- [ ] 3-1. **未払費用（給与）/ 預り金（所得税・住民税・社保・雇用保険）**: MF給与連携で取込
- [ ] 3-2. **未払費用（社会保険料）/ 法定福利費**: 納付書から月次計上 → 翌月口座振替で消込
- [ ] 3-3. **預り金（所得税・住民税・源泉所得税報酬）の納付**: 納付書から納付

### フェーズ4 不定期発生のBS科目（該当月のみ）

- [ ] 4-1. **仮払金**: 仮払受け・精算（運用している会社のみ）
- [ ] 4-2. **立替金**: 社員・役員の個人立替
- [ ] 4-3. **役員借入金・短期借入金**: 代表や役員からの一時貸借
- [ ] 4-4. **長期借入金**: 毎月返済（フェーズ1の銀行連携で消込）
- [ ] 4-5. **前払金・前受金**: 発生時のみ
- [ ] 4-6. **固定資産（建物・車両・工具・ソフトウェア等）**: 取得・除却時

### フェーズ5 振替仕訳（発生したら）

- [ ] 5-1. カードのポイント・キャッシュバック 等 → `(借) 未払金 / (貸) 雑収入` 系
- [ ] 5-2. 現金過不足の調整
- [ ] 5-3. 誤入力の修正・補助科目の付け替え

### フェーズ6 セルフチェック（BS残高の整合性確認）

- [ ] 6-1. 現金残高（手入力なので特に注意）
- [ ] 6-2. 普通預金残高（データ連携残高 vs 実通帳）
- [ ] 6-3. 売掛金の補助科目別残高
- [ ] 6-4. 買掛金の補助科目別残高
- [ ] 6-5. 未払金（カード）の残高（翌月引落予定額と一致するか）
- [ ] 6-6. 未払費用の残高
- [ ] 6-7. 預り金の残高（補助科目別）
- [ ] 6-8. 中間勘定（仮払金・立替金・役員借入金 等）の残高（長期滞留していないか）
- [ ] 6-9. マイナス残高の科目がないか
- [ ] 6-10. 部門の付け忘れ（該当する場合）

> **カバー率の検証（Phase 4B生成時の必須工程）:**
> 月次フロー生成後、Pythonで借方×貸方のパターンを頻度順に集計し、各パターンが上記フェーズ1〜5のどれに該当するか検証する。該当しないパターンがあればフェーズに追記するか、フェーズ5の例外処理として記載する。目標カバー率99%以上。

---

## Step 4. BS科目別 入力ソース一覧

> **引き継ぎ書の骨格。** BS科目ごとに「どの証憑・どのソースから入力するか」を1対1で対応づける。
> この表が完成していれば、月次入力で仕訳が浮くことはない。
> **注意:** 同じ「現金経費」でも、会社によって使う科目が異なる（現金・仮払金・立替金・役員借入金・代表者勘定・事業主借 等）。仕訳データから実際に使われているBS科目を洗い出して書くこと。

### 資産

| BS科目 | 補助科目 | 入力ソース | 頻度 | 備考 |
|---|---|---|---|---|
| 現金 | - | 現金出納帳 + 領収書 / CSVインポート / 等 | | 残高管理の有無を明示 |
| 普通預金 | 〇〇銀行 | データ連携 / 通帳手入力 | | 補助科目ごとに記載 |
| 売掛金 | 取引先名 | 月次請求書（手起票） | | 補助科目ごとに記載 |
| 仮払金 | - | 仮払精算書 | 不定期 | 代表者の仮払受け等 |
| 立替金 | - | 個人立替精算書 | 不定期 | 社員・役員の立替 |
| 前払金 | - | 契約書等 | 不定期 | |
| 棚卸資産 | - | 棚卸表 | 期末 | |
| 固定資産 | - | 取得時の見積書・請求書 | 取得時 | |

### 負債

| BS科目 | 補助科目 | 入力ソース | 頻度 | 備考 |
|---|---|---|---|---|
| 買掛金 | 取引先名 | 月次仕入請求書 | | |
| 未払金 | カード名/取引先 | カード明細（データ連携） / 振込手数料の手計上 | | カード毎に補助科目 |
| 未払費用 | 給与/社会保険料 等 | MF給与連携 / 納付書の手計上 | | |
| 預り金 | 所得税/住民税/社保/雇用保険/源泉所得税(報酬) | MF給与連携（発生）/ 納付書（消込） | | 補助科目5種は標準 |
| 短期借入金・役員借入金 | - | 借用書・通帳 | 不定期 | |
| 長期借入金 | 借入先別 | 返済予定表 + 銀行連携 | 月次 | 補助科目で管理 |
| 前受金 | - | 契約書 | 不定期 | |

### 純資産

| BS科目 | 補助科目 | 入力ソース | 頻度 | 備考 |
|---|---|---|---|---|
| 資本金 | - | 設立時払込 | 1回 | |
| 利益剰余金 | - | 期末決算整理 | 決算時 | |

### 運用上の注意

- **現金経費は「現金」科目だけとは限らない**。会社によっては仮払金・立替金・役員借入金・代表者勘定・事業主借など、運用科目が異なる。仕訳データから実際のパターンを抽出して記載すること。
- **各BS科目について、借方・貸方の主な相手科目と頻度を仕訳データから算出**して、根拠のある内容にする。

---

## Step 5. 毎月やる定期仕訳

決済口座・決済手段ごとにグループ化して表示する。

### 5-1. 普通預金(メイン口座) から直接払い
| 取引先/内容 | 借方科目 | 月額（平均） | 変動 |
|----------|--------|-------:|------|

### 5-2. クレジットカード経由（経費→未払金→翌月口座引落）
カード会社ごとに小テーブルを作成。

### 5-3. 現金払い
| 取引先/内容 | 借方科目 | 月額（平均） | 変動 |
|----------|--------|-------:|------|

### 5-4. 振替仕訳（口座動かない）
| 取引先/内容 | 借方科目 | 貸方科目 | 月額（平均） | 変動 |
|----------|--------|--------|-------:|------|

### 5-5. 給与仕訳（行ビューで人別集計）
| 科目 | 補助科目（人名） | 月額 | 部門 |
|------|------------|-----:|------|

（最新月の複合仕訳テンプレート全行も記載）

---

## Step 6. 中間勘定・特殊科目の処理ルール

（使われている中間勘定ごとに、件数・発生パターン・消込パターンを記載）

### 〇〇勘定（{件数}件）
- 発生パターン:
- 消込パターン:

---

## Step 7. 年次・決算整理仕訳と不定期の大口取引

### 年次・不定期の大口取引
| 時期 | 科目 | 内容 | 金額 |
|------|------|------|------|

### 主要BS科目の残高（参考値）
| 科目 | 残高 |
|------|------|

---

## Step 8. 科目別 頻出摘要パターン

入力時に迷ったら、以下の摘要パターンを参考にすること。

| 科目 | 頻出摘要 |
|------|---------|

---

{Step 9: ユーザーから残高照合画面のテキストが提供されている場合のみ、この位置に Phase 4B-9 で生成したセクションを挿入する。提供されていない場合はこのセクションごと省略する。}

## 補足: この法人特有の注意点

（仕訳データや証憑から読み取った、この法人固有の注意事項を箇条書きで記載。
例: ファクタリング処理、グループ間取引、補助科目の運用ルール、科目変更の経緯 等）
```

---

## 分析完了後のアテンド

レポート保存後、以下を添えてユーザーに報告する：

```
分析完了

（生成したレポートのファイル名を列挙）

--- 要点 ---
（ビジネスモデル・主要取引先・特記事項を3〜5行で）

--- 実質取引先の抽出状況 ---
取引ビュー: {X}% の取引で取引先を特定（{filled}/{total}件）
複合仕訳: {Y}件
主な特定元: （債権債務科目の補助科目 / 取引先フィールド / 費用科目の補助科目 / 摘要 等）

前々期（FY{fiscal_year - 1}）のデータと比較することもできます。
レポートの内容や、気になる点があればそのまま聞いてください！
```

**文字化けチェック（レポート保存後に必ず実行）:**
保存したマークダウンファイルをReadツールで先頭〜末尾まで流し読みし、`�`（U+FFFD）が含まれていないか確認する。
見つかった場合は該当箇所を修正してから納品する。

---

## 注意事項・よくある誤り

**実質取引先の特定について（最重要）：**
- MFクラウド会計では「取引先」フィールドを運用していない会社が大半
- 実務では補助科目で取引先を管理するのが一般的
- 本スキルでは2段階で実質取引先を特定する:
  - **行ビュー** (`enrich_partners`): 1.相手科目の債権債務補助 → 2.自科目の補助 → 3.取引先フィールド → 4.摘要
  - **取引ビュー** (`build_transaction_view`): 取引No全行をスキャンし、1.債権債務科目の補助 → 2.取引先フィールド → 3.費用/収益科目の補助（口座・税金除外）→ 4.摘要
- 取引先系の分析（売上先・仕入先・定期取引等）は**取引ビュー**を使う（複合仕訳で金額が分裂しない）
- BS残高・口座別・入力元の分析は**行ビュー**を使う
- レポートでは「特定元」を明示し、どこから取得した情報か読み手がわかるようにする
- `借方取引先` / `貸方取引先`（MFの取引先フィールド）を直接集計に使わない

**部門について：**
- 部門設定がある会社では、取引先→部門の対応表が記帳の肝になる
- 同じ取引先が複数部門にまたがる場合は要確認事項として明示する
- 部門の付与にムラがある科目（ある月はつけている、ある月はつけていない）も検出する
- 部門なし（全社共通）の科目は意図的な場合が多いのでそのまま記載

**海外・外国人取引について：**
- 人名・地名・通貨だけで取引の実態を決めつけない（顧客・現地スタッフ・業務委託先など様々）
- 摘要を必ず確認してから判断する

**資金移動勘定・口座間振替について：**
- 摘要に会社名が出てきても外部支払とは限らない
- 同じ取引Noの借方・貸方を両方確認して判断すること

**複数年度のデータについて：**
- 年度をまたいで分析する場合は全年度を結合してから分析する

**推測と事実の区別（厳守）：**

会計事務所が引き継ぎ資料として使うレポートなので、事実と推測が混在すると実害が出る。

**断言してよいもの**（「〜と思われる」不要）：
- 仕訳データに直接記録されている数値・勘定科目・取引先・摘要の文言
- 集計結果（件数・合計金額・月次パターンなど）

**「〜と思われる」「〜と推察される」を使うもの**：
- 摘要や科目名から類推した取引の目的・背景・ビジネス上の意図
- 事業モデルや組織の実態についての解釈

**書いてはいけないもの**：
- データに根拠のない憶測（「おそらく〜だろう」だけで根拠を示さない説明）
- 「〜と思われる」を多用して事実の記述まで曖昧にすること

例：
- 「毎月末に〇〇社へ100万円を支払っている（仕訳12件）」← 事実なので断言
- 「摘要に『システム利用料』とあることから、SaaSの月額費用と思われる」← 解釈なので「思われる」
- NG: 「毎月14,689円が計上されていると思われる」← 数字は事実なので「思われる」不要
- NG: 「〇〇社はおそらくメインの外注先だろう」← 根拠なし

**対応データについて：**
- JSON入力時のみ使える分析（`entered_by`・税額・インボイス区分）はCSV時はスキップ
- MF以外の会計ソフトのCSVは対応していない

---

## Phase 4B-9: Step 9（通帳カタカナ → 仕訳 逆引きマップ）の生成

**実行条件:** ユーザーから「MFの残高照合画面の情報」が1つ以上提供された場合のみ実行する。
提供されていない場合はこのフェーズをスキップし、Step 9セクションをテンプレから削除する。

### 9-1. 入力ファイルの実態を確認する

ユーザーが渡してくれるものは、**毎回フォーマットが違う**。MF残高照合画面のUIをガバッとドラッグ＆ドロップでコピペするやり方なので、以下のような多様なパターンがある:

- **テキストファイル(.txt/.md)**: タブ区切りで列が綺麗に並んでいる / スペース区切り / 改行位置がバラバラ / 全部1行に潰れている / 行番号プレフィックスありなし / HTMLタグ混入
- **CSVファイル(.csv)**: たまにある
- **スクリーンショット画像(.png/.jpg)**: 画面をそのまま撮ったもの。複数枚に分かれていることも
- **PDFファイル(.pdf)**: 印刷プレビューを保存したものなど
- **部分的・不完全**: 一部の取引しか含まれていない、見出しがない、列がズレている

**まず Read ツールで実際の中身を確認する**。判断基準:
- テキスト系 → そのまま読める
- 画像系 → Read ツール（マルチモーダル）で画像内容を読み取る
- PDF → pdf スキルや md-to-pdf スキルの逆方向で抽出、または Read で直接（小さければ）

### 9-2. ファイルから抽出すべき最低限の情報

**最終的に何が欲しいかを意識して読む。** 1取引につき以下の項目が取れれば構造化できる:

| フィールド | 必須? | 備考 |
|---|---|---|
| 取引日 | 必須 | 頻度算出用 |
| 通帳カタカナ摘要 | 必須 | 例: 「出金 タテコウツキバライ」 |
| 入金額 or 出金額 | 必須 | どちらかが入っている |
| 勘定科目（相手科目） | 必須 | 例: 保険料、未払金 |
| 補助科目 | 任意 | 例: 社会保険、カード名 |
| MF摘要 | 任意 | 例: 「商工会共済」「建更月払」 |
| ステータス | 必須 | 「入力済み」 / 「未入力」 |

**読み取れない・抜けている場合の対処:**
- 列がズレている → 行頭の取引日（YYYY/MM/DD パターン）と金額（円）を手がかりに正しい列を再構成する
- 全部1行に潰れている → 取引日パターンで強制的に分割する
- スクショで一部欠けている → 読める部分だけ使い、Step 9 の冒頭に「※残高照合画面の一部のみのデータです」と注記する
- 構造が完全に壊れている → ユーザーに「読み取れませんでした。MFの残高照合画面でテキストを再取得していただけますか？コツは……」と返して再取得を依頼する

### 9-3. 構造化の方法（2通り）

#### 方法A: パーサースクリプト（タブ区切りの綺麗なテキストの場合）

入力ファイルの種類に応じて2種類のパーサーを使い分ける。**どちらもJSON突合（`--journals`）を強く推奨**。

**A-1. 明細一覧画面用パーサー（推奨）**

`{skill_dir}/scripts/parse_meisai_list.py`

```
{PYTHON} {skill_dir}/scripts/parse_meisai_list.py --journals {code}_{name}/journals_FY{year}.json <file1.txt> [<file2.txt> ...] > {code}_{name}/meisai_aggregated.json
```

対応入力フォーマット:
- MFクラウド会計 > データ連携 > 登録済み一覧 > 「明細」画面のコピペ
- 3行で1取引: 行1=日付・内容・金額・残高・サービス名 / 行2=口座名 / 行3=ステータス・取引No
- 銀行口座・カード・電子マネーすべて対応（画面構造が同じ）

**A-2. 残高照合画面用パーサー（代替）**

`{skill_dir}/scripts/parse_balance_match.py`

```
{PYTHON} {skill_dir}/scripts/parse_balance_match.py --journals {code}_{name}/journals_FY{year}.json <file1.txt> [<file2.txt> ...] > {code}_{name}/balance_match_aggregated.json
```

対応入力フォーマット:
- MFクラウド会計 > 取引管理 > 残高照合画面のコピペ
- 2行で1取引: 行1=取引日・通帳摘要・入金・出金・残高・ステータス・取引No・相手勘定科目 / 行2=補助科目・摘要
- 銀行口座のみ対応（カードは科目が画面に表示されない）

**`--journals` オプションで取得できる情報:**
- 税区分（課仕10%、非仕、対象外、不課税 等）
- 部門（農場A〜G、共通 等）
- 補助科目の正確な値（画面では1行目しか見えない）
- 複合仕訳の全行構造（画面では「諸口」や1科目しか見えない仕訳の本当の中身）
- インボイス区分（適格 / 区分記載 / 対象外）
- 取引先フィールド

`--journals` なしの場合、明細一覧パーサーは相手科目すら取れない（画面に表示されないため）。残高照合パーサーは主要科目は取れるが、複合仕訳は「諸口」としか見えない。

**⚠ 期間整合性の注意:**
明細一覧／残高照合のテキストの取引日と journals JSON の対象期間が**重なっていないと突合できない**。
例: journals が 2025-05〜2025-12 で、明細が 2026-01〜02 → 突合0件。
この場合は **getJournals で明細の期間も含めて取り直す**こと。
スクリプト実行後、`journal_match_count` が 0 や極端に少ない場合は期間ズレを疑う。
ただし「未入力」「対象外」の取引は当然 JSON に存在しないので、`journal_match_count` と `input_count` が一致すれば正常。

**⚠ MFの仕訳構造の罠（JSON突合時）:**
MFの仕訳JSONでは、**1つの `branch` に `debitor` と `creditor` が両方入ることがある**（通常の対応行1組）。
さらに別の `branch` で片方だけの行が追加される（複合仕訳の追加行）。
パーサーでは両方を展開してから代表行を選ぶこと（既に `extract_journal_detail` で対応済み）。

代表行の選び方:
- 入金（amount > 0）なら通帳科目は借方 → 相手は**貸方**優先で取る
- 出金（amount < 0）なら通帳科目は貸方 → 相手は**借方**優先で取る
- これを間違えると、売掛金回収なのに「雑費（振込手数料）」が相手科目として出てくる等の誤判定が起きる

**方法Bにフォールバックすべき条件（パーサーでは対応不能な場合）:**
パーサーを実行した後、以下のいずれかに該当したら方法Bに切り替える：

- パーサーが例外終了した（構文エラー・パース失敗）
- `total_transactions` が 0 または極端に少ない（ヘッダー検出失敗）
- 入力ファイルが画像（.png/.jpg/.jpeg/.heic 等）
- 入力ファイルが PDF
- 入力ファイルがCSV・Excel・HTMLコピペ等、想定外のフォーマット
- サンプル出力を見て、カタカナ摘要・金額・取引Noのいずれかが明らかにズレている
- ユーザーの画面コピペ方法が独特で、タブが揃っていない／改行位置がバラバラ／行番号プレフィックス混入等

**重要:** パーサーで一部だけ取れた場合も、件数が想定より極端に少なければ方法Bで取り直す。
パーサーの結果を鵜呑みにせず、`total_transactions` と入力ファイルの行数・件数感覚を照らし合わせること。

#### 方法B: Claude が直接読んで構造化（汎用・フォールバック）

パーサーで対応できない場合はこちらに切り替える。ファイルの中身を Read で読み込み、Claude 自身が以下のJSON構造に整形する:

```json
{
  "accounts": [
    {
      "account_name": "（ファイル名や画面見出しから判定した口座名／サービス名）",
      "source_type": "meisai_list or balance_match",
      "transactions": [
        {
          "date": "2026/02/02",
          "katakana": "出金 コウザフリカエ",
          "direction": "出金",
          "amount": 1097711,
          "torihiki_no": "1528",
          "kamoku": "未払金",
          "hojo": "社会保険",
          "mf_tekiyo": "社会保険料",
          "status": "入力済み"
        }
      ]
    }
  ]
}
```

- **明細一覧画面の場合**: 画面に相手科目が表示されないため、`kamoku` / `hojo` / `mf_tekiyo` は空でOK（JSON突合で補完する）。必須なのは `date` / `katakana` / `amount` / `torihiki_no` / `status`
- **残高照合画面の場合**: 画面に相手科目が表示されるので、可能な範囲で `kamoku` / `hojo` / `mf_tekiyo` も埋める
- **スクショ画像の場合**: Read ツールで画像を読み込み、視認できる列を JSON に起こす
- **PDFの場合**: ページが少なければ Read で直接、多ければ pdf スキルでテキスト化してから読む
- **複数ファイル**: `accounts` 配列に追加していく

**JSON突合（強く推奨）:**
`torihiki_no` が取れていれば、journals JSON から該当する仕訳を引いて以下を補完する:
- 税区分・部門・補助科目・複合仕訳構造・インボイス区分

突合手順:
1. journals JSON の `journals[].number` と取引の `torihiki_no` を **文字列化して比較**（型は `int` vs `str`）
2. 一致した仕訳の `branches` を展開（**1つの branch に debitor / creditor 両方入ることがあるので両方取る**）
3. 代表行は **通帳科目（普通預金・当座預金・現金・未払金）の反対側** を優先:
   - 入金（amount > 0）→ 相手は**貸方**優先
   - 出金（amount < 0）→ 相手は**借方**優先
   - これを間違えると、売掛金回収なのに「雑費（振込手数料）」等の追加行が相手科目として出てくる誤判定が起きる
4. 反対側に候補がなければ、通帳科目以外の行を探す
5. 全部通帳系（口座間振替など）なら1行目を返す

### 9-4. 集計とカテゴリ分け

得られた `transactions` を以下の方針で集計する（パーサーを使った場合は集計済みなのでこのステップは省略可）:

1. **(正規化カタカナ, 勘定科目, 補助科目) でグループ化**
   - 正規化: 「入金」「出金」「振込入金」プレフィックスや日付プレフィックス（例: `2- 2 シヨウテンカイ` の `2- 2`）を除去
   - 同じカタカナでも科目が違えば別グループ（金額帯で別科目になるパターンに注意）

2. **各グループの集計値を出す**
   - 件数（頻度）
   - 金額の min / max
   - 定額か変動か（金額が全件同じなら「定額」）
   - MF摘要のサンプル

3. **カテゴリに振り分け**（科目 × カタカナ × 金額帯で判定）

| カテゴリ | 判定基準（参考） |
|---|---|
| **入金（売掛金回収・収益）** | direction == "入金" |
| **定額・準定額引落** | 出金で is_constant == true、または振れ幅が小さい |
| **給与・社保・税金** | カタカナに `キユウヨ`/`コウザフリカエ`（社保）/`チヨウケンミンゼイ`（住民税）/`ゲンセン`（源泉）等 |
| **クレカ・カード引落** | 科目が `未払金` でカタカナに `クレジツト`/`カ-ド` 等のクレカ社名が含まれる |
| **電気代** | カタカナに `デントウ`/`デンリヨク`/`イツカツ` |
| **ガス・水道** | 科目が `水道光熱費` または `水道光熱費(製)` で電気以外 / カタカナに `ガス`/`スイドウ`/水道局名 等 |
| **振込（取引先別）** | 上記いずれにも該当しない出金で、取引先名らしきカタカナがあるもの |
| **手数料** | カタカナが `テスウリヨウ`/`ホウジンIB` / 科目が `支払手数料` |
| **仮払金・その他** | 科目が `仮払金`、または不明なもの |
| **未入力（要注意）** | status が「未入力」のものすべて |

カテゴリ判定のキーワードは目安。ユーザーの会社の取引内容を見て柔軟に判断する。
迷ったら「振込（取引先別）」または「仮払金・その他」に入れる。

### 9-5. Markdown出力テンプレ

**JSON突合ありの場合は税区分・部門列を含める。** 突合なしの場合は省略可。

**重要**: Step 9 は `handover_FY{year}.md` の**末尾に inline で展開**する（単一ファイル原則）。`meisai_aggregated.json`（parse_meisai_list.py の出力）は**中間ファイル**であり、Step 9 を handover に展開したら**削除**する（再生成が必要ならパーサーを再実行すれば冪等）。

```markdown
## Step 9. 通帳カタカナ → 仕訳 逆引きルールブック

> **使い方:** MFのデータ連携で未仕訳が表示されたら、通帳摘要のカタカナを下表から探して科目を確定する。
> ソース: MF残高照合画面の実績データ（{口座数}口座、計{N}取引、入力済み{M}件 / 未入力{K}件 / JSON突合 {Q}件）。

### Step 9-A. {口座名1}

#### 9-A-1. 入金（売掛金回収・収益）

| 通帳カタカナ | 勘定科目 | 補助科目 | 部門 | 税区分 | MF摘要の書き方 | 金額目安 | 頻度 |
|---|---|---|---|---|---|---|---|
| シヨウカンジユンビキン | 売掛金 | 補助科目なし | 部門なし | 非仕 | 償還準備金 | 250万〜390万 | 月3〜4回 |

#### 9-A-2. 出金 — 毎月の定額・準定額引落

| 通帳カタカナ | 勘定科目 | 補助科目 | 部門 | 税区分 | MF摘要の書き方 | 金額 | 備考 |
|---|---|---|---|---|---|---|---|
| JAミツイリ-ス | 賃借料 | 補助科目なし | 部門なし | 課仕10% | JAミツイリース | **77,000円（定額）** | |

#### 9-A-3. 出金 — 給与・社保・税金
#### 9-A-4. 出金 — クレカ・カード引落

#### 9-A-5. 出金 — 電気代（契約番号と農場部門の対応）

| 通帳カタカナ | 勘定科目 | 補助科目 | 部門 | 税区分 | 金額目安 | 件数 |
|---|---|---|---|---|---|---|
| デントウ 08-01 | 水道光熱費 | 補助科目なし | 部門なし | 課仕10% | 6,941〜35,602円 | N回 |
| デントウ 08-02 | 水道光熱費(製) | 電気 | 農場E(平出水) | 課仕10% | 22,814円 | N回 |

> **電気代は契約番号（08-01, 08-02 等）で農場部門が決まっている**。同じ「デントウ」でも番号で部門が違うので注意。

#### 9-A-6. 出金 — ガス・水道
#### 9-A-7. 出金 — 振込（取引先別）
#### 9-A-8. 出金 — 手数料
#### 9-A-9. 出金 — 仮払金・その他

#### 9-A-10. 複合仕訳のテンプレート（重要）

残高照合画面では「諸口」や1科目しか見えないが、実際は複合仕訳になっているもの。
JSON突合で実際の仕訳構造を取得済み。**新任担当者はこのテンプレ通りに入力すること。**

##### キユウヨ（給与） — 21行の複合仕訳例（取引No 1546）

| 借/貸 | 勘定科目 | 補助科目 | 部門 | 税区分 | 金額 |
|---|---|---|---|---|---|
| 借 | 役員報酬 | 角 晋吉 | - | 対象外 | 450,000 |
| 借 | 給料賃金(製) | - | 農場A | 対象外 | 190,000 |
| ... | ... | ... | ... | ... | ... |
| 貸 | 未払費用 | - | - | 対象外 | 2,391,287 |

#### 9-A-11. 未入力が多い取引（要注意）

| 通帳カタカナ | 金額 | 推定内容 | 対応方針 |
|---|---|---|---|
| 0071 | 271万 | JA購買品（大額） | 農協買掛明細と突合して科目確定 |

### Step 9-B. {口座名2}
（同様）

### Step 9 まとめ：注意すべきパターン

仕訳の入力にあたって、特に注意すべきパターンを抽出して記載する：
- 同じカタカナで金額により科目・部門が分かれるもの（例: タテコウツキバライ＝建更月払、デントウ系電気代）
- 残高照合画面では「諸口」しか見えないが実は複合仕訳のもの（給与、複合経費）
- 摘要なしの「出金」「入金」のみのパターン（仮払金など）
- 4桁番号のみの摘要（口座振替コードなど。番号→取引先の対応をメモ）
- 未入力で残っている定型的な取引（処理ルールが未確立の可能性）
```

### 9-6. 出力上の細かい注意

- 同じ正規化カタカナでも複数の科目に分かれている場合、サブセクションをまたいでも漏れなく全部表示する
- 金額が固定の場合は「**N円（定額）**」と太字、変動の場合は「N円〜M円」のレンジ表示
- MF摘要が空（諸口仕訳など）の場合は「（複合仕訳のため摘要なし）」と注記
- カテゴリ内の表示順は頻度（件数）の降順が望ましい
- 4桁番号や摘要なしなど **特に解釈が難しいもの** は別途「⚠ 注意」マークと注記をつける
- 1ヶ月分しかない場合は「※1ヶ月分のサンプルのみ。年次・四半期取引は含まれていない」と注記
