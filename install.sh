#!/bin/sh
set -eu

REPO="Steven147/world-mirror"
BRANCH="main"
SKILL_PATH="skill/world-mirror-game"
CODEX_BASE="${CODEX_HOME:-$HOME/.codex}"
DESTINATION="${1:-$CODEX_BASE/skills/world-mirror-game}"
TEMP_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "$TEMP_DIR"
}
trap cleanup EXIT INT TERM

if command -v curl >/dev/null 2>&1; then
  curl -fsSL "https://github.com/$REPO/archive/refs/heads/$BRANCH.tar.gz" -o "$TEMP_DIR/world-mirror.tar.gz"
elif command -v wget >/dev/null 2>&1; then
  wget -q "https://github.com/$REPO/archive/refs/heads/$BRANCH.tar.gz" -O "$TEMP_DIR/world-mirror.tar.gz"
else
  echo "需要 curl 或 wget 才能下载安装。" >&2
  exit 1
fi

tar -xzf "$TEMP_DIR/world-mirror.tar.gz" -C "$TEMP_DIR"
SOURCE="$TEMP_DIR/world-mirror-$BRANCH/$SKILL_PATH"

if [ ! -f "$SOURCE/SKILL.md" ]; then
  echo "下载内容中缺少 SKILL.md，安装已停止。" >&2
  exit 1
fi

if [ -e "$DESTINATION" ]; then
  BACKUP="$DESTINATION.backup.$(date +%Y%m%d%H%M%S)"
  mv "$DESTINATION" "$BACKUP"
  echo "现有版本已备份到：$BACKUP"
fi

mkdir -p "$(dirname "$DESTINATION")"
cp -R "$SOURCE" "$DESTINATION"
echo "世界之镜已安装到：$DESTINATION"
