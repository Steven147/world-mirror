#!/usr/bin/env python3
import argparse, json, re, sys
from datetime import datetime
from pathlib import Path

def load(path):
    with Path(path).open(encoding="utf-8") as handle: return json.load(handle)

def fail(messages):
    for message in messages: print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(2)

def validate(turn, config):
    errors=[]; label=turn.get("meta",{}).get("label")
    if label not in config["labels"]: return [f"未知 label：{label}"]
    if "state_updates" in turn: errors.append("已接受对话 JSON 不得包含内部 state_updates")
    if type(turn.get("meta",{}).get("turn")) is not int or turn["meta"]["turn"]<0: errors.append("meta.turn 必须是非负整数")
    spec=config["states"][label]
    allowed_keys=set(spec["required"])|set(spec["optional"])|{"progress","answer_record"}
    unexpected=set(turn)-allowed_keys
    if unexpected: errors.append(f"已接受对话 JSON 包含未公开或未知顶层字段：{sorted(unexpected)}")
    for key in spec["required"]:
        if key not in turn or turn[key] in (None,"",[],{}): errors.append(f"{label} 缺少必填区块：{key}")
    for key in spec["forbidden"]:
        if key in turn: errors.append(f"{label} 禁止区块：{key}")
    mirror=turn.get("time",{}).get("mirror","")
    if not re.fullmatch(r"T\+\d{2,}:[0-5]\d:[0-5]\d",mirror): errors.append("镜机时间格式应为 T+HH:MM:SS")
    progress=turn.get("progress")
    if not isinstance(progress,dict) or set(progress)!={"projection_count","core_fragments"}:
        errors.append("已接受对话 JSON 的 progress 必须且只能包含 projection_count 与 core_fragments")
    else:
        if type(progress["projection_count"]) is not int or progress["projection_count"]<0: errors.append("projection_count 必须是非负整数")
        match=re.fullmatch(r"(\d+)/(\d+)",str(progress["core_fragments"]))
        if not match or int(match.group(2))<1 or int(match.group(1))>int(match.group(2)): errors.append("core_fragments 必须是 collected/total 格式、总数为正且收集数不能超过总数")
    answer_record=turn.get("answer_record")
    if answer_record is not None:
        required={"fragment_id","question_id","question_turn","answer_turn","question","answer","passed","answered_at","collected_at"}
        if not isinstance(answer_record,dict) or set(answer_record)!=required:
            errors.append("answer_record 字段不完整")
        elif type(answer_record["question_turn"]) is not int or type(answer_record["answer_turn"]) is not int or answer_record["answer_turn"]!=turn.get("meta",{}).get("turn") or answer_record["question_turn"]>=answer_record["answer_turn"]:
            errors.append("answer_record 的提问回合或作答回合不合法")
        elif type(answer_record["passed"]) is not bool or (answer_record["passed"] and answer_record["collected_at"] is None) or (not answer_record["passed"] and answer_record["collected_at"] is not None):
            errors.append("answer_record 的通过结果与收集时间不一致")
    try:
        real_time=datetime.fromisoformat(turn.get("meta",{}).get("real_time",""))
        if real_time.tzinfo is None: raise ValueError
    except (ValueError,TypeError): errors.append("meta.real_time 必须是带时区的 ISO 8601 时间戳")
    if label=="越界投射":
        options=turn.get("oracle",{}).get("options",[])
        if not any("沉默" in str(item.get("text","")) for item in options if isinstance(item,dict)): errors.append("越界投射必须包含沉默选项")
    return errors

LABELS={"mirror":"镜机纪时","local":"当地时间","elapsed":"本轮流逝","projection_count":"投射次数","core_fragments":"核心碎片","result":"判定","explanation":"说明","turns":"总回合"}
def render_value(value):
    if isinstance(value,str): return [value]
    if isinstance(value,list): return [f"- {item}" for item in value]
    if isinstance(value,dict): return [f"- {LABELS.get(key,key)}：{item}" for key,item in value.items()]
    return [str(value)]

def render(turn,titles):
    meta=turn["meta"]; out=[f"# 世界之镜 · 第 {meta['turn']} 回合","",f"> 当前阶段：{meta['label']}",f"> 现实时间：{meta['real_time']}",f"> 本局样式：{meta.get('style','默认')}"]
    order=["time","progress","time_jump","creator","oracle","resolution","mirror_change","collection","history","completion","fragments","echoes","statistics","actions","prompt"]
    for key in order:
        if key not in turn: continue
        out += ["",f"## {titles.get(key,key)}",""]
        value=turn[key]
        if key in {"oracle","collection"} and isinstance(value,dict):
            if value.get("raw_signal"): out.extend(str(x) for x in value["raw_signal"]); out.append("")
            question=value.get("translated") or value.get("text")
            if question: out.append(f"> {question}")
            if value.get("options"): out += [""]+[f"- {x['id']}. {x['text']}" for x in value["options"]]
        else: out.extend(render_value(value))
    return "\n".join(out).rstrip()+"\n"

def main():
    parser=argparse.ArgumentParser(description="从已接受对话 JSON 渲染世界之镜 Markdown"); parser.add_argument("--turn",required=True); parser.add_argument("--config",required=True)
    args=parser.parse_args(); turn,config=load(args.turn),load(args.config)
    errors=validate(turn,config)
    if errors: fail(errors)
    sys.stdout.write(render(turn,config["section_titles"]))
if __name__=="__main__": main()
