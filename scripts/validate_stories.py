#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORIES = ROOT / "stories"
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,79}$")
REQUIRED = {"schema_version", "story_id", "world_id", "title", "author", "completed_at", "kind", "summary", "fragments", "themes", "relations", "consent"}
FORBIDDEN_PATTERNS = [re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"), re.compile(r"/Users/[^/\s]+/"), re.compile(r"BEGIN [A-Z ]*PRIVATE KEY")]

def main():
    errors = []
    seen = set()
    for meta_path in sorted(STORIES.glob("*/*/meta.json")):
        if "_template" in meta_path.parts:
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{meta_path}: JSON 无法读取：{exc}")
            continue
        missing = REQUIRED - set(meta)
        if missing: errors.append(f"{meta_path}: 缺少字段 {sorted(missing)}")
        story_id = meta.get("story_id", "")
        if not ID_PATTERN.fullmatch(story_id): errors.append(f"{meta_path}: story_id 格式错误")
        if story_id in seen: errors.append(f"{meta_path}: story_id 重复")
        seen.add(story_id)
        if meta.get("kind") not in {"player-story", "community-thread", "canon"}: errors.append(f"{meta_path}: kind 不合法")
        if meta.get("consent", {}).get("public") is not True: errors.append(f"{meta_path}: 缺少公开同意")
        story_path = meta_path.with_name("story.md")
        if not story_path.exists(): errors.append(f"{meta_path}: 缺少 story.md")
        combined = meta_path.read_text(encoding="utf-8") + (story_path.read_text(encoding="utf-8") if story_path.exists() else "")
        for pattern in FORBIDDEN_PATTERNS:
            if pattern.search(combined): errors.append(f"{meta_path}: 检测到可能的秘密或本地路径")
    if errors:
        print("\n".join(f"ERROR: {error}" for error in errors), file=sys.stderr)
        return 1
    print(f"Validated {len(seen)} stories.")
    return 0

if __name__ == "__main__": raise SystemExit(main())
