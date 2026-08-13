#!/usr/bin/env python3
import argparse
import importlib.util
import json
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RENDER_PATH = Path(__file__).with_name("render_turn.py")
RENDER_SPEC = importlib.util.spec_from_file_location("world_mirror_session_render", RENDER_PATH)
render_turn = importlib.util.module_from_spec(RENDER_SPEC)
RENDER_SPEC.loader.exec_module(render_turn)
TURN_MACHINE_PATH = Path(__file__).with_name("turn_machine.py")
TURN_MACHINE_SPEC = importlib.util.spec_from_file_location("world_mirror_session_machine", TURN_MACHINE_PATH)
turn_machine = importlib.util.module_from_spec(TURN_MACHINE_SPEC)
TURN_MACHINE_SPEC.loader.exec_module(turn_machine)


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def atomic_write_json(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_write_text(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(value)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def question_maps(questions):
    items = questions.get("questions", [])
    return ({item["id"]: item for item in items}, {item["text"]: item for item in items})


def canonical_collection(collection, by_id, by_text):
    question = by_id.get(collection.get("question_id")) or by_text.get(collection.get("text"))
    if question is None:
        raise ValueError(f"题库中找不到问题：{collection.get('text')}")
    return {
        "question_id": question["id"],
        "fragment_id": question["fragment"],
        "text": question["text"],
        "options": [{"id": key, "text": value} for key, value in question["options"].items()],
    }


def canonical_candidate(source, by_id, by_text):
    candidate = json.loads(json.dumps(source, ensure_ascii=False))
    candidate.pop("progress", None)
    candidate.pop("answer_record", None)
    if isinstance(candidate.get("collection"), dict):
        candidate["collection"] = canonical_collection(candidate["collection"], by_id, by_text)
    updates = candidate.get("state_updates")
    if isinstance(updates, dict) and "fragment_answer" in updates:
        old_answer = updates["fragment_answer"]
        updates = {key: value for key, value in updates.items() if key != "fragment"}
        updates["fragment_answer"] = {
            "answer": old_answer["answer"],
            "answered_at": old_answer["answered_at"],
        }
        candidate["state_updates"] = updates
    return candidate


def initial_replay_state(save, bootstrap, game):
    return {
        "game_id": save.get("game_id"),
        "label": bootstrap["meta"]["label"],
        "turn": bootstrap["meta"]["turn"],
        "session_seed": save.get("session_seed"),
        "profile": save.get("profile", {}),
        "fragments": {item: "locked" for item in game["required_core_fragments"]},
        "claims": {item: False for item in game["completion_claims"]},
        "projection_count": bootstrap.get("progress", {}).get("projection_count", 0),
        "started_at": save.get("started_at", bootstrap["meta"]["real_time"]),
        "last_real_time": bootstrap["meta"]["real_time"],
        "fragment_answers": [],
        "history_streak": 0,
        "completed": False,
        "last_turn_id": bootstrap["meta"].get("id"),
    }


def public_payload(turn):
    value = json.loads(json.dumps(turn, ensure_ascii=False))
    value.pop("progress", None)
    value.pop("answer_record", None)
    value.pop("state_updates", None)
    return value


def build_canonical_history(session, questions, game, layout):
    by_id, by_text = question_maps(questions)
    save = load(session / "save.json")
    latest_turn = save["turn"]
    candidates = {}
    legacy_turns = set()
    for turn in range(1, latest_turn + 1):
        name = f"turn-{turn:03}.json"
        current = session / "candidates" / name
        legacy = session / "turn-json" / name
        source = current if current.is_file() else legacy
        if not source.is_file():
            raise ValueError(f"缺少第 {turn} 回合候选 JSON")
        if source == legacy:
            legacy_turns.add(turn)
        candidates[turn] = canonical_candidate(load(source), by_id, by_text)

    bootstrap_path = session / "dialogue" / "turn-000.json"
    if not bootstrap_path.is_file():
        bootstrap_path = session / "bootstrap.json"
    bootstrap = load(bootstrap_path)
    bootstrap["progress"] = {"projection_count": 0, "core_fragments": f"0/{len(game['required_core_fragments'])}"}

    dialogue = {0: bootstrap}
    markdown = {}
    replay_state = initial_replay_state(save, bootstrap, game)
    previous = bootstrap
    for turn in range(1, latest_turn + 1):
        candidate = candidates[turn]
        if candidate["meta"]["turn"] != turn:
            raise ValueError(f"第 {turn} 回合 meta.turn 不一致")
        errors = turn_machine.validate(previous, candidate, replay_state, layout, game, questions)
        if errors:
            raise ValueError(f"第 {turn} 回合未通过状态机重放：{'；'.join(errors)}")
        try:
            replay_state = turn_machine.apply_updates(
                previous, candidate, replay_state, layout, game, questions
            )
        except SystemExit as exc:
            raise ValueError(f"第 {turn} 回合状态更新被拒绝") from exc
        accepted = turn_machine.build_accepted_turn(candidate, replay_state, game)
        errors = render_turn.validate(accepted, layout)
        if errors:
            raise ValueError(f"第 {turn} 回合不符合当前渲染协议：{'；'.join(errors)}")
        dialogue[turn] = accepted
        markdown[turn] = render_turn.render(accepted, layout["section_titles"])
        previous = accepted

    for field in ("label", "turn", "projection_count", "completed"):
        if save.get(field) != replay_state.get(field):
            raise ValueError(f"save.json 的 {field} 与逐回合重放结果不一致")
    return candidates, dialogue, markdown, replay_state, legacy_turns


def main():
    parser = argparse.ArgumentParser(description="把旧世界之镜 session 收敛到 candidates/dialogue/save.json 最新结构")
    parser.add_argument("--session", required=True)
    parser.add_argument("--apply", action="store_true", help="验证通过后原子写入规范化文件；默认只检查")
    parser.add_argument("--game-config", default=str(ROOT / "configs" / "game.json"))
    parser.add_argument("--questions", default=str(ROOT / "data" / "questions.json"))
    parser.add_argument("--layout", default=str(ROOT / "configs" / "layouts.json"))
    args = parser.parse_args()
    session = Path(args.session).resolve()
    save_path = session / "save.json"
    save_snapshot = save_path.read_bytes()
    game, questions, layout = load(args.game_config), load(args.questions), load(args.layout)
    candidates, dialogue, markdown, normalized_save, legacy_turns = build_canonical_history(
        session, questions, game, layout
    )

    latest_turn = normalized_save["turn"]
    normalization_turns = []
    for turn in range(1, latest_turn + 1):
        existing_dialogue = session / "dialogue" / f"turn-{turn:03}.json"
        existing_markdown = session / "turns" / f"turn-{turn:03}.md"
        if existing_dialogue.is_file():
            existing = load(existing_dialogue)
            if public_payload(existing) != public_payload(dialogue[turn]):
                raise ValueError(f"现有 dialogue/turn-{turn:03}.json 的公开内容与候选历史不一致")
            if existing != dialogue[turn]:
                normalization_turns.append(turn)
        elif turn not in legacy_turns:
            raise ValueError(f"缺少现有 dialogue/turn-{turn:03}.json")
        if existing_markdown.is_file() and existing_markdown.read_text(encoding="utf-8") != markdown[turn]:
            normalization_turns.append(turn)

    legacy_entries = [
        path.name
        for path in (
            session / "turn-json",
            session / "bootstrap.json",
            session / "save.bootstrap.json",
        )
        if path.exists()
    ]
    if args.apply:
        if save_path.read_bytes() != save_snapshot:
            raise RuntimeError("检查期间 save.json 已被新回合更新，请重新运行迁移")
        for turn in range(1, latest_turn + 1):
            atomic_write_json(session / "candidates" / f"turn-{turn:03}.json", candidates[turn])
        for turn in range(0, latest_turn + 1):
            atomic_write_json(session / "dialogue" / f"turn-{turn:03}.json", dialogue[turn])
        for turn in range(1, latest_turn + 1):
            atomic_write_text(session / "turns" / f"turn-{turn:03}.md", markdown[turn])
        if save_path.read_bytes() != save_snapshot:
            raise RuntimeError("写入历史期间 save.json 已被新回合更新；历史已补齐，请重新运行迁移")
        atomic_write_json(save_path, normalized_save)
        print(f"已迁移：{session}")
    else:
        if legacy_turns or normalization_turns:
            status = "可迁移"
        elif legacy_entries:
            status = "数据已迁移，可清理旧入口"
        else:
            status = "已是最新结构"
        print(f"检查通过，{status}：{session}")
    print(f"规范化范围：turn-000…turn-{latest_turn:03}")
    print(f"核心碎片：{dialogue[latest_turn]['progress']['core_fragments']}")
    if normalization_turns:
        print(f"需规范化权威回合：{len(set(normalization_turns))}")
    if legacy_entries:
        print(f"迁移后可移入废纸篓：{'、'.join(legacy_entries)}")
    else:
        print("未发现旧版 session 入口")


if __name__ == "__main__":
    main()
