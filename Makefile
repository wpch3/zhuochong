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
LDLIBS     = -lm -pthread -ldl   # 线程：渲染分块（T30.2）；dl：ztls 运行期加载 OpenSSL（T61.9）
#   注意 -ldl 只给原生目标。Windows 那条用 LoadLibrary，不需要也没有 libdl。
#   glibc 2.34 起 dlopen 已并进 libc，-ldl 变成空壳；留着是为了兼容更老的系统。
BUILD      = build

CORE_SRC   = $(wildcard src/core/*.c)
# ★ 头文件也要当依赖：原来只写了 .c，**改 .h 不会触发重编** ——
#   2026-10-17 做 T47.1 的负向对照时踩到：把 zphys2.h 里的常量改坏，
#   测试照样全绿（根本没重编），差点把一条没牙的闸当成有牙的。
CORE_HDR   = $(wildcard src/core/*.h)
CORE_OBJ   = $(patsubst src/%.c,$(BUILD)/%.o,$(CORE_SRC))

ZIG       ?= $(shell ls /home/user/.cache/tc/zigenv/lib/python3.*/site-packages/ziglang/zig 2>/dev/null | head -1)
WINTARGET  = x86_64-windows-gnu
DIST_WIN   = dist/windows/x86_64

.PHONY: all test smoke preview win pack-win clean fmt-check selfcheck asan check warncheck tls

all: test

$(BUILD)/%.o: src/%.c
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) $(INC) -c $< -o $@

# ---------------------------------------------------------------- 单元测试
$(BUILD)/test_core: tests/test_core.c $(CORE_SRC) $(CORE_HDR)
	@mkdir -p $(BUILD)
	$(CC) $(CFLAGS) $(INC) -o $@ tests/test_core.c $(CORE_SRC) $(LDLIBS)

test: $(BUILD)/test_core
	@echo "== 运行单元测试 =="
	@./$(BUILD)/test_core .

# ---------------------------------------------------------- TLS 闸门（T61.9）
# 它需要一个真的 TLS 服务端和一张证书，所以由 tools/check_tls.py 起好环境再调用。
# 单独一个二进制而不是塞进 test_core：在 C 里起 TLS 服务端要再 dlopen 一批
# 服务端符号、还要在测试里造证书，脚手架比被测的东西还重。
$(BUILD)/tls_probe: tests/tls_probe.c $(CORE_SRC) $(CORE_HDR)
	@mkdir -p $(BUILD)
	$(CC) $(CFLAGS) $(INC) -o $@ tests/tls_probe.c $(CORE_SRC) $(LDLIBS)

.PHONY: tls
tls: $(BUILD)/tls_probe
	@python3 tools/check_tls.py

# ---------------------------------------------------------------- 预览服务
$(BUILD)/zhuochong_preview: src/headless/main_headless.c $(CORE_SRC) $(CORE_HDR)
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
$(BUILD)/test_core_asan: tests/test_core.c $(CORE_SRC) $(CORE_HDR)
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

# 零告警闸：CI 是 `make clean` 后从零编的，本地增量编译会把告警藏起来。
# 额外带 -Wformat-security：**Ubuntu 的 gcc 默认开它、Debian 的不开**，
# CI 跑在 ubuntu-latest 上，本地是 Debian —— 不显式加就会出现"本地绿 CI 红"。
# （2026-10-17 实测：本地 make -s check 全绿，CI 却红了 20 多次，就是因为
#  tests/test_core.c 的告警从来没被重新触发过）。这里不碰 build/ 与 dist/，
#  直接编到临时目录，和 CI 同一套参数、同一条判据。
warncheck:
	@$(CC) $(CFLAGS) -Wformat-security $(INC) -o /tmp/zc_warncheck_bin tests/test_core.c $(CORE_SRC) $(LDLIBS) 2>/tmp/zc_warncheck.log; \
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
	    -luser32 -lgdi32 -lshell32 -lole32 -lcomctl32 -lws2_32
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
