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
QUESTIONS=json.loads((ROOT/"data"/"questions.json").read_text())
QUESTION_BY_ID={item["id"]:item for item in QUESTIONS["questions"]}

def turn(label,number,**extra):
    required={"meta":{"id":f"T{number:03}","label":label,"turn":number,"real_time":f"2026-08-13T01:{number:02}:00+08:00"},"time":{"mirror":"T+00:00:00"}}
    question=QUESTION_BY_ID["CQ01"]
    bodies={"越界投射":{"oracle":{"translated":"选择？","options":[{"id":"S","text":"保持沉默"}]}},"投射结算":{"resolution":"完成","mirror_change":"变化"},"收集碎片":{"creator":"问","collection":{"question_id":question["id"],"fragment_id":question["fragment"],"text":question["text"],"options":[{"id":key,"text":value} for key,value in question["options"].items()]}},"自由追溯历史":{"history":"历史","actions":["继续"]},"通关结算":{"completion":"重建"}}
    required.update(bodies[label]); required.update(extra); return required

def fragment_answer(answer="B",minute=4):
    return {"answer":answer,"answered_at":f"2026-08-13T01:{minute:02}:00+08:00"}

def state(label="越界投射",number=1,connected=False):
    status="connected" if connected else "locked"
    answers=[]
    if connected:
        answers=[{"fragment_id":item,"question_id":f"CQ{index:02}","question_turn":1,"answer_turn":2,"question":"问题","answer":"A","passed":True,"answered_at":"2026-08-13T01:02:00+08:00","collected_at":"2026-08-13T01:02:00+08:00"} for index,item in enumerate(GAME["required_core_fragments"],1)]
    return {"label":label,"turn":number,"fragments":{x:status for x in GAME["required_core_fragments"]},"claims":{x:False for x in GAME["completion_claims"]},"projection_count":1,"started_at":f"2026-08-13T01:{number:02}:00+08:00","last_real_time":f"2026-08-13T01:{number:02}:00+08:00","fragment_answers":answers,"history_streak":0,"completed":False}

class MachineTest(unittest.TestCase):
    def accepted(self,previous,candidate,current):
        self.assertEqual(tm.validate(previous,candidate,current,LAYOUT,GAME,QUESTIONS),[])
        return tm.apply_updates(previous,candidate,current,LAYOUT,GAME,QUESTIONS)
    def test_cycle(self):
        current=state(); previous=turn("越界投射",1)
        current=self.accepted(previous,turn("投射结算",2),current)
        current=self.accepted(turn("投射结算",2),turn("收集碎片",3),current)
        current=self.accepted(turn("收集碎片",3),turn("自由追溯历史",4,state_updates={"fragment_answer":fragment_answer()}),current)
        self.assertEqual(current["fragments"]["F01"],"connected")
        self.assertEqual(current["fragment_answers"][0]["question_turn"],3)
        self.assertEqual(current["fragment_answers"][0]["answer_turn"],4)
        current=self.accepted(turn("自由追溯历史",4),turn("越界投射",5),current)
        self.assertEqual(current["label"],"越界投射")
    def test_illegal_skip_rejected(self):
        errors=tm.validate(turn("越界投射",1),turn("收集碎片",2),state(),LAYOUT,GAME,QUESTIONS)
        self.assertTrue(any("非法状态迁移" in x for x in errors))
    def test_cannot_finish_early(self):
        with self.assertRaises(SystemExit): tm.apply_updates(turn("收集碎片",3),turn("通关结算",4),state("收集碎片",3),LAYOUT,GAME,QUESTIONS)
    def test_all_fragments_force_completion(self):
        current=state("收集碎片",3,connected=True)
        current["fragment_answers"]=[item for item in current["fragment_answers"] if item["fragment_id"]!="F08"]
        current["fragments"]["F08"]="locked"
        question=QUESTION_BY_ID["CQ08"]
        previous=turn("收集碎片",3,collection={"question_id":question["id"],"fragment_id":question["fragment"],"text":question["text"],"options":[{"id":key,"text":value} for key,value in question["options"].items()]})
        result=self.accepted(previous,turn("通关结算",4,state_updates={"fragment_answer":fragment_answer()}),current)
        self.assertEqual(result["label"],"通关结算")
    def test_completion_questions_lock_game(self):
        current=state("通关结算",8,connected=True)
        previous=turn("通关结算",8)
        for number,claim in enumerate(GAME["completion_claims"],start=9):
            candidate=turn("通关结算",number,state_updates={"claims":{claim:True}})
            current=self.accepted(previous,candidate,current)
            previous=candidate
        self.assertTrue(current["completed"])
        errors=tm.validate(previous,turn("通关结算",13),current,LAYOUT,GAME,QUESTIONS)
        self.assertTrue(any("已经通关" in x for x in errors))
    def test_history_can_repeat_three_times_then_forces_oracle(self):
        current=state("收集碎片",3)
        previous=turn("收集碎片",3)
        candidate=turn("自由追溯历史",4,state_updates={"fragment_answer":fragment_answer()})
        current=self.accepted(previous,candidate,current); previous=candidate
        self.assertEqual(current["history_streak"],1)
        for number in (5,6):
            candidate=turn("自由追溯历史",number)
            current=self.accepted(previous,candidate,current); previous=candidate
        self.assertEqual(current["history_streak"],3)
        errors=tm.validate(previous,turn("自由追溯历史",7),current,LAYOUT,GAME,QUESTIONS)
        self.assertTrue(any("最多连续 3 回合" in x for x in errors))
        current=self.accepted(previous,turn("越界投射",7),current)
        self.assertEqual(current["history_streak"],0)
        self.assertEqual(current["projection_count"],2)
    def test_progress_is_generated_from_state(self):
        current=state(); candidate=turn("投射结算",2)
        rendered=tm.build_accepted_turn(candidate,current,GAME)
        self.assertNotIn("progress",candidate)
        self.assertEqual(rendered["progress"],{"projection_count":1,"core_fragments":"0/8"})
        current["fragment_answers"].append({"fragment_id":"F01","passed":True})
        current["fragment_answers"].append({"fragment_id":"F03","passed":True})
        rendered=tm.build_accepted_turn(candidate,current,GAME)
        self.assertEqual(rendered["progress"],{"projection_count":1,"core_fragments":"2/8"})
    def test_failed_answer_is_recorded_without_collecting_fragment(self):
        current=state("收集碎片",3)
        candidate=turn("收集碎片",4,state_updates={"fragment_answer":fragment_answer("A")})
        result=self.accepted(turn("收集碎片",3),candidate,current)
        self.assertEqual(result["fragments"]["F01"],"locked")
        self.assertEqual(result["fragment_answers"][0],{
            "fragment_id":"F01","question_id":"CQ01","question_turn":3,"answer_turn":4,"question":QUESTION_BY_ID["CQ01"]["text"],"answer":"A","passed":False,
            "answered_at":"2026-08-13T01:04:00+08:00","collected_at":None,
        })
        self.assertEqual(tm.build_accepted_turn(candidate,result,GAME)["progress"]["core_fragments"],"0/8")
    def test_collected_fragment_cannot_be_asked_again(self):
        current=state("投射结算",2)
        current["fragment_answers"].append({"fragment_id":"F01","passed":True})
        errors=tm.validate(turn("投射结算",2),turn("收集碎片",3),current,LAYOUT,GAME,QUESTIONS)
        self.assertTrue(any("已经收集" in error for error in errors))
    def test_collection_enforces_session_question_order_and_prerequisites(self):
        current=state("投射结算",2)
        current["profile"]={"question_order":["CQ03","CQ08","CQ01"]}
        cq08=QUESTION_BY_ID["CQ08"]
        collection={"question_id":cq08["id"],"fragment_id":cq08["fragment"],"text":cq08["text"],"options":[{"id":key,"text":value} for key,value in cq08["options"].items()]}
        errors=tm.validate(turn("投射结算",2),turn("收集碎片",3,collection=collection),current,LAYOUT,GAME,QUESTIONS)
        self.assertTrue(any("题序与先修条件" in error and "CQ03" in error for error in errors))
    def test_accepted_dialogue_strips_internal_state_updates(self):
        current=state("收集碎片",3)
        candidate=turn("自由追溯历史",4,state_updates={"fragment_answer":fragment_answer()})
        result=self.accepted(turn("收集碎片",3),candidate,current)
        accepted=tm.build_accepted_turn(candidate,result,GAME)
        self.assertNotIn("state_updates",accepted)
        self.assertEqual(accepted["answer_record"]["question_id"],"CQ01")
        self.assertEqual(tm.render_turn.validate(accepted,LAYOUT),[])
        leaked=dict(accepted,state_updates={"fragment_answer":fragment_answer()})
        self.assertTrue(any("state_updates" in error for error in tm.render_turn.validate(leaked,LAYOUT)))
    def test_candidate_progress_is_rejected(self):
        candidate=turn("投射结算",2,progress={"projection_count":999,"fragment_count":999})
        errors=tm.validate(turn("越界投射",1),candidate,state(),LAYOUT,GAME,QUESTIONS)
        self.assertTrue(any("不得提供 progress" in error for error in errors))
    def test_internal_top_level_fields_are_rejected(self):
        candidate=turn("投射结算",2,claims={"C01":True},fragment_answers=[])
        errors=tm.validate(turn("越界投射",1),candidate,state(),LAYOUT,GAME,QUESTIONS)
        self.assertTrue(any("未公开或未知顶层字段" in error for error in errors))
        accepted=tm.build_accepted_turn(turn("投射结算",2),state(),GAME)
        accepted["claims"]={"C01":True}
        self.assertTrue(any("未公开或未知顶层字段" in error for error in tm.render_turn.validate(accepted,LAYOUT)))
    def test_skip_collection_forces_time_jump_to_next_concept(self):
        current=state("收集碎片",3)
        candidate=turn("越界投射",4,
            time_jump={"target_fragment_id":"F01","target_concept":"电磁生命","elapsed":"三百个当地周期","from_event":"针尖号返航","to_event":"早期生命遗迹被发现"},
            state_updates={"skip_collection":{"reason":"no_new_core_concept","next_fragment_id":"F01"}})
        result=self.accepted(turn("收集碎片",3),candidate,current)
        self.assertEqual(result["projection_count"],2)
        self.assertEqual(result["fragments"]["F01"],"locked")
        self.assertEqual(result["last_skip"]["target_fragment_id"],"F01")
    def test_skip_without_time_jump_is_rejected(self):
        with self.assertRaises(SystemExit):
            tm.apply_updates(turn("收集碎片",3),turn("越界投射",4,state_updates={"skip_collection":{"reason":"no_new_core_concept","next_fragment_id":"F01"}}),state("收集碎片",3),LAYOUT,GAME,QUESTIONS)
    def test_skip_cannot_bypass_next_fragment(self):
        candidate=turn("越界投射",4,
            time_jump={"target_fragment_id":"F02","target_concept":"空间","elapsed":"百年","from_event":"旧事件","to_event":"新事件"},
            state_updates={"skip_collection":{"reason":"no_new_core_concept","next_fragment_id":"F02"}})
        with self.assertRaises(SystemExit): tm.apply_updates(turn("收集碎片",3),candidate,state("收集碎片",3),LAYOUT,GAME,QUESTIONS)
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
                "--questions",str(ROOT/"data"/"questions.json"),
                "--next-state",str(Path(directory)/"next.json"),
                "--dialogue-output",str(Path(directory)/"dialogue-002.json"),
                "--markdown-output",str(markdown_path),"--render"
            ],capture_output=True,text=True,check=True)
            saved=markdown_path.read_text(encoding="utf-8")
            dialogue=json.loads((Path(directory)/"dialogue-002.json").read_text(encoding="utf-8"))
            rerendered=subprocess.run([
                "python3",str(ROOT/"scripts"/"render_turn.py"),
                "--turn",str(Path(directory)/"dialogue-002.json"),
                "--config",str(ROOT/"configs"/"layouts.json"),
            ],capture_output=True,text=True,check=True).stdout
        self.assertIn("- 投射次数：1",result.stdout)
        self.assertIn("- 核心碎片：0/8",result.stdout)
        self.assertNotIn("- 总数：",result.stdout)
        self.assertNotIn('"progress"',result.stdout)
        self.assertEqual(dialogue["progress"],{"projection_count":1,"core_fragments":"0/8"})
        self.assertEqual(saved,result.stdout)
        self.assertEqual(rerendered,saved)

if __name__=="__main__": unittest.main()
