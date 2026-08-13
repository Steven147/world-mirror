# 世界之镜

一款通过对话游玩的纯文本世界解谜游戏。玩家回答创造者的问题，使镜中世界逐渐显现；随后调查世界碎片、重建文明历史并通关。

## 一键安装 Skill

macOS / Linux：

```bash
curl -fsSL https://raw.githubusercontent.com/Steven147/world-mirror/main/install.sh | bash
```

也可以先下载并检查脚本，再执行：

```bash
curl -fsSLO https://raw.githubusercontent.com/Steven147/world-mirror/main/install.sh
less install.sh
bash install.sh
```

默认安装到 `${CODEX_HOME}/skills/world-mirror-game`；未设置 `CODEX_HOME` 时安装到 `~/.codex/skills/world-mirror-game`。安装器只下载本仓库的 `skill/world-mirror-game`，不会安装创作记录。

安装后使用：

```text
使用 $world-mirror-game 开始一局世界之镜。
```

## 通关故事

网站由 GitHub Pages 托管。每篇投稿位于：

```text
stories/<world-id>/<story-id>/meta.json
stories/<world-id>/<story-id>/story.md
```

档案馆首页会把公开元数据组织为故事、人物、事件与概念的关系星图；进入故事后，可以按回合翻阅投稿中公开的完整权威对话档案。原始聊天、系统信息和未公开输入不会进入网页。

投稿步骤见 [CONTRIBUTING.md](CONTRIBUTING.md)。公开投稿前请删除隐私、完整聊天记录、系统提示、隐藏答案、令牌和本地路径。

## 仓库内容

- `skill/world-mirror-game/`：可安装游戏 Skill。
- `install.sh`：一键安装脚本。
- `stories/`：已合并的玩家通关故事。
- `site/`：GitHub Pages 静态页面。
- `scripts/build_site.py`：根据故事元数据与公开回合档案生成网站索引、关系图谱和对话阅读数据。

`world-mirror-creator` 是作者的本地创作记录，不属于本仓库。
