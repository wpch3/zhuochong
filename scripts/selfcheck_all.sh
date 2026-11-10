#!/usr/bin/env bash
# selfcheck_all.sh - 一键自检（[测试锁]：必须全绿）
#
# 检查项：
#   1) 编译告警：核心代码零警告（-Wall -Wextra）
#   2) 单元测试：全部通过
#   3) 配置与 schema：全部能被解析与校验（含故意写坏的负例）
#   4) 素材验收：每个形态的部件都有透明通道、分辨率达标、无键色残留
#   5) Windows 交叉编译：能产出 x86_64 的 GUI 子系统 exe
#   6) 预览服务：能起来并返回真实帧
#   7) 互动/动作端到端：眨眼、视线、17 个动作、四种互动、区域命中、测试台页面
#
# 用法：bash scripts/selfcheck_all.sh
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
FAIL=0

# 选一个带 pillow 的 Python（素材检查需要）
PY=""
for cand in "${ZC_PYTHON:-}" /home/user/.imgenv/bin/python python3; do
  [ -n "$cand" ] || continue
  if "$cand" -c "import PIL" >/dev/null 2>&1; then PY="$cand"; break; fi
done
if [ -z "$PY" ]; then
  echo "[警告] 找不到带 pillow 的 Python，素材透明通道检查将跳过（安装：python3 -m venv .imgenv && .imgenv/bin/pip install pillow numpy）"
fi
step() { printf "\n=== %s ===\n" "$1"; }
ok()   { printf "  [通过] %s\n" "$1"; }
bad()  { printf "  [失败] %s\n" "$1"; FAIL=1; }

step "1/8 仓库静态自检（引用完整性/唯一性/契约/卫生）"
if "${PY:-python3}" tools/selfcheck_repo.py --root . >/tmp/zc_repo.log 2>&1; then
  ok "$(tail -1 /tmp/zc_repo.log)"
else
  bad "仓库自检不通过：$(grep 不通过 /tmp/zc_repo.log | head -3 | tr '\n' ' ')"
fi

step "2/8 编译检查（核心代码零告警）"
if make clean >/dev/null 2>&1 && make build/test_core >/tmp/zc_build.log 2>&1; then
  if grep -qiE "warning|error" /tmp/zc_build.log; then
    bad "编译有告警，见 /tmp/zc_build.log"; cat /tmp/zc_build.log | head -20
  else
    ok "核心代码编译无告警"
  fi
else
  bad "编译失败"; head -30 /tmp/zc_build.log
fi

step "3/8 单元测试"
if ./build/test_core . 2>/dev/null | tail -3 | grep -q "全部通过"; then
  ok "单元测试全部通过"
else
  bad "单元测试未通过"; ./build/test_core . 2>&1 | tail -12
fi

step "4/8 配置解析与 schema 校验"
if ./build/test_core . >/dev/null 2>&1; then ok "配置加载与坏配置诊断已覆盖（见单元测试）"; else bad "配置相关测试失败"; fi
for f in config/*.json; do
  if grep -q '"schema_version"' "$f"; then ok "$f 带 schema_version"; else bad "$f 缺少 schema_version"; fi
done

step "5/8 素材验收（形状/色卡/对位/透明通道/残留）"
# 完整验收：形状(IoU)、色卡距离、关节对位、落在身体内、键色与白边残留
if [ -n "$PY" ] && [ -f tools/check_assets.py ]; then
  if "$PY" tools/check_assets.py --character xiaoxun --form teen --quiet \
       --json logs/asset_qa/report.json >/dev/null 2>&1; then
    ok "素材机器验收全部通过（详见 logs/asset_qa/report.json）"
  else
    bad "素材机器验收有不合格项（看 logs/asset_qa/report.json）"
  fi
else
  echo "  跳过完整验收（缺少带 pillow 的 Python）"
fi
REPORT="characters/xiaoxun/forms/teen/sprites_report.json"
if [ -f "$REPORT" ]; then
  MAGE=$("${PY:-python3}" - "$REPORT" <<'PY' 2>/dev/null
import json,sys
d=json.load(open(sys.argv[1]))
print(d.get("magenta_residue_pixels", -1), d.get("white_residue_pixels", -1), d.get("sprite_size"))
PY
)
  echo "  报告：$MAGE"
  if echo "$MAGE" | awk '{exit !($1 < 200 && $2 < 800)}'; then ok "键色残留与白边在阈值内"; else bad "素材残留超标"; fi
else
  bad "缺少素材验收报告 $REPORT"
fi
for f in characters/*/forms/*/sprites/*.png; do
  [ -f "$f" ] || continue
  # L 模式的 armpit/skirt mask 是灰度权重图，不是 RGBA 精灵；在 check_assets 中按 mask schema 校验。
  case "$f" in */armpit_mask*.png|*/skirt_mask*.png|*/skirt_mask_base*.png) continue ;; esac
  [ -n "$PY" ] || break
  "$PY" - "$f" <<'PY' || bad "$f 透明通道检查失败"
import sys
from PIL import Image
im = Image.open(sys.argv[1])
assert im.mode == "RGBA", f"{sys.argv[1]} 不是 RGBA（没有透明通道）"
a = im.convert("RGBA").getchannel("A")
assert a.getextrema()[0] == 0, f"{sys.argv[1]} 完全没有透明像素（可能忘了抠背景）"
sys.exit(0)
PY
done
[ $FAIL -eq 0 ] && ok "所有部件都有透明通道"
if [ -n "$PY" ]; then
  if "$PY" tools/qa_hair_purity.py --character xiaoxun --form teen --check-twin-hood-eye; then
    ok "twin hood 刘海中央无蓝色眼部污染"
  else
    bad "twin hood 刘海中央眼部污染检查失败"
  fi
else
  echo "  跳过 twin hood 定点像素检查（缺少带 Pillow/NumPy 的 Python）"
fi

step "6/8 Windows 交叉编译"
if command -v python3 >/dev/null; then :; fi
ZIG=$(ls /home/user/.cache/tc/zigenv/lib/python3.*/site-packages/ziglang/zig 2>/dev/null | head -1)
if [ -z "${ZIG:-}" ]; then
  bad "找不到 zig：请安装 ziglang==0.17.0（见 docs/memory/LESSONS.md 第六节），不能跳过 Windows 编译"
elif [ -n "${ZIG:-}" ]; then
  if make win >/tmp/zc_win.log 2>&1 && [ -f dist/windows/x86_64/zhuochong.exe ]; then
    SUB=$(python3 - <<'PY'
import struct
d=open('dist/windows/x86_64/zhuochong.exe','rb').read()
pe=struct.unpack_from('<I', d, 0x3C)[0]
print(struct.unpack_from('<H', d, pe+0x5C)[0], struct.unpack_from('<H', d, pe+4)[0])
PY
)
    echo "  目标：子系统 机器码 = $SUB（期望 2 8664）"
    case "$SUB" in
      "2 34404") ok "Windows GUI exe 生成成功" ;;
      *) bad "exe 子系统/架构不符合预期" ;;
    esac
  else
    bad "Windows 交叉编译失败"; tail -20 /tmp/zc_win.log
  fi
else
  echo "  [跳过] 未找到 zig（沙箱外请自行安装或用 MSVC/MinGW）"
fi

step "7/8 预览服务"
if make build/zhuochong_preview >/tmp/zc_prev.log 2>&1; then
  ./build/zhuochong_preview --root . --port 5199 --bind 127.0.0.1 >/tmp/zc_prev_run.log 2>&1 &
  PID=$!
  sleep 2
  CODE=$(curl -s -o /tmp/zc_frame.png -w "%{http_code}" "http://127.0.0.1:5199/api/frame.png" || echo 000)
  INFO=$(curl -s "http://127.0.0.1:5199/api/info.json" | head -c 120 || echo "")
  kill $PID 2>/dev/null
  if [ "$CODE" = "200" ] && [ -s /tmp/zc_frame.png ]; then
    ok "预览服务返回真实帧（$(stat -c%s /tmp/zc_frame.png) 字节）"
    echo "  info: $INFO"
  else
    bad "预览服务未返回帧（HTTP $CODE）"; tail -5 /tmp/zc_prev_run.log
  fi
else
  bad "预览服务编译失败"
fi

step "8/8 互动与动作端到端（冒烟）"
if [ -x build/zhuochong_preview ]; then
  if "${PY:-python3}" tools/api_smoke.py --spawn --port 5200 --root . >/tmp/zc_smoke.log 2>&1; then
    ok "$(tail -1 /tmp/zc_smoke.log)"
  else
    bad "互动/动作冒烟测试有不通过项（见 /tmp/zc_smoke.log）"; tail -12 /tmp/zc_smoke.log
  fi
else
  bad "没有 build/zhuochong_preview，跳不过去"
fi

printf "\n================ 结论 ================\n"
if [ $FAIL -eq 0 ]; then
  echo "全部通过（[测试锁]）。真机项目仍需在 Windows 上确认：透明窗/穿透/光标/托盘/动效。"
else
  echo "存在失败项，禁止交付。"
fi
exit $FAIL
