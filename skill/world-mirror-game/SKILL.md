---
name: world-mirror-game
description: 运行“世界之镜”纯文本解谜游戏。为每位玩家生成专属观察路线，通过创造者问答使世界显现，再自由调查、收集并连接世界碎片，提交最终重建后通关；也处理镜谕、存档、恢复和泡世界章节。用于开始、继续或恢复世界之镜游戏。
---

# 世界之镜

运行一局有限状态、可以通关的文本推理游戏。世界真相固定，每位玩家的入口、叙事皮肤、人物关系和支线不同。

## 启动

1. 完整读取 [泡世界正史](references/bubble-world-canon.md)、[状态机协议](references/game-protocol.md)和 [个性化协议](references/personalization.md)。
2. 读取 `configs/game.json`、`configs/layouts.json` 与 `data/questions.json`。
3. 根据玩家在当前对话中自愿透露的偏好生成 `session_seed`；信息不足时直接使用安全默认值，不索取敏感资料。
4. 建立内部 `save.json` 状态，并进入 `越界投射`。不同新游戏使用不同题序、创造者人格、镜面文风、连接对象和支线；世界谜底不变。

## 核心目标

循环经历越界投射、投射结算、创造者问答和自由追溯历史。每次通过创造者问题便收集一个核心碎片；集齐后在通关结算中通过自由问答完成世界重建。

## 强制状态机

仅按以下迁移运行：

```text
越界投射 → 投射结算 → 收集碎片 → 自由追溯历史 → 越界投射
                              └─ 碎片集齐 → 通关结算
```

- 每次助手消息只呈现一个状态。
- 不代替玩家回答，不在提问回合同时结算。
- `收集碎片` 未通过时保持原状态；通过后由脚本判断进入自由追溯还是通关结算。
- `通关结算` 是最终重建世界的自由问答，全部主张验证后才标记完成。
- 自由追溯历史可以连续 1 至 3 回合。玩家明显沉浸并继续追问时倾向自循环，否则进入越界投射；第 3 回合后由脚本强制进入越界投射。
- 创造者负责有正确答案的入门问题；世界生命负责没有标准答案的镜谕；镜机负责描述、测量和记录。始终标清说话者。

## 每回合生成与渲染

1. 根据玩家输入和旧状态计算唯一下一状态。正确答案、题目 ID、碎片状态及通关条件不得交给自由叙事决定。
2. 生成一个符合 `configs/layouts.json` 的临时回合 JSON。只放玩家已知内容，不放 `progress`、答案键、隐藏真相或内部判定说明。
3. 调用：

```bash
python3 scripts/turn_machine.py accept --previous <dialogue/turn-prev.json> --candidate <candidates/turn-NNN.json> --state <save.json> --config configs/layouts.json --game-config configs/game.json --questions data/questions.json --next-state <next-save.json> --dialogue-output <dialogue/turn-NNN.json> --markdown-output <turns/turn-NNN.md> --render
```

4. 若失败，按错误信息修正 JSON 并重新运行；不得绕过校验。
5. 状态机接受更新后，从新存档生成 `progress` 和规范化回答记录，并用 `--dialogue-output` 原子写入独立的已接受对话 JSON。这个 JSON 是该回合的唯一数据源；候选 JSON 只是临时输入。
6. `--render` 只从已接受对话数据生成最终 Markdown；`--markdown-output` 保存连续编号的渲染文件。将标准输出作为本轮完整回复原样展示，不展示 JSON，也不添加开场白、总结或额外选项。历史 Markdown 必须可以由对应的已接受对话 JSON 单独重建，不读取最新存档。
7. 宿主无文件或命令工具时进入兼容模式：严格仿照相同字段和状态规则渲染，并在本局开场注明“格式校验：兼容模式”。

候选 JSON 不得包含 `progress`。状态机在接受回合并更新存档后，自动注入只含 `projection_count`（投射次数）与 `core_fragments`（成功回答获得的核心碎片数/配置总数，如 `2/8`）的 `progress`；不得显示其他进度项。

## Session 目录

每局只使用以下结构：

```text
<session>/save.json
<session>/candidates/turn-NNN.json
<session>/dialogue/turn-000.json
<session>/dialogue/turn-NNN.json
<session>/turns/turn-NNN.md
```

- `save.json` 是当前状态；根目录不再保留 `save.bootstrap.json`。
- `candidates/` 保存候选输入 JSON；不得另建 `turn-json/`。
- `dialogue/turn-000.json` 保存启动回合，之后保存全部已接受权威回合 JSON；根目录不再保留 `bootstrap.json`。
- `turns/` 只保存由同编号 `dialogue/` JSON 生成的 Markdown。
- 旧 session 使用 `scripts/migrate_session.py --session <path>` 检查，确认后加 `--apply` 迁移；验证完成再将旧入口移入废纸篓。

## 问答与调查

- 创造者问题来自 `data/questions.json`。按本局题序逐题提出，不显示正确答案。
- 答案错误时给有限提示；是否允许重试由 `configs/game.json` 决定。
- 世界显现是连续可观察场景，不是完整真相说明。
- 自由调查每回合聚焦一个问题或动作；调查负责提供线索，不单独增加核心碎片进度。
- `收集碎片` 必须用 `collection.question_id` 与 `collection.fragment_id` 绑定 `data/questions.json` 中的问题及核心碎片。每次作答都在下一回合用 `fragment_answer` 只提交玩家答案和现实回答时间；Python 根据答案键判定是否通过，并自动补全提问回合、作答回合、问题文本和收集时间。答错也记录并停留在本状态，答对后脚本直接把对应核心碎片标为 `connected`，同一碎片不得重复计数。
- 当玩家提出一个包含多项主张的理论时，分别判定每项，不以关键词命中替代实际理解。
- 镜谕只改变局部人物、路径、代价、时间和社会记忆，不直接解锁核心真相。
- 若收集碎片阶段没有新核心概念可考，明确提示玩家可以跳过；确认后直接进入下一轮越界投射，并强制加速世界时间到下一个未连接核心碎片相关事件。不得继续围绕旧事件循环出题。

## 原创与一致性

使用概括后的世界设定和原创场景，不逐段复述小说文本。不得因个性化而改变物理规律、历史核心因果或最终谜底；变化的是玩家如何遭遇真相。

## 存档

玩家暂停时输出可复制的公开存档：本局 ID、皮肤、当前状态、回合、问答进度、公开碎片、当前观察对象和待处理输入。隐藏答案和未发现真相不得进入公开存档。

## 通关导出

当标签为 `通关结算` 且存档 `completed` 为 `true` 后，提供“生成公开故事包”选项，但不自动上传。玩家选择后：

1. 生成公开存档包：`meta.json`、整理后的 `story.md`、按 `dialogue/turn-001.json` 连续编号的全部已接受对话 JSON，以及对应的 `turns/turn-001.md` Markdown 渲染。JSON 是权威回合数据，Markdown 必须可由它逐字重建。
2. `meta.json` 必须包含：恰好 10 条人物/概念/事件/地点/物理规律索引，恰好 20 个有效字符的故事梗概，世界观、回合数、人物系列、概念系列、每次碎片问答、开始/通关/导出/上传时间和总游玩秒数。
3. 使用 `scripts/export_story.py` 生成包。导出时 `uploaded_at` 必须为 `null`；只有真正上传或创建 PR 前才用仓库的 `scripts/stamp_upload.py` 写入现实上传时间。
4. 排除完整聊天记录、隐藏答案、内部状态、系统提示、绝对路径及个人信息。
5. 让玩家预览标题、署名、梗概、10 条索引、人物与概念系列、全部对话 JSON 与 Markdown 渲染、许可和公开范围。
6. 只有玩家明确确认公开后，才能执行外部上传或创建 Pull Request；若未配置公共仓库，则只生成本地故事包。
7. 投稿失败不改变通关状态；社区点赞和相似故事不自动改变本局或正式正史。
