#!/usr/bin/env python3
import argparse
import importlib.util
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

RENDER_PATH = Path(__file__).with_name("render_turn.py")
RENDER_SPEC = importlib.util.spec_from_file_location("world_mirror_render_turn", RENDER_PATH)
render_turn = importlib.util.module_from_spec(RENDER_SPEC)
RENDER_SPEC.loader.exec_module(render_turn)

EXIT_REJECTED = 2

def load(path):
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)

def reject(messages):
    for message in messages:
        print(f"REJECTED: {message}")
    raise SystemExit(EXIT_REJECTED)

def atomic_write(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)

def atomic_write_text(path, value):
    target=Path(path); target.parent.mkdir(parents=True,exist_ok=True)
    fd,temporary=tempfile.mkstemp(prefix=f".{target.name}.",dir=target.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as handle: handle.write(value)
        os.replace(temporary,target)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)

def prepare_json(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return target, Path(temporary)

def prepare_text(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(value)
    return target, Path(temporary)

def commit_accepted_turn(dialogue_path, accepted_turn, state_path, next_state, markdown_path=None, markdown=None):
    """Prepare every artifact first, then use save.json as the commit marker."""
    prepared = [prepare_json(dialogue_path, accepted_turn)]
    if markdown_path is not None:
        prepared.append(prepare_text(markdown_path, markdown))
    prepared.append(prepare_json(state_path, next_state))
    try:
        for target, temporary in prepared[:-1]:
            os.replace(temporary, target)
        state_target, state_temporary = prepared[-1]
        os.replace(state_temporary, state_target)
    finally:
        for _, temporary in prepared:
            if temporary.exists():
                temporary.unlink()

def collected_core_fragment_ids(state, game):
    passed = {
        item.get("fragment_id")
        for item in state.get("fragment_answers", [])
        if isinstance(item, dict) and item.get("passed") is True
    }
    return [item for item in game["required_core_fragments"] if item in passed]

def all_fragments_connected(state, game):
    return len(collected_core_fragment_ids(state, game)) == len(game["required_core_fragments"])

def all_claims_verified(state, game):
    return all(state.get("claims", {}).get(item) is True for item in game["completion_claims"])

def next_unconnected_fragment(state, game):
    collected = set(collected_core_fragment_ids(state, game))
    return next((item for item in game["required_core_fragments"] if item not in collected), None)

def collected_question_ids(state, questions):
    fragment_questions = {
        item.get("fragment"): item.get("id")
        for item in questions.get("questions", [])
    }
    return {
        item.get("question_id") or fragment_questions.get(item.get("fragment_id"))
        for item in state.get("fragment_answers", [])
        if isinstance(item, dict) and item.get("passed") is True
    }

def configured_question_order(state, questions):
    configured = [item.get("id") for item in questions.get("questions", [])]
    preferred = state.get("profile", {}).get("question_order", [])
    if not isinstance(preferred, list):
        preferred = []
    ordered = []
    for question_id in [*preferred, *configured]:
        if question_id in configured and question_id not in ordered:
            ordered.append(question_id)
    return ordered

def next_available_question_id(state, questions):
    collected = collected_question_ids(state, questions)
    by_id = {item.get("id"): item for item in questions.get("questions", [])}
    for question_id in configured_question_order(state, questions):
        question = by_id[question_id]
        if question_id in collected:
            continue
        if all(item in collected for item in question.get("prerequisites", [])):
            return question_id
    return None

def build_accepted_turn(candidate, next_state, game):
    accepted=json.loads(json.dumps(candidate,ensure_ascii=False))
    updates = accepted.pop("state_updates", {})
    collected=len(collected_core_fragment_ids(next_state,game))
    total=len(game["required_core_fragments"])
    accepted["progress"]={
        "projection_count":next_state.get("projection_count",0),
        "core_fragments":f"{collected}/{total}",
    }
    if updates.get("fragment_answer"):
        accepted["answer_record"]=next_state["fragment_answers"][-1]
    return accepted

def parse_real_time(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None: raise ValueError("timezone required")
    return parsed

def question_by_id(questions, question_id):
    return next((item for item in questions.get("questions",[]) if item.get("id")==question_id),None)

def answer_is_correct(answer, question):
    normalized=answer.strip().casefold()
    correct_id=str(question["answer"])
    correct_text=str(question.get("options",{}).get(correct_id,""))
    return normalized in {correct_id.casefold(),correct_text.strip().casefold()}

def collection_matches_question(collection, question):
    expected_options=[{"id":key,"text":value} for key,value in question.get("options",{}).items()]
    return (
        collection.get("question_id")==question.get("id")
        and collection.get("fragment_id")==question.get("fragment")
        and collection.get("text")==question.get("text")
        and collection.get("options")==expected_options
    )

def validate(previous, candidate, state, layout, game, questions):
    errors = []
    labels = set(layout["labels"])
    previous_label = previous.get("meta", {}).get("label")
    candidate_label = candidate.get("meta", {}).get("label")
    previous_turn = previous.get("meta", {}).get("turn")
    candidate_turn = candidate.get("meta", {}).get("turn")
    candidate_real_time = candidate.get("meta", {}).get("real_time")

    if state.get("completed") is True:
        errors.append("本局已经通关，不再接受新游戏回合")
    if "progress" in candidate:
        errors.append("候选回合不得提供 progress；投射次数与核心碎片进度由脚本根据存档生成")
    if previous_label not in labels: errors.append(f"上一回合 label 不合法：{previous_label}")
    if candidate_label not in labels: errors.append(f"候选回合 label 不合法：{candidate_label}")
    if state.get("label") != previous_label: errors.append("存档 label 与上一回合不一致")
    if state.get("turn") != previous_turn: errors.append("存档 turn 与上一回合不一致")
    if not isinstance(previous_turn, int) or candidate_turn != previous_turn + 1: errors.append("候选回合号必须是上一回合号加一")
    if candidate_label not in layout.get("transitions", {}).get(previous_label, []):
        errors.append(f"非法状态迁移：{previous_label} → {candidate_label}")
    history_streak = state.get("history_streak", 0)
    history_limit = game.get("max_consecutive_history_turns", 3)
    if previous_label == "自由追溯历史" and candidate_label == "自由追溯历史" and history_streak >= history_limit:
        errors.append(f"自由追溯历史最多连续 {history_limit} 回合，下一状态必须是越界投射")
    try:
        current_time=parse_real_time(candidate_real_time)
        previous_time=parse_real_time(previous.get("meta",{}).get("real_time"))
        if current_time < previous_time: errors.append("候选回合现实时间不能早于上一回合")
    except (ValueError,TypeError): errors.append("每个回合 meta.real_time 必须是带时区的 ISO 8601 时间戳")

    spec = layout.get("states", {}).get(candidate_label, {})
    allowed_candidate_keys = set(spec.get("required", [])) | set(spec.get("optional", [])) | {"state_updates"}
    unexpected_candidate_keys = set(candidate) - allowed_candidate_keys
    if unexpected_candidate_keys:
        errors.append(f"候选回合包含未公开或未知顶层字段：{sorted(unexpected_candidate_keys)}")
    for key in spec.get("required", []):
        if key not in candidate or candidate[key] in (None, "", [], {}): errors.append(f"{candidate_label} 缺少必填区块：{key}")
    for key in spec.get("forbidden", []):
        if key in candidate: errors.append(f"{candidate_label} 禁止区块：{key}")

    if candidate_label == "收集碎片":
        collection=candidate.get("collection",{})
        fragment_id=collection.get("fragment_id") if isinstance(collection,dict) else None
        question_id=collection.get("question_id") if isinstance(collection,dict) else None
        question=question_by_id(questions,question_id)
        if fragment_id not in game["required_core_fragments"]:
            errors.append("收集碎片回合必须通过 collection.fragment_id 绑定一个核心碎片")
        elif fragment_id in collected_core_fragment_ids(state,game):
            errors.append(f"不能再次提问已经收集的核心碎片：{fragment_id}")
        if question is None:
            errors.append("收集碎片回合必须通过 collection.question_id 绑定 data/questions.json 中的问题")
        elif not collection_matches_question(collection,question):
            errors.append("collection 的问题、选项、核心碎片与 questions.json 不一致")
        previous_fragment=previous.get("collection",{}).get("fragment_id") if isinstance(previous.get("collection"),dict) else None
        if previous_label=="收集碎片" and previous_fragment and fragment_id!=previous_fragment:
            errors.append("回答未通过时必须继续当前核心碎片问题")
        elif previous_label != "收集碎片":
            expected_question_id = next_available_question_id(state, questions)
            if question_id != expected_question_id:
                errors.append(f"必须按本局题序与先修条件提出下一个问题：{expected_question_id}")

    updates = candidate.get("state_updates", {})
    allowed_update_keys = {"fragment_answer", "skip_collection"} if previous_label == "收集碎片" else ({"claims"} if previous_label == "通关结算" else set())
    extra = set(updates) - allowed_update_keys
    if extra: errors.append(f"{previous_label} 不允许状态更新：{sorted(extra)}")
    return errors

def apply_updates(previous, candidate, state, layout, game, questions):
    next_state = json.loads(json.dumps(state, ensure_ascii=False))
    previous_label = previous["meta"]["label"]
    requested_label = candidate["meta"]["label"]
    updates = candidate.get("state_updates", {})

    if previous_label == "收集碎片" and "skip_collection" in updates:
        skip=updates["skip_collection"]
        if set(skip)!={"reason","next_fragment_id"} or skip.get("reason")!="no_new_core_concept":
            reject(["skip_collection 必须声明 reason=no_new_core_concept 与 next_fragment_id"])
        expected_target=next_unconnected_fragment(next_state,game)
        if skip.get("next_fragment_id")!=expected_target:
            reject([f"跳过后必须前往下一个未连接核心碎片：{expected_target}"])
        if requested_label!="越界投射": reject(["跳过收集碎片后必须直接进入越界投射"])
        if "fragment_answer" in updates: reject(["跳过收集碎片时不能记录问答"])
        jump=candidate.get("time_jump")
        required_jump={"target_fragment_id","target_concept","elapsed","from_event","to_event"}
        if not isinstance(jump,dict) or set(jump)!=required_jump: reject(["跳过后的越界投射必须提供完整 time_jump"])
        if jump.get("target_fragment_id")!=expected_target: reject(["time_jump 目标碎片与跳过目标不一致"])
        if not all(isinstance(jump.get(key),str) and jump[key].strip() for key in ("target_concept","elapsed","from_event","to_event")): reject(["time_jump 的概念、流逝量和前后事件不能为空"])
        next_state["last_skip"]={"at":candidate["meta"]["real_time"],"target_fragment_id":expected_target,"time_jump":jump}
    elif previous_label == "收集碎片" and requested_label == "越界投射":
        reject(["收集碎片直接进入越界投射时必须提供 skip_collection"])

    if previous_label == "收集碎片" and "fragment_answer" in updates:
        answer=updates["fragment_answer"]
        if not isinstance(answer,dict) or set(answer)!={"answer","answered_at"}:
            reject(["fragment_answer 必须且只能包含 answer 与 answered_at；是否通过由脚本判定"])
        collection=previous.get("collection",{})
        fragment_id=collection.get("fragment_id")
        question_id=collection.get("question_id")
        question=collection.get("text")
        question_config=question_by_id(questions,question_id)
        if fragment_id not in game["required_core_fragments"]:
            reject(["上一回合 collection.fragment_id 必须是已配置的核心碎片"])
        if question_config is None or not collection_matches_question(collection,question_config):
            reject(["上一回合 collection 与 questions.json 不一致"])
        if not isinstance(question,str) or not question.strip():
            reject(["上一回合 collection.text 不能为空"])
        if not isinstance(answer.get("answer"),str) or not answer["answer"].strip():
            reject(["fragment_answer.answer 不能为空"])
        try: answered_at=parse_real_time(answer.get("answered_at"))
        except (ValueError,TypeError): reject(["fragment_answer.answered_at 必须是带时区的 ISO 8601 时间戳"])
        question_time=parse_real_time(previous["meta"]["real_time"])
        turn_time=parse_real_time(candidate["meta"]["real_time"])
        if answered_at < question_time: reject(["碎片回答时间不能早于提问回合现实时间"])
        if answered_at > turn_time: reject(["碎片回答时间不能晚于当前回合现实时间"])
        passed=answer_is_correct(answer["answer"],question_config)
        already_collected=fragment_id in collected_core_fragment_ids(next_state,game)
        if passed and already_collected:
            reject([f"核心碎片已经收集，不能重复计数：{fragment_id}"])
        if passed and requested_label=="收集碎片":
            reject(["回答成功后不能停留在收集碎片"])
        if not passed and requested_label!="收集碎片":
            reject(["回答未通过时必须停留在收集碎片"])
        record={
            "fragment_id":fragment_id,
            "question_id":question_id,
            "question_turn":previous["meta"]["turn"],
            "answer_turn":candidate["meta"]["turn"],
            "question":question,
            "answer":answer["answer"],
            "passed":passed,
            "answered_at":answer["answered_at"],
            "collected_at":candidate["meta"]["real_time"] if passed else None,
        }
        next_state.setdefault("fragment_answers",[]).append(record)
        if passed:
            next_state.setdefault("fragments",{})[fragment_id]="connected"
    elif previous_label == "收集碎片" and "skip_collection" not in updates:
        reject(["收集碎片作答后必须提供 fragment_answer；成功和失败都会记录"])

    fragments_complete = all_fragments_connected(next_state, game)
    if previous_label == "收集碎片":
        if requested_label == "通关结算" and not fragments_complete:
            reject(["核心碎片尚未全部 connected，不能进入通关结算"])
        if requested_label == "自由追溯历史" and fragments_complete:
            reject(["核心碎片已集齐，必须进入通关结算"])
        if "skip_collection" not in updates and requested_label == "越界投射":
            reject(["没有合法跳过记录，不能直接进入越界投射"])

    if previous_label == "通关结算":
        claims = updates.get("claims", {})
        unknown = set(claims) - set(game["completion_claims"])
        if unknown: reject([f"未知通关主张：{sorted(unknown)}"])
        for claim_id, verified in claims.items():
            if verified is not True: reject([f"主张只能在验证通过时写入 true：{claim_id}"])
            next_state.setdefault("claims", {})[claim_id] = True
        next_state["completed"] = all_claims_verified(next_state, game)

    next_state["label"] = requested_label
    next_state["turn"] = candidate["meta"]["turn"]
    next_state["last_turn_id"] = candidate["meta"].get("id")
    next_state.setdefault("started_at", previous.get("meta",{}).get("real_time"))
    next_state["last_real_time"] = candidate["meta"]["real_time"]
    if requested_label == "自由追溯历史":
        if previous_label == "自由追溯历史":
            next_state["history_streak"] = next_state.get("history_streak", 0) + 1
        else:
            next_state["history_streak"] = 1
    elif requested_label == "越界投射":
        next_state["history_streak"] = 0
        next_state["projection_count"] = next_state.get("projection_count", 0) + 1
    return next_state

def main():
    parser = argparse.ArgumentParser(description="接受或拒绝世界之镜候选回合")
    sub = parser.add_subparsers(dest="command", required=True)
    accept = sub.add_parser("accept")
    for name in ("previous", "candidate", "state", "config", "game-config", "questions", "next-state", "dialogue-output"):
        accept.add_argument(f"--{name}", required=True)
    accept.add_argument("--render", action="store_true", help="接受后直接输出最终 Markdown")
    accept.add_argument("--markdown-output", help="接受后原子保存最终回合 Markdown")
    args = parser.parse_args()
    previous, candidate, state = load(args.previous), load(args.candidate), load(args.state)
    layout, game, questions = load(args.config), load(args.game_config), load(args.questions)
    errors = validate(previous, candidate, state, layout, game, questions)
    if errors: reject(errors)
    next_state = apply_updates(previous, candidate, state, layout, game, questions)
    accepted_turn = build_accepted_turn(candidate, next_state, game)
    render_errors = render_turn.validate(accepted_turn, layout)
    if render_errors:
        reject(render_errors)
    markdown = render_turn.render(accepted_turn, layout["section_titles"])
    markdown_path = args.markdown_output if args.render and args.markdown_output else None
    commit_accepted_turn(
        args.dialogue_output,
        accepted_turn,
        args.next_state,
        next_state,
        markdown_path,
        markdown if markdown_path else None,
    )
    if args.render:
        print(markdown, end="")
    else:
        print(json.dumps({"accepted": True, "turn": next_state["turn"], "label": next_state["label"], "completed": next_state.get("completed", False)}, ensure_ascii=False))

if __name__ == "__main__": main()
