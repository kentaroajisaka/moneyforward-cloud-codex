# Money Forward Cloud Codex Plugin

マネーフォワード クラウド会計の公式MCPをCodexで使うための、非公式ローカルプラグインです。

このリポジトリには以下が含まれます。

- `.codex-plugin/plugin.json`: Codexプラグインのメタデータ
- `.mcp.json`: Money Forward Cloud MCP の alpha / beta エンドポイント定義
- `skills/unofficial-official-mf-mcp-skill`: 公式MCPの使い方・クセをCodexに教えるスキル（仕訳の取得・登録・更新、試算表取得など）
- `skills/mfc-journal-analyst`: 仕訳分析・引き継ぎ資料作成用スキル

## プラグインとスキルの関係

このリポジトリは、**プラグイン**と**スキル**を両方含んでいます。

- **プラグイン**: CodexにMoney Forward Cloud MCPサーバーを登録する
- **スキル**: CodexにMCPツールの安全な使い方や仕訳分析手順を教える

フルプラグインをインストールすると、`skills/` 配下のスキルも一緒に読み込まれます。

```json
{
  "skills": "./skills/",
  "mcpServers": "./.mcp.json"
}
```

通常は、**このプラグインを1回インストールすればOK**です。スキルを別途インストールする必要はありません。

同梱スキル:

- `unofficial-official-mf-mcp-skill`: マネーフォワード クラウド会計 公式MCPの操作ガイド（仕訳の取得・登録・更新、試算表取得など）
- `mfc-journal-analyst`: 仕訳データの分析・引き継ぎ資料作成ワークフロー

## インストール方法

このリポジトリ全体がCodexプラグインです。`SKILL.md` だけではなく、フォルダ全体を使ってください。

### いちばん簡単な方法

このリポジトリをclone、またはGitHubからZIPでダウンロードして展開します。

その後、Codexアプリで次のように頼みます。

```text
このフォルダをCodexアプリのローカルプラグインとして配置して。
```

例:

```text
/path/to/moneyforward-cloud-codex をCodexアプリのローカルプラグインとして配置して。
```

配置できたら、Codexアプリ側で有効化します。

1. サイドメニューの **Plugins** を開く
2. 上部のプラグイン種別を **Local Plugins** に切り替える
3. **Money Forward Cloud MCP** を探す
4. クリックしてインストール、または有効化する

チェックマークが表示されれば完了です。

### ファイルを取得する

cloneする場合:

```bash
git clone https://github.com/kentaroajisaka/moneyforward-cloud-codex.git
```

ZIPでダウンロードする場合は、先に展開してください。展開後のフォルダ全体がプラグインです。

### 手動で配置する場合

Codexのローカルプラグインは、次のような場所に配置されます。

```text
~/.codex/plugins/cache/local/moneyforward-cloud-mcp/0.1.1/
```

プラグインのルートには、少なくとも次の3つが必要です。

```text
.codex-plugin/plugin.json
.mcp.json
skills/
```

ZIPファイルを普通のCodexチャットに添付するだけでは、自動インストールされません。Codexは中身を読むことはできますが、プラグインとして有効にするには、ローカルプラグインとして配置したうえで **Local Plugins** からインストールまたは有効化してください。

## スキル単体ZIPについて

`skills/unofficial-official-mf-mcp-skill/build-zip.sh` は、`unofficial-official-mf-mcp-skill` だけのZIPを作るためのスクリプトです。

このZIPには `.mcp.json` が含まれないため、Money Forward MCPサーバー自体は登録されません。

すでにMCPサーバー設定が済んでいて、説明書スキルだけ追加したい場合に使ってください。通常は、このリポジトリ全体をプラグインとしてインストールするのがおすすめです。

## 使い方

インストール後、Codexに次のように依頼できます。

```text
Use Money Forward Cloud MCP beta.
```

```text
MFクラウド会計の仕訳を取得して分析して
```

```text
MFクラウド会計にこの仕訳を登録して
```

```text
MFクラウド会計の仕訳を更新したい
```

```text
マネーフォワードの試算表を見たい
```

利用できるMCPサーバー名:

- `mf-official-beta`: 通常はこちらを推奨
- `mf-official-alpha`: ヘッドレス環境や複数事業者を同時に扱う場合に利用

## 注意事項

このリポジトリは、再利用可能なプラグイン定義とスキル説明だけを含める想定です。

コミットしないもの:

- `.mfc_token.json`
- `journals_FY*.json` などの仕訳エクスポート
- 顧客固有の会計データ
- 顧客情報を含む分析レポート

`.gitignore` で、よくあるローカル分析ファイルは除外しています。

## 更新履歴

### 0.1.2（2026-09-25）

- スキル `unofficial-official-mf-mcp-skill` を更新（元のスキルの v2.4.0 と同じ内容）
  - 明細（取引）の取得 `getTransactions` の仕様（`per_page` は10〜500、金額で絞るときは `side` が必須など）と、月次のチェックでの使い方を追加
  - 推移表を `with_sub_accounts: true` で取ると「補助科目なし」の行が出て、補助科目の付け忘れが分かることを追加
  - 部門別の残高を仕訳から集計するときは期首仕訳を必ず含めること、部門の合計を推移表と検算することを追加

### 0.1.1

- README に、仕訳の登録に対応している範囲を明記

### 0.1.0

- 最初の公開

## 作成者

鯵坂健太郎（あじさか けんたろう）

- 税理士 / 鯵坂税理士事務所 代表
- https://office-wing.net/
- X: [@sabaaji0113](https://x.com/sabaaji0113)

## ライセンス

MIT License
