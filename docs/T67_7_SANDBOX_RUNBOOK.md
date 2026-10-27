# T67.7 沙箱运行手册（给下一代理）

更新：2026-10-27
适用仓库：`/home/user/zhuochong`
当前分支：`arena/ba836be0-zhuochong`（不要切分支）
相关交接：[`docs/T67_7_HANDOFF_NEXT_AGENT_2026-10-27.md`](T67_7_HANDOFF_NEXT_AGENT_2026-10-27.md)

> 本手册只说明 Arena 沙箱内如何构建、运行、隔离试验和回归。它不把沙箱表现等同于 Windows 真机验收。

## 0. 先读要求，后运行命令

用户当轮明确要求、纠正、已批准内容和硬性质量标准始终排在项目施工优先级第一。先读 [`T67_7_HANDOFF_NEXT_AGENT_2026-10-27.md`](T67_7_HANDOFF_NEXT_AGENT_2026-10-27.md) 的“最高优先级”和“不可跳步的施工顺序”，再动素材或启动候选 root。流程必须是：需求清单 → 真值源/基线 → 资料核查 → `/tmp` 隔离制作 → 代理本人实际看图 → 自动回归 → 用户目视批准 → 生产接入/证据归档。不要因为预览方便、测试全绿或旧资料存在而跳过任何一道门槛。

## 1. 当前环境状态

- 真实 C 预览服务已经在 `0.0.0.0:5173` 运行，Arena 进程 ID 为 `process-a5294a89`，根目录是 `/home/user/zhuochong`。
- 该服务显示的是**仓库基线**，不是长发候选。刚检查时 `/` 和 `/test.html` 均返回 HTTP 200。
- 端口 5173 已被占用时不要再启动第二个服务，也不要用 bash `&`/后台 shell 管理长进程；先用 Arena 进程工具检查现有服务。
- 图片处理环境：`/home/user/.imgenv/bin/python`，当前含 Pillow 13.0.0、NumPy 2.4.6、SciPy 1.17.1。系统 `python3` 不保证有这些包；图像工具统一用这个绝对路径。
- 仓库预览 C 程序源于 `src/headless/main_headless.c`，通过 `--root` 读取人物、配置、数据和网页；PNG/rig 试验应放到隔离 root。
- `/tmp` 与 `~/.cache` 是临时区，可能随沙箱恢复而消失，不能当项目归档。中间草稿放这里；若某个“已修/已达标”结论需要特定图或数据复核，按 `docs/qa/README.md` 归档到 `docs/qa/`。
- 依赖用量与网络不要想当然：仓库工作流记录此沙箱无 GPU/ffmpeg/torch，资源有限；shell 出网也受白名单限制。需要外部教程优先使用 `web_search`/`fetch_page`，查 GitHub 源码优先用已配置 `gh api`/仓库脚本，只取相关文件，不在仓库根大规模克隆。

## 2. 每次开始前先做安全检查

在仓库根目录：

```bash
cd /home/user/zhuochong
git branch --show-current
git rev-parse --short HEAD
git status --short --branch
```

预期当前分支为 `arena/ba836be0-zhuochong`，本地 HEAD 基于 `a85c706`。工作区已有未提交文档改动；不得 `git reset --hard`、`git clean`、批量覆盖或一把暂存全部变更。只处理当前任务允许的文件。

检查本地工具链：

```bash
make --version | head -1
gcc --version | head -1
node --version
/home/user/.imgenv/bin/python -c 'import PIL, numpy, scipy; print(PIL.__version__, numpy.__version__, scipy.__version__)'
```

若图像环境丢失，只在沙箱重建：

```bash
python3 -m venv /home/user/.imgenv
/home/user/.imgenv/bin/pip install Pillow numpy scipy
```

对 `tools/rebuild_parts.sh` 这类流水线，可显式指定：

```bash
export ZC_PYTHON=/home/user/.imgenv/bin/python
```

## 3. 构建 C 预览服务

仅构建（不会启动服务）：

```bash
cd /home/user/zhuochong
make -s build/zhuochong_preview
```

启动命令如下。Arena Agent Mode 中应使用 `start_process`，而不是 bash 背景进程：

- **name**：`Avatar preview`
- **cwd**：`/home/user/zhuochong`
- **command**：`./build/zhuochong_preview --root . --port 5173 --bind 0.0.0.0`
- **startup_wait**：约 5 秒

Makefile 的 `make preview` 目标等价于构建后用上述参数启动；如果经 Arena 进程工具启动，也可以将命令写成 `make preview`。必须绑定 `0.0.0.0`，才能被 Arena Live Preview 代理访问。

### 在浏览器里看

- 使用 Arena **Live Preview** 面板自动提供的预览地址，不要让浏览器端 JS 请求 `localhost`、`127.0.0.1` 或容器内部地址。
- `/` 是产品预览入口；`/test.html` 是工程测试台，供操作参数/观察 API，不是最终产品 UI。
- `/test.html` 能打开只说明测试台服务正常，不代表视觉交付或真机通过。
- 前端若需要访问服务，沿用相对路径（例如 `/api/...`），不要写死本机 URL。

### 端口冲突与切换 root

当前 5173 已有仓库基线服务。若要显示临时候选：

1. 先确认正在运行的进程与 root；不要直接重复启动。
2. 使用 Arena 的 `stop_process` 停止该进程。
3. 通过 `start_process` 用同一端口和绑定地址启动 `./build/zhuochong_preview --root /tmp/t67_7_candidates/testroot --port 5173 --bind 0.0.0.0`。
4. 查看启动日志必须显示临时 root；然后在 Live Preview 面板检查。候选改动后若服务有缓存，停止并重启。
5. 测完停止临时 root 服务，再将 `--root .` 的基线预览重新启动，不要让用户看到一个被遗忘的临时测试服务。

不要通过运行 `./build/zhuochong_preview --help` 来查参数：这个二进制没有帮助页，会继续走启动流程，默认尝试绑定 5173；端口被占时会输出绑定失败。可读源码 `src/headless/main_headless.c` 中的参数解析，支持 `--root`、`--web`、`--port`、`--bind`。

## 4. 隔离 testroot（不改生产素材）

当前临时目录 `/tmp/t67_7_candidates/testroot/` 已准备好预览所需的副本，包含：

- `characters/xiaoxun/`
- `web/`
- `data/`
- `config/`
- `schemas/`
- `tools/`

它来自当前本地基线（不是远端 `d6fe833`），并非获批长发候选 rig；目录已具备 headless 预览所需的 `config/`、`characters/`、`web/`、`data/`。本轮尚未用该临时 root 实际启动预览，因此第一次启动时要确认日志读到该 root、角色 rig 正常加载。用它做进一步图层/rig 实验时，所有输出仍必须留在该目录或其他 `/tmp` 目录。

需要新建干净的临时副本时，推荐：

```bash
cd /home/user/zhuochong
TESTROOT="$(mktemp -d /tmp/zc-t67-7-XXXXXX)"
git archive HEAD | tar -x -C "$TESTROOT"
printf '临时 root: %s\n' "$TESTROOT"
```

这会从当前本地 `HEAD` 导出一份完整已跟踪树，不包含未跟踪文件。若需要测试当前临时母稿，显式把那张图复制到临时工作目录；不要把它复制进生产 `characters/`。

> `tools/rebuild_parts.sh` 会从 `tools/` 的实际位置推导项目 root，且会大范围重建/覆盖素材；**不要从仓库根运行它**。如果确实需要整链实验，必须在 `/tmp` 的完整副本中运行，并先读该脚本顶部和每一步输出。当前 T67.7 任务不需要全量 26 步重建。单独工具若有 `--root` 参数，必须把它指向临时 root；没有 `--root` 的脚本，先拷贝必要源码/数据到 `/tmp` 再执行。

当前图像候选：

```text
/tmp/t67_7_candidates/master_rebuild_unapproved_v1.png
```

它是未批准的新母稿，不是已恢复的 `frame_static_long_color_v4.png`；不能因此直接拆件或写入上面的 testroot rig。

## 5. 自动化测试与验证范围

这些命令都从仓库根目录运行：

```bash
make -s selfcheck   # 仓库静态引用/契约/卫生自检
make -s test        # C 核心单元测试
make -s web-test    # web 内核/组件测试（需要 node）
make -s smoke       # API/实际画面变化冒烟；脚本自起临时服务，使用 5200 端口
make -s asan        # AddressSanitizer/UBSan 单测
make -s check       # selfcheck + warncheck + test + asan + smoke + web-test 全套
```

- `make -s check` 较重；遇到失败先读完整输出，不要靠旧日志说“通过”。
- `make -s smoke` 会自启自停端口 5200 的服务；它与 Live Preview 的 5173 不同。
- 自动测试不检查细发丝、接缝美术、透明边颜色或用户审美；即使全绿也只能说代码/接口过闸。
- 视觉验收必须输出原尺寸、白底/深底和局部放大图，并逐处人工检查。证据若支撑验收结论，最终图/数据入库 `docs/qa/`；调参草稿留在 `/tmp`。

## 6. T67.7 图像处理规范

- 图像读写、mask、颜色分析使用：`/home/user/.imgenv/bin/python`。
- 所有派生图放在 `/tmp/t67_7_candidates/`，并用不易混淆的名字标注状态，例如 `master_rebuild_unapproved_v2.png`、`frame_static_long_trial.png`。不要继续沿用误导性的 `*_v4` 名字。
- 图片转换/透明化后至少在白底与深底各检查一次，再查看胸前拼接、鬓侧连接、肩前、腰/上胯、发梢和轮廓的放大细节。
- 颜色以 teen 原装短发实际像素为参照；冷调浅灰紫主体、蓝/青发梢必须连续。色差统计是定位线索，不可盲目全局套色；用户要求先目视找到断点再设计局部修复。
- 不要将全身概念中的脸、身体、衣物抠进发层；不要以色键残留的绿/洋红/黑白边作为可接受状态。
- 先让用户批准完整 hair-only 母稿，之后才拆六件；静止拼回通过并目视确认后才进行 `ParamHairSway` 动态沙箱测试。

### 必做的人工视觉验收（不可用数字代替）

每次视觉修改都按此顺序，不是只在最后看一次：

1. 在仓库根/临时 root 确认本次服务实际加载了哪一套资产；改了 sprite 或 rig 后，如果预览缓存了旧内容，停止并重启服务，再查看启动日志中的 `root` 与角色 rig。
2. 生成实际合成帧和 before/after 图；先检查**整帧 1×**，再看整帧约 **1.5×**，最后看接缝/边缘局部 **4–8×**。裁剪只用于放大，不能替代完整画面复核。
3. 透明 PNG 在白、灰、黑/深色底上做 alpha 合成后分别检查；不能丢掉 alpha 直接查看 RGB，也不能以棋盘格/纯黑背景掩盖透明像素的 RGB 彩边。
4. 比较必须同画布、同缩放和同姿势；逐一核对发根、脸洞轮廓、左右鬓侧、肩前、胸前、腰/上胯、发梢、遮挡补画区。写清“看到了什么、在哪个位置、计划怎样修”，之后局部修正并重复目视。
5. 运动问题必须抓真实渲染帧：`ParamHairSway` 负向、中位、正向分别检查；只看静帧或接口 HTTP 200 不算动态验收。涉及其他发型/帽子共用件时也做对应回归。
6. 如果机器指标与画面判断冲突，先验证取图、alpha 合成、坐标和当前 rig 是否正确；指标只是诊断/防回归，不能为追求全绿而牺牲用户指定的视觉要求。
7. 将真实结果用 `read_file` 打开供代理本人检查；交付候选用 `present_file` 或 Arena Live Preview 给用户看。未获用户批准不得进入下一道破坏性/生产步骤。

## 7. 状态标签与沙箱边界

- **`[测试锁]`**：单元测试、自检和 API 冒烟等自动化结果；写清具体命令与实际结果。
- **`[沙箱实测]`**：当前 C 引擎 Live Preview 中实际运行并目视检查的状态/画面；说明使用的是 repo 还是 temp root。
- **`[需真机]`**：Windows 原生窗口、透明/点击穿透、拖拽手感、托盘、实际硬件帧率等。沙箱无法验收，必须留给用户。

不得把 `[测试锁]` 自动测试通过等同 `[沙箱实测]`；也不得把任一沙箱结果升级成 `[需真机]` 完成声明。
