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
CFLAGS    ?= -std=c11 -O2 -Wall -Wextra -Wno-unused-parameter
INC        = -Isrc
LDLIBS     = -lm
BUILD      = build

CORE_SRC   = $(wildcard src/core/*.c)
CORE_OBJ   = $(patsubst src/%.c,$(BUILD)/%.o,$(CORE_SRC))

ZIG       ?= $(shell ls /home/user/.cache/tc/zigenv/lib/python3.*/site-packages/ziglang/zig 2>/dev/null | head -1)
WINTARGET  = x86_64-windows-gnu
DIST_WIN   = dist/windows/x86_64

.PHONY: all test smoke preview win pack-win clean fmt-check

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
