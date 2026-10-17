# Makefile - 桌宠项目构建
#
# 目标：
#   make test        构建并运行单元测试（沙箱内可验证，[测试锁]）
#   make preview     构建并启动沙箱预览服务（C 引擎真实渲染，端口 5173）
#   make win         用 zig cc 交叉编译出 Windows 可执行文件（dist/windows/x86_64/）
#   make pack-win    打包 Windows 发行目录（exe + config + schemas + characters）
#   make clean
#
# 说明：本项目零第三方依赖（仅自带 stb_image.h），Windows 用 zig cc 直接交叉编译，
#       不需要安装 MinGW 工具链。

CC        ?= gcc
CFLAGS    ?= -std=c11 -O2 -Wall -Wextra -Wno-unused-parameter -pthread
INC        = -Isrc
LDLIBS     = -lm -pthread   # 渲染分块用线程（T30.2）
BUILD      = build

CORE_SRC   = $(wildcard src/core/*.c)
CORE_OBJ   = $(patsubst src/%.c,$(BUILD)/%.o,$(CORE_SRC))

ZIG       ?= $(shell ls /home/user/.cache/tc/zigenv/lib/python3.*/site-packages/ziglang/zig 2>/dev/null | head -1)
WINTARGET  = x86_64-windows-gnu
DIST_WIN   = dist/windows/x86_64

.PHONY: all test smoke preview win pack-win clean fmt-check selfcheck asan check warncheck

all: test

$(BUILD)/%.o: src/%.c
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) $(INC) -c $< -o $@

# ---------------------------------------------------------------- 单元测试
$(BUILD)/test_core: tests/test_core.c $(CORE_SRC)
	@mkdir -p $(BUILD)
	$(CC) $(CFLAGS) $(INC) -o $@ tests/test_core.c $(CORE_SRC) $(LDLIBS)

test: $(BUILD)/test_core
	@echo "== 运行单元测试 =="
	@./$(BUILD)/test_core .

# ---------------------------------------------------------------- 预览服务
$(BUILD)/zhuochong_preview: src/headless/main_headless.c $(CORE_SRC)
	@mkdir -p $(BUILD)
	$(CC) $(CFLAGS) $(INC) -o $@ src/headless/main_headless.c $(CORE_SRC) $(LDLIBS)

preview: $(BUILD)/zhuochong_preview
	@echo "预览服务：http://0.0.0.0:5173   测试台：http://0.0.0.0:5173/test.html"
	./$(BUILD)/zhuochong_preview --root . --port 5173 --bind 0.0.0.0

# 互动/动作端到端冒烟（自己起一个预览再打一圈端点，判据是"画面真的变了"）
smoke: $(BUILD)/zhuochong_preview
	@python3 tools/api_smoke.py --spawn --port 5200 --root .

# ---------------------------------------------------------------- 自检（保险）
# 仓库静态自检：引用完整性 / 唯一性 / 契约 / 卫生（1 秒，不编译不渲染）
selfcheck:
	@python3 tools/selfcheck_repo.py --root .

# 带地址消毒器跑一遍单测：越界读写、释放后使用、内存泄漏都会当场炸出来
$(BUILD)/test_core_asan: tests/test_core.c $(CORE_SRC)
	@mkdir -p $(BUILD)
	$(CC) -std=c11 -g -O1 -fsanitize=address,undefined -fno-omit-frame-pointer \
		-Wall -Wextra -Wno-unused-parameter -pthread $(INC) -o $@ tests/test_core.c $(CORE_SRC) $(LDLIBS)

asan: $(BUILD)/test_core_asan
	@echo "== ASan/UBSan 跑单测（慢 3~5 倍，越界/泄漏当场非零退出）=="
	@ASAN_OPTIONS=detect_leaks=1 ./$(BUILD)/test_core_asan .

# 交付前跑这一条：静态自检 + 单测 + ASan + 端到端冒烟
# 平台契约校验 + 生成 web/platform.json（能力 × 供应商清单）
platform:
	@python3 tools/check_platform.py

# 界面内核与组件的单测（node + DOM stub，不需要浏览器）
web-test:
	@node tests/test_web.js

check: selfcheck warncheck test asan smoke web-test
	@echo "== 全部保险都过了 =="

# 零告警闸：CI 是 `make clean` 后从零编的，本地增量编译会把告警藏起来
# （2026-10-17 实测：本地 make -s check 全绿，CI 却红了 20 多次，就是因为
#  tests/test_core.c 的告警从来没被重新触发过）。这里不碰 build/ 与 dist/，
#  直接编到临时目录，和 CI 同一套参数、同一条判据。
warncheck:
	@$(CC) $(CFLAGS) $(INC) -o /tmp/zc_warncheck_bin tests/test_core.c $(CORE_SRC) $(LDLIBS) 2>/tmp/zc_warncheck.log; \
	  rc=$$?; n=`grep -c "warning:" /tmp/zc_warncheck.log || true`; \
	  if [ $$rc -ne 0 ] || [ $$n -ne 0 ]; then \
	    echo "== 从零重编出现 $$n 条告警（CI 会因此失败）=="; cat /tmp/zc_warncheck.log; exit 1; \
	  fi; \
	  echo "零告警全量重编通过（CI 同款口径）"

# ---------------------------------------------------------------- Windows
win: $(CORE_OBJ)
	@mkdir -p $(DIST_WIN)
	@if [ -z "$(ZIG)" ]; then echo "未找到 zig（python3 -m venv + pip install ziglang）"; exit 1; fi
	$(ZIG) cc -target $(WINTARGET) -std=c11 -O2 -Wall -Wextra \
	    -Isrc -Wl,/subsystem:windows \
	    -o $(DIST_WIN)/zhuochong.exe \
	    src/win32/main_win.c src/win32/zw32.c $(CORE_SRC) \
	    -luser32 -lgdi32 -lshell32 -lole32 -lcomctl32
	@rm -f $(DIST_WIN)/zhuochong.pdb
	@echo "已生成 $(DIST_WIN)/zhuochong.exe"
	@ls -la $(DIST_WIN)/zhuochong.exe

pack-win: win
	@rm -rf dist/windows/zhuochong
	@mkdir -p dist/windows/zhuochong
	cp $(DIST_WIN)/zhuochong.exe dist/windows/zhuochong/
	cp -r config schemas characters dist/windows/zhuochong/
	@mkdir -p dist/windows/zhuochong/logs
	@echo "已打包 dist/windows/zhuochong（把整个目录拷到 Windows 双击 exe 即可）"

clean:
	rm -rf $(BUILD) dist
