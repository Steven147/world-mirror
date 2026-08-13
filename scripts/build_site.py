#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
stories = []
details = {}
for path in sorted((ROOT / "stories").glob("*/*/meta.json")):
    if "_template" in path.parts: continue
    meta = json.loads(path.read_text(encoding="utf-8"))
    detail_key = f'{meta["world_id"]}/{meta["story_id"]}'
    meta["story_path"] = str(path.with_name("story.md").relative_to(ROOT))
    meta["detail_path"] = "story-details.json"
    meta["detail_key"] = detail_key
    dialogue = [
        json.loads((path.parent / relative).read_text(encoding="utf-8"))
        for relative in meta.get("dialogue_files", [])
    ]
    details[detail_key] = {
        "schema_version": 1,
        "story_id": meta["story_id"],
        "world_id": meta["world_id"],
        "title": meta["title"],
        "dialogue": dialogue,
    }
    stories.append(meta)

index = json.dumps(
    {"schema_version": 1, "stories": stories},
    ensure_ascii=False,
    indent=2,
) + "\n"
for output in (ROOT / "stories" / "index.json", ROOT / "site" / "stories.json"):
    output.write_text(index, encoding="utf-8")

(ROOT / "site" / "story-details.json").write_text(
    json.dumps(
        {"schema_version": 1, "stories": details},
        ensure_ascii=False,
        indent=2,
    ) + "\n",
    encoding="utf-8",
)

print(f"Built site index for {len(stories)} stories.")
