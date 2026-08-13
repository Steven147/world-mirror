#!/usr/bin/env python3
import argparse
import importlib.util
import json
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

RENDER_PATH=Path(__file__).with_name("render_turn.py")
RENDER_SPEC=importlib.util.spec_from_file_location("world_mirror_export_render",RENDER_PATH)
render_turn=importlib.util.module_from_spec(RENDER_SPEC); RENDER_SPEC.loader.exec_module(render_turn)
LAYOUT_PATH=Path(__file__).resolve().parents[1]/"configs"/"layouts.json"

ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,79}$")
INDEX_TYPES = {"人物", "概念", "事件", "地点", "物理规律"}
TIME_FIELDS = ("started_at", "completed_at", "exported_at")
LEGACY_ANSWER_FIELDS={"fragment_id","question","answer","passed","answered_at","collected_at"}
ANSWER_FIELDS=LEGACY_ANSWER_FIELDS|{"question_id","question_turn","answer_turn"}
FORBIDDEN_PATTERNS = [
    ("访问令牌", re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}")),
    ("私钥", re.compile(r"BEGIN [A-Z ]*PRIVATE KEY")),
    ("本地绝对路径", re.compile(r"(?:/Users/|/home/|/root/|/var/git/|[A-Za-z]:\\\\Users\\\\)")),
    ("内部状态字段", re.compile(r'"(?:state_updates|session_seed)"\s*:')),
]

def parse_time(value):
    parsed=datetime.fromisoformat(value)
    if parsed.tzinfo is None: raise ValueError("时间戳必须包含时区")
    return parsed

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def semantic_length(text):
    return len(re.findall(r"[\u3400-\u9fffA-Za-z0-9]", text))

def privacy_errors(paths):
    errors=[]
    for path in paths:
        if not path.is_file():
            continue
        text=path.read_text(encoding="utf-8")
        for label,pattern in FORBIDDEN_PATTERNS:
            if pattern.search(text): errors.append(f"{path}: 检测到{label}")
    return errors

def validate_manifest(manifest, turn_paths, dialogue_paths):
    errors=[]
    required={"schema_version","story_id","world_id","title","author","kind","summary","worldview","keywords","characters","concepts","fragment_answers","started_at","completed_at","themes","relations","consent"}
    missing=required-set(manifest)
    if missing: errors.append(f"缺少字段：{sorted(missing)}")
    if not ID_PATTERN.fullmatch(manifest.get("story_id","")): errors.append("story_id 格式错误")
    if semantic_length(manifest.get("summary","")) != 20: errors.append("summary 必须恰好包含 20 个汉字、字母或数字")
    keywords=manifest.get("keywords",[])
    if len(keywords)!=10: errors.append("keywords 必须恰好包含 10 条")
    seen=set()
    for index,item in enumerate(keywords,1):
        if not isinstance(item,dict) or set(item)!={"name","type","description"}: errors.append(f"keywords[{index}] 必须且只能包含 name、type、description"); continue
        if item["type"] not in INDEX_TYPES: errors.append(f"keywords[{index}] type 不合法")
        if not all(isinstance(item[key],str) and item[key].strip() for key in item): errors.append(f"keywords[{index}] 字段不能为空")
        if item.get("name") in seen: errors.append(f"关键词重复：{item.get('name')}")
        seen.add(item.get("name"))
    for field in ("characters","concepts"):
        value=manifest.get(field)
        if not isinstance(value,list) or not value or not all(isinstance(x,str) and x.strip() for x in value): errors.append(f"{field} 必须是非空字符串数组")
    if manifest.get("kind")!="player-story": errors.append("导出包 kind 必须是 player-story")
    if manifest.get("consent",{}).get("public") is not True: errors.append("缺少公开同意")
    try:
        started=parse_time(manifest.get("started_at","")); completed=parse_time(manifest.get("completed_at",""))
        if completed < started: errors.append("completed_at 不能早于 started_at")
    except (ValueError,TypeError): errors.append("started_at 与 completed_at 必须是带时区的 ISO 8601 时间戳")
    answers=manifest.get("fragment_answers",[])
    if not isinstance(answers,list) or not answers: errors.append("fragment_answers 必须是非空数组")
    else:
        for index,item in enumerate(answers,1):
            if not isinstance(item,dict) or frozenset(item) not in {frozenset(LEGACY_ANSWER_FIELDS),frozenset(ANSWER_FIELDS)}: errors.append(f"fragment_answers[{index}] 结构错误"); continue
            if "question_turn" in item and (not isinstance(item["question_turn"],int) or not isinstance(item["answer_turn"],int) or item["answer_turn"]<=item["question_turn"]): errors.append(f"fragment_answers[{index}] 回合记录错误")
            if "question_turn" in item and (type(item.get("passed")) is not bool or (item["passed"] and item["collected_at"] is None) or (not item["passed"] and item["collected_at"] is not None)): errors.append(f"fragment_answers[{index}] 通过结果与收集时间不一致")
            try: parse_time(item["answered_at"])
            except (ValueError,TypeError): errors.append(f"fragment_answers[{index}].answered_at 时间戳错误")
            if item["collected_at"] is not None:
                try: parse_time(item["collected_at"])
                except (ValueError,TypeError): errors.append(f"fragment_answers[{index}].collected_at 时间戳错误")
    if not turn_paths: errors.append("至少需要一个回合 Markdown 文件")
    if not dialogue_paths: errors.append("至少需要一个已接受对话 JSON 文件")
    if len(dialogue_paths)!=len(turn_paths): errors.append("已接受对话 JSON 与回合 Markdown 数量必须一致")
    return errors

def main():
    parser=argparse.ArgumentParser(description="生成世界之镜公开存档包")
    parser.add_argument("--manifest",required=True); parser.add_argument("--story",required=True); parser.add_argument("--dialogue",required=True,nargs="+"); parser.add_argument("--turns",required=True,nargs="+"); parser.add_argument("--output",required=True)
    args=parser.parse_args(); manifest=load(args.manifest); dialogue_paths=[Path(x) for x in args.dialogue]; turn_paths=[Path(x) for x in args.turns]
    errors=validate_manifest(manifest,turn_paths,dialogue_paths)
    for path in [Path(args.story),*dialogue_paths,*turn_paths]:
        if not path.is_file(): errors.append(f"文件不存在：{path}")
    if not errors:
        layout=load(LAYOUT_PATH)
        previous_time=None
        for number,(dialogue_path,turn_path) in enumerate(zip(dialogue_paths,turn_paths),1):
            dialogue=load(dialogue_path)
            if dialogue.get("meta",{}).get("turn")!=number: errors.append(f"已接受对话回合号不连续：{dialogue_path}"); continue
            for error in render_turn.validate(dialogue,layout): errors.append(f"{dialogue_path}: {error}")
            try:
                current_time=parse_time(dialogue.get("meta",{}).get("real_time",""))
                if previous_time is not None and current_time < previous_time: errors.append(f"{dialogue_path}: 回合现实时间倒退")
                previous_time=current_time
            except (ValueError,TypeError): pass
            if render_turn.render(dialogue,layout["section_titles"])!=turn_path.read_text(encoding="utf-8"): errors.append(f"{turn_path}: Markdown 与已接受对话 JSON 渲染结果不一致")
    errors.extend(privacy_errors([Path(args.manifest),Path(args.story),*dialogue_paths,*turn_paths]))
    if errors:
        for error in errors: print(f"ERROR: {error}")
        return 2
    output=Path(args.output); output.parent.mkdir(parents=True,exist_ok=True)
    temporary=Path(tempfile.mkdtemp(prefix=f".{output.name}.",dir=output.parent))
    try:
        turns_dir=temporary/"turns"; turns_dir.mkdir()
        dialogue_dir=temporary/"dialogue"; dialogue_dir.mkdir()
        turn_files=[]; dialogue_files=[]
        for number,(dialogue_path,path) in enumerate(zip(dialogue_paths,turn_paths),1):
            name=f"turn-{number:03}.md"; shutil.copyfile(path,turns_dir/name); turn_files.append(f"turns/{name}")
            dialogue_name=f"turn-{number:03}.json"; shutil.copyfile(dialogue_path,dialogue_dir/dialogue_name); dialogue_files.append(f"dialogue/{dialogue_name}")
        public_meta=dict(manifest); public_meta["turn_count"]=len(turn_files); public_meta["turn_files"]=turn_files; public_meta["dialogue_files"]=dialogue_files
        started=parse_time(public_meta["started_at"]); completed=parse_time(public_meta["completed_at"])
        public_meta["total_play_seconds"]=int((completed-started).total_seconds())
        public_meta["exported_at"]=datetime.now().astimezone().isoformat(timespec="seconds")
        public_meta["uploaded_at"]=None
        (temporary/"meta.json").write_text(json.dumps(public_meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        shutil.copyfile(args.story,temporary/"story.md")
        if output.exists(): raise FileExistsError(f"输出目录已存在：{output}")
        temporary.rename(output)
    except Exception:
        shutil.rmtree(temporary,ignore_errors=True); raise
    print(f"已生成公开存档包：{output}")
    print("上传前请预览 meta.json、story.md、dialogue/ 和 turns/，确认无隐私后再创建 PR。")
    return 0

if __name__=="__main__": raise SystemExit(main())
