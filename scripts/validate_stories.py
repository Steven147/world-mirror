#!/usr/bin/env python3
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORIES = ROOT / "stories"
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,79}$")
REQUIRED = {"schema_version", "story_id", "world_id", "title", "author", "started_at", "completed_at", "exported_at", "uploaded_at", "total_play_seconds", "kind", "summary", "worldview", "turn_count", "turn_files", "keywords", "characters", "concepts", "fragment_answers", "fragments", "themes", "relations", "consent"}
INDEX_TYPES = {"人物", "概念", "事件", "地点", "物理规律"}
FORBIDDEN_PATTERNS = [re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"), re.compile(r"/Users/[^/\s]+/"), re.compile(r"BEGIN [A-Z ]*PRIVATE KEY")]

def semantic_length(text):
    return len(re.findall(r"[\u3400-\u9fffA-Za-z0-9]", text))

def parse_time(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None: raise ValueError("timezone required")
    return parsed

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
        if semantic_length(meta.get("summary", "")) != 20: errors.append(f"{meta_path}: summary 必须恰好为 20 个汉字、字母或数字")
        keywords = meta.get("keywords", [])
        if len(keywords) != 10: errors.append(f"{meta_path}: keywords 必须恰好为 10 条")
        for index, item in enumerate(keywords, 1):
            if not isinstance(item, dict) or set(item) != {"name", "type", "description"}: errors.append(f"{meta_path}: keywords[{index}] 结构错误")
            elif item.get("type") not in INDEX_TYPES: errors.append(f"{meta_path}: keywords[{index}] type 不合法")
        for field in ("characters", "concepts"):
            value = meta.get(field)
            if not isinstance(value, list) or not value: errors.append(f"{meta_path}: {field} 必须是非空数组")
        try:
            started=parse_time(meta.get("started_at","")); completed=parse_time(meta.get("completed_at","")); parse_time(meta.get("exported_at","")); parse_time(meta.get("uploaded_at",""))
            if completed < started: errors.append(f"{meta_path}: completed_at 早于 started_at")
            if meta.get("total_play_seconds") != int((completed-started).total_seconds()): errors.append(f"{meta_path}: total_play_seconds 计算错误")
        except (ValueError,TypeError): errors.append(f"{meta_path}: 现实时间戳必须是带时区的 ISO 8601 格式，且 uploaded_at 不得为空")
        answers=meta.get("fragment_answers",[])
        if not isinstance(answers,list) or not answers: errors.append(f"{meta_path}: fragment_answers 必须是非空数组")
        else:
            for index,item in enumerate(answers,1):
                if not isinstance(item,dict) or set(item)!={"fragment_id","question","answer","passed","answered_at","collected_at"}: errors.append(f"{meta_path}: fragment_answers[{index}] 结构错误"); continue
                try:
                    parse_time(item.get("answered_at",""))
                    if item.get("collected_at") is not None: parse_time(item["collected_at"])
                except (ValueError,TypeError): errors.append(f"{meta_path}: fragment_answers[{index}] 时间戳错误")
        story_path = meta_path.with_name("story.md")
        if not story_path.exists(): errors.append(f"{meta_path}: 缺少 story.md")
        turn_files = meta.get("turn_files", [])
        if meta.get("turn_count") != len(turn_files): errors.append(f"{meta_path}: turn_count 与 turn_files 数量不一致")
        expected_turns = [f"turns/turn-{number:03}.md" for number in range(1, len(turn_files) + 1)]
        if turn_files != expected_turns: errors.append(f"{meta_path}: 回合文件必须从 turn-001.md 连续编号")
        turn_paths = [meta_path.parent / item for item in turn_files]
        for turn_path in turn_paths:
            if not turn_path.is_file(): errors.append(f"{meta_path}: 缺少回合文件 {turn_path.relative_to(meta_path.parent)}")
        combined = meta_path.read_text(encoding="utf-8") + (story_path.read_text(encoding="utf-8") if story_path.exists() else "") + "".join(path.read_text(encoding="utf-8") for path in turn_paths if path.is_file())
        for pattern in FORBIDDEN_PATTERNS:
            if pattern.search(combined): errors.append(f"{meta_path}: 检测到可能的秘密或本地路径")
    if errors:
        print("\n".join(f"ERROR: {error}" for error in errors), file=sys.stderr)
        return 1
    print(f"Validated {len(seen)} stories.")
    return 0

if __name__ == "__main__": raise SystemExit(main())
