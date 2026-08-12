#!/usr/bin/env python3
import argparse
import json
import os
import tempfile
from pathlib import Path

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

def all_fragments_connected(state, game):
    return all(state.get("fragments", {}).get(item) == "connected" for item in game["required_core_fragments"])

def all_claims_verified(state, game):
    return all(state.get("claims", {}).get(item) is True for item in game["completion_claims"])

def connected_fragment_count(state, game):
    return sum(state.get("fragments", {}).get(item) == "connected" for item in game["required_core_fragments"])

def expected_progress(state, game):
    return {
        "projection_count": state.get("projection_count", 0),
        "fragment_count": connected_fragment_count(state, game),
    }

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

    spec = layout.get("states", {}).get(candidate_label, {})
    for key in spec.get("required", []):
        if key not in candidate or candidate[key] in (None, "", [], {}): errors.append(f"{candidate_label} 缺少必填区块：{key}")
    for key in spec.get("forbidden", []):
        if key in candidate: errors.append(f"{candidate_label} 禁止区块：{key}")

    updates = candidate.get("state_updates", {})
    allowed_update_keys = {"fragment"} if previous_label == "收集碎片" else ({"claims"} if previous_label == "通关结算" else set())
    extra = set(updates) - allowed_update_keys
    if extra: errors.append(f"{previous_label} 不允许状态更新：{sorted(extra)}")
    return errors

def apply_updates(previous, candidate, state, layout, game):
    next_state = json.loads(json.dumps(state, ensure_ascii=False))
    previous_label = previous["meta"]["label"]
    requested_label = candidate["meta"]["label"]
    updates = candidate.get("state_updates", {})

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

    fragments_complete = all_fragments_connected(next_state, game)
    if previous_label == "收集碎片":
        if requested_label == "通关结算" and not fragments_complete:
            reject(["核心碎片尚未全部 connected，不能进入通关结算"])
        if requested_label == "自由追溯历史" and fragments_complete:
            reject(["核心碎片已集齐，必须进入通关结算"])
        if requested_label == "收集碎片" and updates.get("fragment"):
            reject(["碎片问题已通过，不能停留在收集碎片"])

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
    atomic_write(args.next_state, next_state)
    print(json.dumps({"accepted": True, "turn": next_state["turn"], "label": next_state["label"], "completed": next_state.get("completed", False)}, ensure_ascii=False))

if __name__ == "__main__": main()
