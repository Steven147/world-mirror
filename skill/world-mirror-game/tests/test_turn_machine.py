#!/usr/bin/env python3
import importlib.util
import json
import tempfile
import unittest
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("turn_machine",ROOT/"scripts"/"turn_machine.py")
tm=importlib.util.module_from_spec(spec); spec.loader.exec_module(tm)
LAYOUT=json.loads((ROOT/"configs"/"layouts.json").read_text())
GAME=json.loads((ROOT/"configs"/"game.json").read_text())

def turn(label,number,**extra):
    required={"meta":{"id":f"T{number:03}","label":label,"turn":number,"real_time":f"2026-08-13T01:{number:02}:00+08:00"},"time":{"mirror":"T+00:00:00"},"progress":{"projection_count":1,"fragment_count":0}}
    bodies={"越界投射":{"oracle":{"translated":"选择？","options":[{"id":"S","text":"保持沉默"}]}},"投射结算":{"resolution":"完成","mirror_change":"变化"},"收集碎片":{"creator":"问","collection":{"text":"答？","options":[{"id":"A","text":"答"}]}},"自由追溯历史":{"history":"历史","actions":["继续"]},"通关结算":{"completion":"重建"}}
    required.update(bodies[label]); required.update(extra); return required

def state(label="越界投射",number=1,connected=False):
    status="connected" if connected else "locked"
    return {"label":label,"turn":number,"fragments":{x:status for x in GAME["required_core_fragments"]},"claims":{x:False for x in GAME["completion_claims"]},"projection_count":1,"started_at":f"2026-08-13T01:{number:02}:00+08:00","last_real_time":f"2026-08-13T01:{number:02}:00+08:00","fragment_answers":[],"history_streak":0,"completed":False}

class MachineTest(unittest.TestCase):
    def accepted(self,previous,candidate,current):
        self.assertEqual(tm.validate(previous,candidate,current,LAYOUT,GAME),[])
        return tm.apply_updates(previous,candidate,current,LAYOUT,GAME)
    def test_cycle(self):
        current=state(); previous=turn("越界投射",1)
        current=self.accepted(previous,turn("投射结算",2),current)
        current=self.accepted(turn("投射结算",2),turn("收集碎片",3),current)
        current=self.accepted(turn("收集碎片",3),turn("自由追溯历史",4,state_updates={"fragment":{"id":"F01","status":"hinted"},"fragment_answer":{"fragment_id":"F01","question":"为什么？","answer":"因为证据","passed":True,"answered_at":"2026-08-13T01:04:00+08:00"}}),current)
        current=self.accepted(turn("自由追溯历史",4),turn("越界投射",5),current)
        self.assertEqual(current["label"],"越界投射")
    def test_illegal_skip_rejected(self):
        errors=tm.validate(turn("越界投射",1),turn("收集碎片",2),state(),LAYOUT,GAME)
        self.assertTrue(any("非法状态迁移" in x for x in errors))
    def test_cannot_finish_early(self):
        with self.assertRaises(SystemExit): tm.apply_updates(turn("收集碎片",3),turn("通关结算",4),state("收集碎片",3),LAYOUT,GAME)
    def test_all_fragments_force_completion(self):
        current=state("收集碎片",3,connected=True)
        result=self.accepted(turn("收集碎片",3),turn("通关结算",4),current)
        self.assertEqual(result["label"],"通关结算")
    def test_completion_questions_lock_game(self):
        current=state("通关结算",8,connected=True)
        previous=turn("通关结算",8)
        for number,claim in enumerate(GAME["completion_claims"],start=9):
            candidate=turn("通关结算",number,state_updates={"claims":{claim:True}})
            current=self.accepted(previous,candidate,current)
            previous=candidate
        self.assertTrue(current["completed"])
        errors=tm.validate(previous,turn("通关结算",13),current,LAYOUT,GAME)
        self.assertTrue(any("已经通关" in x for x in errors))
    def test_history_can_repeat_three_times_then_forces_oracle(self):
        current=state("收集碎片",3)
        previous=turn("收集碎片",3)
        candidate=turn("自由追溯历史",4,state_updates={"fragment":{"id":"F01","status":"hinted"},"fragment_answer":{"fragment_id":"F01","question":"为什么？","answer":"因为证据","passed":True,"answered_at":"2026-08-13T01:04:00+08:00"}})
        current=self.accepted(previous,candidate,current); previous=candidate
        self.assertEqual(current["history_streak"],1)
        for number in (5,6):
            candidate=turn("自由追溯历史",number)
            current=self.accepted(previous,candidate,current); previous=candidate
        self.assertEqual(current["history_streak"],3)
        errors=tm.validate(previous,turn("自由追溯历史",7),current,LAYOUT,GAME)
        self.assertTrue(any("最多连续 3 回合" in x for x in errors))
        current=self.accepted(previous,turn("越界投射",7),current)
        self.assertEqual(current["history_streak"],0)
        self.assertEqual(current["projection_count"],2)
    def test_progress_has_exactly_two_machine_values(self):
        current=state(); expected=tm.expected_progress(current,GAME)
        self.assertEqual(expected,{"projection_count":1,"fragment_count":0})
        current["fragments"]["F01"]="connected"
        self.assertEqual(tm.expected_progress(current,GAME),{"projection_count":1,"fragment_count":1})
    def test_accept_and_render_outputs_two_progress_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            markdown_path=Path(directory)/"turn-002.md"
            result=subprocess.run([
                "python3",str(ROOT/"scripts"/"turn_machine.py"),"accept",
                "--previous",str(ROOT/"examples"/"turn-001-oracle.json"),
                "--candidate",str(ROOT/"examples"/"turn-002-resolution.json"),
                "--state",str(ROOT/"examples"/"save.initial.json"),
                "--config",str(ROOT/"configs"/"layouts.json"),
                "--game-config",str(ROOT/"configs"/"game.json"),
                "--next-state",str(Path(directory)/"next.json"),"--markdown-output",str(markdown_path),"--render"
            ],capture_output=True,text=True,check=True)
            saved=markdown_path.read_text(encoding="utf-8")
        self.assertIn("- 投射次数：1",result.stdout)
        self.assertIn("- 碎片收集个数：0",result.stdout)
        self.assertNotIn("- 总数：",result.stdout)
        self.assertNotIn('"progress"',result.stdout)
        self.assertEqual(saved,result.stdout)

if __name__=="__main__": unittest.main()
