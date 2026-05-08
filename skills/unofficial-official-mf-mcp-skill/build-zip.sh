#!/bin/bash
# スキル単体のzipを生成するスクリプト
#
# Usage: ./build-zip.sh [output_path]
# Default: /tmp/unofficial-official-mf-mcp-skill.zip

set -e

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT="${1:-/tmp/unofficial-official-mf-mcp-skill.zip}"
WORK="/tmp/mf-mcp-skill-zip-$$"
DIST="$WORK/unofficial-official-mf-mcp-skill"

rm -rf "$WORK"
mkdir -p "$DIST"

cp "$SKILL_DIR/SKILL.md" "$DIST/SKILL.md"

# 残りのファイルをそのままコピー
for dir in recipes references scripts; do
    if [ -d "$SKILL_DIR/$dir" ]; then
        cp -r "$SKILL_DIR/$dir" "$DIST/"
    fi
done

# LICENSEがあればコピー
[ -f "$SKILL_DIR/LICENSE" ] && cp "$SKILL_DIR/LICENSE" "$DIST/"

# zip生成
rm -f "$OUTPUT"
cd "$WORK"
zip -r "$OUTPUT" unofficial-official-mf-mcp-skill/

# 確認
echo ""
echo "=== 公開版zip生成完了 ==="
echo "出力: $OUTPUT"
echo ""
echo "--- 含まれるファイル ---"
unzip -l "$OUTPUT"

# クリーンアップ
rm -rf "$WORK"
