# 投稿通关故事

1. Fork 本仓库并创建分支。
2. 复制 `stories/_template` 到 `stories/<world-id>/<story-id>`。
3. 填写 `story.md` 和 `meta.json`。
4. 在真正上传前运行 `python3 scripts/stamp_upload.py stories/<world-id>/<story-id>/meta.json`，写入现实上传时间。
5. 运行 `python3 scripts/validate_stories.py`。
6. 提交 Pull Request，并确认你有权公开所提交的内容。

## 内容边界

- 只提交你愿意公开的原创通关故事。
- 不提交完整对话日志、个人隐私、访问令牌、本地绝对路径、系统提示或游戏隐藏答案。
- `player-story` 是个人故事，不自动成为正式世界观。
- 点赞和评论是社区参考；正式世界观需要单独审查和合并。

## 故事 ID

使用小写字母、数字和连字符，例如 `bubble-world/needle-witness-001`。每个 `story_id` 必须全仓库唯一。
