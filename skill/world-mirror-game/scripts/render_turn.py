#!/usr/bin/env python3
import argparse
import json
import re
import sys
from pathlib import Path

STATES = {"CREATOR_QUESTION", "ANSWER_RESOLUTION", "WORLD_REVELATION", "FREE_INVESTIGATION", "ORACLE_QUESTION", "ORACLE_RESOLUTION", "FINAL_RECONSTRUCTION", "COMPLETED"}

def load(path):
    with Path(path).open(encoding="utf-8") as f:
        return json.load(f)

def fail(messages):
    for message in messages:
        print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(2)

def validate(turn, state, config):
    errors = []
    current = turn.get("meta", {}).get("state")
    if current not in STATES:
        errors.append(f"未知状态: {current}")
        return errors
    spec = config["states"][current]
    for key in spec["required"]:
        if key not in turn or turn[key] in (None, "", [], {}): errors.append(f"{current} 缺少必填区块: {key}")
    for key in spec["forbidden"]:
        if key in turn: errors.append(f"{current} 禁止区块: {key}")
    if turn.get("meta", {}).get("turn") != state.get("turn"):
        errors.append("turn.meta.turn 必须等于存档 turn")
    if current != state.get("state"):
        errors.append("回合状态必须与存档状态一致")
    mirror = turn.get("time", {}).get("mirror", "")
    if not re.fullmatch(r"T\+\d{2,}:[0-5]\d:[0-5]\d", mirror):
        errors.append("镜机时间格式应为 T+HH:MM:SS")
    if "progress" in turn:
        p = turn["progress"]
        if p.get("correct") != state.get("quiz", {}).get("correct"): errors.append("正确题数与存档不一致")
        if p.get("threshold") != state.get("quiz", {}).get("threshold"): errors.append("显现阈值与存档不一致")
    if current == "CREATOR_QUESTION":
        opts = turn.get("question", {}).get("options", [])
        ids = [o.get("id") for o in opts if isinstance(o, dict)]
        if len(opts) < 2: errors.append("创造者问题至少需要两个选项")
        if len(ids) != len(set(ids)): errors.append("问题选项 ID 必须唯一")
    if current == "ORACLE_QUESTION":
        opts = turn.get("oracle", {}).get("options", [])
        if not any("沉默" in str(o.get("text", "")) for o in opts if isinstance(o, dict)):
            errors.append("镜谕问题必须提供沉默选项")
    if current == "WORLD_REVELATION" and state.get("quiz", {}).get("correct", 0) < state.get("quiz", {}).get("threshold", 5):
        errors.append("尚未达到世界显现阈值")
    if current == "FINAL_RECONSTRUCTION" and not state.get("final_reconstruction_available", False):
        errors.append("核心碎片尚未全部连接，不能最终重建")
    if current == "COMPLETED" and not state.get("completion_verified", False):
        errors.append("通关主张尚未通过确定性判定")
    return errors

def lines(value):
    if isinstance(value, str): return [value]
    if isinstance(value, list): return [str(x) for x in value]
    if isinstance(value, dict): return [f"- {k}：{v}" for k, v in value.items()]
    return [str(value)]

FIELD_LABELS = {
    "mirror": "镜机纪时", "local": "当地时间", "elapsed": "本轮流逝",
    "correct": "正确回答", "threshold": "显现阈值", "fragments": "碎片进度",
    "result": "判定", "explanation": "说明", "unlocked": "解锁",
    "turns": "总回合", "questions": "问答数", "oracle_answers": "镜谕回答"
}

def render_dict(value):
    return [f"- {FIELD_LABELS.get(k, k)}：{v}" for k, v in value.items()]

def render(turn, titles):
    meta = turn["meta"]
    out = [f"# 世界之镜 · 第 {meta['turn']} 回合", "", f"> 当前阶段：{meta.get('label', meta['state'])}", f"> 本局样式：{meta.get('style', '默认')}" ]
    order = ["time","progress","creator","question","resolution","mirror_change","revelation","investigation","oracle","mysteries","fragments","echoes","reconstruction","completion","statistics","actions","prompt"]
    for key in order:
        if key not in turn: continue
        out += ["", f"## {titles.get(key, key)}", ""]
        value = turn[key]
        if key in {"question", "oracle"} and isinstance(value, dict):
            if value.get("raw_signal"):
                out.extend(str(x) for x in value["raw_signal"]); out.append("")
            if value.get("text"): out.append(f"> {value['text']}")
            if value.get("translated"): out.append(f"> {value['translated']}")
            if value.get("options"):
                out.append("")
                out.extend(f"- {x['id']}. {x['text']}" for x in value["options"])
        elif key in {"actions", "mysteries", "echoes", "fragments"} and isinstance(value, list):
            out.extend(f"- {x}" for x in value)
        elif isinstance(value, dict):
            out.extend(render_dict(value))
        else:
            out.extend(lines(value))
    return "\n".join(out).rstrip() + "\n"

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--turn", required=True); p.add_argument("--state", required=True); p.add_argument("--config", required=True)
    a = p.parse_args(); turn, state, config = load(a.turn), load(a.state), load(a.config)
    errors = validate(turn, state, config)
    if errors: fail(errors)
    sys.stdout.write(render(turn, config.get("section_titles", {})))

if __name__ == "__main__": main()
