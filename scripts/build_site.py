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
(ROOT / "stories" / "index.json").write_text(json.dumps({"schema_version": 1, "stories": stories}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Built index for {len(stories)} stories.")
