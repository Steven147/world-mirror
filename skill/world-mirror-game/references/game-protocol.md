# 状态机协议

## 状态职责

| 状态 | 需要玩家输入 | 用途 |
|---|---:|---|
| `CREATOR_QUESTION` | 是 | 创造者提出一个有正确答案的问题 |
| `ANSWER_RESOLUTION` | 否 | 判定上一回答、改变清晰度、解锁提示碎片 |
| `WORLD_REVELATION` | 否 | 达到阈值后首次呈现连续世界 |
| `FREE_INVESTIGATION` | 是 | 观察、提问、测量、连接碎片或申请重建 |
| `ORACLE_QUESTION` | 是 | 世界生命投射无标准答案的局部抉择 |
| `ORACLE_RESOLUTION` | 否 | 返回可理解部分并记录延迟回响 |
| `FINAL_RECONSTRUCTION` | 是 | 玩家陈述世界本质与历史因果 |
| `COMPLETED` | 否 | 总结真相、碎片连接、局部影响与统计 |

`ANSWER_RESOLUTION`、`WORLD_REVELATION` 和 `ORACLE_RESOLUTION` 虽不要求玩家决策，仍各占一条助手消息。下一状态在玩家要求继续或作出合法行动后呈现，保持回合边界清楚。

## 持久状态

```json
{
  "game_id": "bubble-world-001",
  "state": "CREATOR_QUESTION",
  "turn": 1,
  "session_seed": "非敏感、可复现字符串",
  "profile": {
    "creator_voice": "archivist",
    "mirror_style": "cold-optical",
    "entry_route": "returning-vessel",
    "connection_role": "scientist"
  },
  "quiz": {
    "correct": 0,
    "threshold": 5,
    "asked": [],
    "current_question": "CQ01"
  },
  "fragments": {
    "F01": "locked"
  },
  "pending_echoes": [],
  "reconstruction_attempts": 0
}
```

碎片只能依次迁移：`locked → hinted → discovered → connected`，不能倒退或跳过；题目可把 `locked` 推进到 `hinted`，调查可推进到 `discovered`，玩家正确解释关联后推进到 `connected`。

## 双重时间

- 镜机时间从 `T+00:00:00` 起，是设备参考系。
- 当地时间最初用观测到的物理周期表达，理解当地历法后才显示译名。
- 玩家思考、规则询问、问答选择和存档不推进世界物理时间。
- 观察按秒至小时推进；历史加速停在新碎片、镜谕或不可逆事件之前。

## 最终重建

检查四个核心主张，而非只匹配单词：

1. 世界位于一颗行星的球形空心地核中。
2. 生命是由半导体结构自然演化出的机械生命，依赖放射性与电磁过程。
3. 有限空间和掘进碎岩塑造了社会冲突、探险禁令与地层战争。
4. 密度递减和引力引导文明向外，随后发现液体、气体、浮力，最终抵达海面与星空。

全部成立则通关；缺项时只指出哪条证据链尚未闭合，返回调查。

## 信息边界

- 创造者知道答案但只按题目给提示。
- 镜机只陈述已测事实和明确标注的假说。
- 世界生命只使用其时代已有的概念。
- 玩家未发现前，避免确定性使用“地核、海洋、行星表面、星空”等答案词。
