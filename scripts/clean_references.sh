#!/usr/bin/env bash
# clean_references.sh - 参考项目源码"用完删除"（用户要求）
#
# 参考源码只放在仓库外缓存目录，永不进入仓库；这个脚本用于清理。
# 用法：bash scripts/clean_references.sh [目标目录]
set -eu
DEST="${1:-${REF_DIR:-$HOME/.cache/zc-refs}}"
if [ -d "$DEST" ]; then
  echo "将删除参考源码目录：$DEST"
  du -sh "$DEST" 2>/dev/null || true
  rm -rf "$DEST"
  echo "已删除。需要时再跑 bash scripts/fetch_references.sh"
else
  echo "目录不存在：$DEST（无需清理）"
fi
