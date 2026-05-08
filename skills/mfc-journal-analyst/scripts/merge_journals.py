#!/usr/bin/env python3
"""
MFC CA getJournals のツール結果ファイル（JSON）を1つの canonical JSON にマージする。

Usage:
    python merge_journals.py <tool_result_file1> [file2 ...] <output.json>
"""

import json
import sys
import os
from datetime import datetime, timezone


def parse_tool_result(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    payload = json.loads(data[0]["text"])
    return payload.get("journals", []), payload.get("metadata", {})


def main():
    if len(sys.argv) < 3:
        print("Usage: python merge_journals.py <file1> [file2 ...] <output.json>")
        sys.exit(1)

    *input_files, output_path = sys.argv[1:]

    all_journals = []
    total_meta = {}
    for fp in sorted(input_files):
        journals, meta = parse_tool_result(fp)
        all_journals.extend(journals)
        total_meta = meta
        print(f"  {os.path.basename(fp)}: {len(journals)} 件", file=sys.stderr)

    result = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "total_count": len(all_journals),
        "metadata": total_meta,
        "journals": all_journals,
    }

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"保存完了: {output_path}  ({len(all_journals)} 件)")


if __name__ == "__main__":
    main()
