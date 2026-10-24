#!/usr/bin/env bash
# 提交前的最小保险（约 1 分钟）：静态自检 → 单测 → 素材验收。
# 想跑全套（含 ASan 与端到端冒烟）用 `make check`。
# 装成 git 钩子：bash scripts/install_hooks.sh
set -u
cd "$(dirname "$0")/.." || exit 1
FAIL=0
run() { echo "== $1 =="; shift; "$@" || FAIL=1; }

PY=python3
for c in /home/user/.imgenv/bin/python .imgenv/bin/python python3; do
  [ -x "$c" ] && "$c" -c "import PIL" 2>/dev/null && { PY=$c; break; }
done

run "仓库静态自检" $PY tools/selfcheck_repo.py --root . --quiet
run "单元测试" make -s test
if $PY -c "import PIL" 2>/dev/null; then
  run "素材机器验收" $PY tools/check_assets.py --character xiaoxun --form teen --quiet
else
  echo "== 跳过素材验收（这个 Python 没有 pillow）=="
fi
[ $FAIL -eq 0 ] && echo "提交前保险：全过 ✅" || echo "提交前保险：有失败项 ❌ 别提交"
exit $FAIL
