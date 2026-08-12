#!/usr/bin/env python3
import argparse
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

def main():
    parser=argparse.ArgumentParser(description="在实际上传前写入现实世界时间戳")
    parser.add_argument("meta")
    args=parser.parse_args(); path=Path(args.meta)
    data=json.loads(path.read_text(encoding="utf-8"))
    data["uploaded_at"]=datetime.now().astimezone().isoformat(timespec="seconds")
    fd,temp=tempfile.mkstemp(prefix=f".{path.name}.",dir=path.parent)
    with os.fdopen(fd,"w",encoding="utf-8") as handle:
        json.dump(data,handle,ensure_ascii=False,indent=2); handle.write("\n")
    os.replace(temp,path)
    print(data["uploaded_at"])
if __name__=="__main__": main()
