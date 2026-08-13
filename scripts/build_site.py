#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
stories = []
for path in sorted((ROOT / "stories").glob("*/*/meta.json")):
    if "_template" in path.parts: continue
    meta = json.loads(path.read_text(encoding="utf-8"))
    meta["story_path"] = str(path.with_name("story.md").relative_to(ROOT))
    stories.append(meta)

index = json.dumps(
    {"schema_version": 1, "stories": stories},
    ensure_ascii=False,
    indent=2,
) + "\n"
for output in (ROOT / "stories" / "index.json", ROOT / "site" / "stories.json"):
    output.write_text(index, encoding="utf-8")

print(f"Built site index for {len(stories)} stories.")
