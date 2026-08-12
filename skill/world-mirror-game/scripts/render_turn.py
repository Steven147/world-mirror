#!/usr/bin/env python3
import argparse, json, re, sys
from pathlib import Path

def load(path):
    with Path(path).open(encoding="utf-8") as handle: return json.load(handle)

def fail(messages):
    for message in messages: print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(2)

def validate(turn, state, config):
    errors=[]; label=turn.get("meta",{}).get("label")
    if label not in config["labels"]: return [f"未知 label：{label}"]
    if label != state.get("label"): errors.append("回合 label 与已接受的新存档不一致")
    if turn.get("meta",{}).get("turn") != state.get("turn"): errors.append("回合号与已接受的新存档不一致")
    spec=config["states"][label]
    for key in spec["required"]:
        if key not in turn or turn[key] in (None,"",[],{}): errors.append(f"{label} 缺少必填区块：{key}")
    for key in spec["forbidden"]:
        if key in turn: errors.append(f"{label} 禁止区块：{key}")
    mirror=turn.get("time",{}).get("mirror","")
    if not re.fullmatch(r"T\+\d{2,}:[0-5]\d:[0-5]\d",mirror): errors.append("镜机时间格式应为 T+HH:MM:SS")
    if label=="越界投射":
        options=turn.get("oracle",{}).get("options",[])
        if not any("沉默" in str(item.get("text","")) for item in options if isinstance(item,dict)): errors.append("越界投射必须包含沉默选项")
    return errors

LABELS={"mirror":"镜机纪时","local":"当地时间","elapsed":"本轮流逝","fragments":"碎片进度","connected":"已连接","total":"总数","result":"判定","explanation":"说明","turns":"总回合"}
def render_value(value):
    if isinstance(value,str): return [value]
    if isinstance(value,list): return [f"- {item}" for item in value]
    if isinstance(value,dict): return [f"- {LABELS.get(key,key)}：{item}" for key,item in value.items()]
    return [str(value)]

def render(turn,titles):
    meta=turn["meta"]; out=[f"# 世界之镜 · 第 {meta['turn']} 回合","",f"> 当前阶段：{meta['label']}",f"> 本局样式：{meta.get('style','默认')}"]
    order=["time","progress","creator","oracle","resolution","mirror_change","collection","history","completion","fragments","echoes","statistics","actions","prompt"]
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
    parser=argparse.ArgumentParser(); parser.add_argument("--turn",required=True); parser.add_argument("--state",required=True); parser.add_argument("--config",required=True)
    args=parser.parse_args(); turn,state,config=load(args.turn),load(args.state),load(args.config)
    errors=validate(turn,state,config)
    if errors: fail(errors)
    sys.stdout.write(render(turn,config["section_titles"]))
if __name__=="__main__": main()
