# Money Forward Cloud Codex Plugin

Codex plugin and skills for using Money Forward Cloud Accounting MCP servers.

This repository contains:

- `.codex-plugin/plugin.json`: Codex plugin metadata
- `.mcp.json`: Money Forward Cloud MCP server definitions for alpha and beta endpoints
- `skills/unofficial-official-mf-mcp-skill`: Skill directory for `unofficial-official-mf-mcp-skill`, an operational guide for the official Money Forward Cloud Accounting MCP
- `skills/mfc-journal-analyst`: Journal analysis workflow and helper scripts

## Plugin vs Skills

This repository includes both:

- **Plugin**: registers the Money Forward Cloud MCP servers in Codex.
- **Skills**: teach Codex how to use those MCP tools safely and how to analyze journal data.

If you install the full plugin, the skills under `skills/` are included through
`.codex-plugin/plugin.json`:

```json
{
  "skills": "./skills/",
  "mcpServers": "./.mcp.json"
}
```

So in normal use, install the plugin once. You do not need to install the skills
separately.

The included skills are:

- `unofficial-official-mf-mcp-skill` (`skills/unofficial-official-mf-mcp-skill`): Money Forward Cloud Accounting MCP usage guide.
- `mfc-journal-analyst`: Journal analysis and handover-document workflow.

## Install and Usage

This repository is a Codex plugin directory. Use the whole repository, not only
one skill file.

### Easiest: ask Codex to place the plugin

After cloning or downloading this repository, open Codex and ask:

```text
このフォルダをCodexアプリのローカルプラグインとして配置して。
```

For example:

```text
/path/to/moneyforward-cloud-codex をCodexアプリのローカルプラグインとして配置して。
```

Then install it from the Codex app:

1. Open the sidebar item **Plugins**.
2. Change the plugin source dropdown from **Built by OpenAI** to **Local Plugins**.
3. Find **Money Forward Cloud MCP**.
4. Click the plugin to install or enable it.

When a checkmark appears next to the plugin, installation is complete.

### Get the plugin files

Clone the repository:

```bash
git clone https://github.com/kentaroajisaka/moneyforward-cloud-codex.git
```

Or download the GitHub ZIP and unzip it first. The extracted folder is the
plugin directory.

### Manual local placement

For manual local development, the directory layout Codex uses for local plugins is:

```text
~/.codex/plugins/cache/local/moneyforward-cloud-mcp/0.1.1/
```

The plugin root must contain:

```text
.codex-plugin/plugin.json
.mcp.json
skills/
```

Do not upload the ZIP to a normal Codex chat and expect it to install itself.
Codex can inspect the files, and a local Codex agent can help place them in the
local plugin directory, but the plugin becomes active only after it appears under
**Local Plugins** and is installed or enabled.

### Skill-only ZIP

`skills/unofficial-official-mf-mcp-skill/build-zip.sh` creates a ZIP for the
`unofficial-official-mf-mcp-skill` skill only. That ZIP does not include
`.mcp.json`, so it does not register the Money Forward MCP servers by itself.

Use a skill-only ZIP only when you already have the MCP server configured
elsewhere and want to install just the instructions.

Use the full plugin repository when you want both:

- Money Forward Cloud MCP server definitions
- Money Forward related Codex skills

The plugin exposes two MCP server names:

- `mf-official-beta`: recommended for normal interactive use
- `mf-official-alpha`: useful for headless flows or handling multiple offices in parallel

After installation, ask Codex things like:

- `Use Money Forward Cloud MCP beta.`
- `MFクラウド会計の仕訳を取得して分析して`
- `マネーフォワードの試算表を見たい`

## Privacy Notes

This repository is intended to contain only reusable plugin and skill instructions.

Do not commit:

- `.mfc_token.json`
- exported journal files such as `journals_FY*.json`
- customer-specific accounting data
- generated analysis reports containing client information

The included `.gitignore` excludes common local analysis artifacts.

## Author

鯵坂健太郎（あじさか けんたろう）

- 税理士 / 鯵坂税理士事務所 代表
- https://office-wing.net/
- X: [@sabaaji0113](https://x.com/sabaaji0113)

## License

MIT License
