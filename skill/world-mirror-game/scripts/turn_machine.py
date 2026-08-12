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

def all_fragments_connected(state, game):
    return all(state.get("fragments", {}).get(item) == "connected" for item in game["required_core_fragments"])

def all_claims_verified(state, game):
    return all(state.get("claims", {}).get(item) is True for item in game["completion_claims"])

def connected_fragment_count(state, game):
    return sum(state.get("fragments", {}).get(item) == "connected" for item in game["required_core_fragments"])

def next_unconnected_fragment(state, game):
    return next((item for item in game["required_core_fragments"] if state.get("fragments", {}).get(item) != "connected"), None)

def expected_progress(state, game):
    return {
        "projection_count": state.get("projection_count", 0),
        "fragment_count": connected_fragment_count(state, game),
    }

def parse_real_time(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None: raise ValueError("timezone required")
    return parsed

def advance_fragment(current, requested, order):
    if current not in order or requested not in order: return False
    return order.index(requested) == order.index(current) + 1

def validate(previous, candidate, state, layout, game):
    errors = []
    labels = set(layout["labels"])
    previous_label = previous.get("meta", {}).get("label")
    candidate_label = candidate.get("meta", {}).get("label")
    previous_turn = previous.get("meta", {}).get("turn")
    candidate_turn = candidate.get("meta", {}).get("turn")
    candidate_real_time = candidate.get("meta", {}).get("real_time")

    if state.get("completed") is True:
        errors.append("本局已经通关，不再接受新游戏回合")
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
    for key in spec.get("required", []):
        if key not in candidate or candidate[key] in (None, "", [], {}): errors.append(f"{candidate_label} 缺少必填区块：{key}")
    for key in spec.get("forbidden", []):
        if key in candidate: errors.append(f"{candidate_label} 禁止区块：{key}")

    updates = candidate.get("state_updates", {})
    allowed_update_keys = {"fragment", "fragment_answer", "skip_collection"} if previous_label == "收集碎片" else ({"claims"} if previous_label == "通关结算" else set())
    extra = set(updates) - allowed_update_keys
    if extra: errors.append(f"{previous_label} 不允许状态更新：{sorted(extra)}")
    return errors

def apply_updates(previous, candidate, state, layout, game):
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
        if "fragment" in updates or "fragment_answer" in updates: reject(["跳过收集碎片时不能更新碎片或记录问答"])
        jump=candidate.get("time_jump")
        required_jump={"target_fragment_id","target_concept","elapsed","from_event","to_event"}
        if not isinstance(jump,dict) or set(jump)!=required_jump: reject(["跳过后的越界投射必须提供完整 time_jump"])
        if jump.get("target_fragment_id")!=expected_target: reject(["time_jump 目标碎片与跳过目标不一致"])
        if not all(isinstance(jump.get(key),str) and jump[key].strip() for key in ("target_concept","elapsed","from_event","to_event")): reject(["time_jump 的概念、流逝量和前后事件不能为空"])
        next_state["last_skip"]={"at":candidate["meta"]["real_time"],"target_fragment_id":expected_target,"time_jump":jump}
    elif previous_label == "收集碎片" and requested_label == "越界投射":
        reject(["收集碎片直接进入越界投射时必须提供 skip_collection"])

    if previous_label == "收集碎片" and "fragment" in updates:
        fragment = updates["fragment"]
        fragment_id = fragment.get("id")
        requested_status = fragment.get("status")
        if fragment_id not in game["required_core_fragments"]:
            reject([f"未知核心碎片：{fragment_id}"])
        current_status = next_state.get("fragments", {}).get(fragment_id, "locked")
        if not advance_fragment(current_status, requested_status, game["fragment_status_order"]):
            reject([f"碎片只能前进一个阶段：{fragment_id} {current_status} → {requested_status}"])
        next_state.setdefault("fragments", {})[fragment_id] = requested_status
        answer=updates.get("fragment_answer")
        if not isinstance(answer,dict) or set(answer)!={"fragment_id","question","answer","passed","answered_at"}:
            reject(["碎片状态前进时必须提供完整 fragment_answer"])
        if answer.get("fragment_id") != fragment_id or answer.get("passed") is not True:
            reject(["fragment_answer 必须对应当前碎片且 passed=true"])
        try: answered_at=parse_real_time(answer.get("answered_at"))
        except (ValueError,TypeError): reject(["fragment_answer.answered_at 必须是带时区的 ISO 8601 时间戳"])
        turn_time=parse_real_time(candidate["meta"]["real_time"])
        if answered_at > turn_time: reject(["碎片回答时间不能晚于当前回合现实时间"])
        record=dict(answer)
        record["collected_at"]=candidate["meta"]["real_time"] if requested_status=="connected" else None
        next_state.setdefault("fragment_answers",[]).append(record)
    elif previous_label == "收集碎片" and "fragment_answer" in updates:
        reject(["fragment_answer 不能脱离 fragment 更新单独出现"])

    fragments_complete = all_fragments_connected(next_state, game)
    if previous_label == "收集碎片":
        if requested_label == "通关结算" and not fragments_complete:
            reject(["核心碎片尚未全部 connected，不能进入通关结算"])
        if requested_label == "自由追溯历史" and fragments_complete:
            reject(["核心碎片已集齐，必须进入通关结算"])
        if requested_label == "收集碎片" and updates.get("fragment"):
            reject(["碎片问题已通过，不能停留在收集碎片"])
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
    for name in ("previous", "candidate", "state", "config", "game-config", "next-state"):
        accept.add_argument(f"--{name}", required=True)
    accept.add_argument("--render", action="store_true", help="接受后直接输出最终 Markdown")
    accept.add_argument("--markdown-output", help="接受后原子保存最终回合 Markdown")
    args = parser.parse_args()
    previous, candidate, state = load(args.previous), load(args.candidate), load(args.state)
    layout, game = load(args.config), load(args.game_config)
    errors = validate(previous, candidate, state, layout, game)
    if errors: reject(errors)
    next_state = apply_updates(previous, candidate, state, layout, game)
    progress = candidate.get("progress")
    expected = expected_progress(next_state, game)
    if not isinstance(progress, dict) or set(progress) != set(expected):
        reject(["progress 必须且只能包含 projection_count 与 fragment_count"])
    if progress != expected:
        reject([f"progress 与状态机计算不一致：应为 {expected}，实际为 {progress}"])
    if args.render:
        render_errors = render_turn.validate(candidate, next_state, layout)
        if render_errors:
            reject(render_errors)
        markdown = render_turn.render(candidate, layout["section_titles"])
        atomic_write(args.next_state, next_state)
        if args.markdown_output: atomic_write_text(args.markdown_output,markdown)
        print(markdown, end="")
    else:
        atomic_write(args.next_state, next_state)
        print(json.dumps({"accepted": True, "turn": next_state["turn"], "label": next_state["label"], "completed": next_state.get("completed", False)}, ensure_ascii=False))

if __name__ == "__main__": main()
