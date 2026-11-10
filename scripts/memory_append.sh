#!/usr/bin/env bash
# memory_append.sh - 追加一条工作日志到 docs/memory/JOURNAL.md
#
# 用法：bash scripts/memory_append.sh "做了什么" "遇到/修了什么" "下一步"
# 约定：每个代理每次工作结束都要追加一条；开头先写"思考"（为什么这么做）。
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
J="$ROOT/docs/memory/JOURNAL.md"
TS="$(date '+%Y-%m-%d %H:%M')"
WHAT="${1:-（未填写）}"
ISSUE="${2:-（无）}"
NEXT="${3:-（见 TASKS.md）}"
{
  printf "\n## %s\n" "$TS"
  printf -- "- 做了什么：%s\n" "$WHAT"
  printf -- "- 遇到/修了什么：%s\n" "$ISSUE"
  printf -- "- 下一步：%s\n" "$NEXT"
} >> "$J"
echo "已追加日志到 $J"
