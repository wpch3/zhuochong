# 工作流与工作要求（WORKFLOW）—— 照这个干，不照这个就是违规

> 本文件回答："一个代理从开工到收工，每一步具体做什么、用什么命令、什么算做完。"
> 配套：`REQUIREMENTS.md`（要什么）、`MEMORY.md`（现状与决策）、`GAPS.md`（缺什么）、`TASKS.md`（任务号）、
> `JOURNAL.md`（日志）、`LESSONS.md`（教训）。

更新：2026-10-11 ｜ 分支：`arena/cc642f66-zhuochong`

---

## 一、开工五步（不做完不许动代码）

1. **读记忆区**：`docs/memory/MEMORY.md` → `REQUIREMENTS.md` → `TASKS.md` → `JOURNAL.md`（最后两篇）→ `LESSONS.md`。
2. **读交接与规格**：`HANDOVER_RESTART (1).md`（执行依据）、`docs/PROJECT_SPEC.md`（需求规格）、`docs/PRODUCT_PLAN.md`（产品规划与缺口）。
3. **确认分支**：`git status && git log --oneline -3`。只在本会话分支上工作，不切分支。
4. **跑一次基线自检**：`make test`（[测试锁]）；必要时 `bash scripts/selfcheck_all.sh`。基线先绿，再改东西。
5. **挑任务**：从 `TASKS.md` 按编号与优先级取，不自创方向；用户当轮指定的优先级**覆盖**任务表顺序。

## 二、遇到问题的查证顺序（用户硬性要求）

1. **先查七个参考项目源码**（不是摘要、不是记忆、不是猜）：
   `bash scripts/fetch_references.sh` → `~/.cache/zc-refs/`（仓库外，不入库）。
   | 项目 | 查什么 |
   | --- | --- |
   | `cubism-web-fw` | 网格渲染 `drawMeshWebGL`、遮罩 `cubismclippingmanager`、参数 id、眨眼状态机 |
   | `vpet` | 模组接口 `IModInfo.cs` / `CoreMOD.cs` / `ModLoader.cs`、交互语汇 |
   | `airi` | 语音流水线 `pipelines-audio/speech-pipeline.ts`、播放/打断 `playback-manager.ts` |
   | `ds-local-pet` | 状态机 `animation/state_machine.py`、空闲检测 `awareness/idle_detector.py` |
   | `bongocat-sdl` / `bongocat-tauri` | 透明窗与托盘思路、全局输入钩子、动作重叠 |
   | `photocraft` | 选区/蒙版/图层 `crates/algo/src/selection.rs`、`crates/engine/` |
2. 源码里找不到 → 上网查，**把 URL 与结论写进 `docs/REFERENCE_NOTES.md`**。
3. 查完 `bash scripts/clean_references.sh` 清缓存（仓库外目录，不占仓库体积）。
4. **不准照搬代码**（BongoCat-C 是 AGPL）：只学结构与思路，自己用 C 重写。

## 三、开发循环（每个任务都走一遍）

```
看现状 → 小步改 → 编译零告警 → 单测通过 → 沙箱实测 → 记日志 → 提交推送 → 汇报
```

### 3.1 编译与测试
```bash
make test                      # [测试锁] 单元测试（现 244 项），必须 0 失败
make smoke                     # 互动/动作端到端冒烟（34 项；自己起预览，判据是画面真的变了）
make                           # 预览端构建
bash scripts/selfcheck_all.sh  # 交付前七步全绿（编译告警/测试/schema/素材/Windows/预览/互动冒烟）
rm -rf build && make test      # 改了头文件或引擎结构时，先清后编，避免增量假绿
```

### 3.2 预览（动态立绘与 UI）
```bash
# 起预览（后台进程工具，名称写"Website"之类的人话）
./build/preview --root . --port 5173 --host 0.0.0.0
```
- **改了 C 代码必须重启预览进程**：磁盘二进制换了，运行中的旧进程不会自动更新（踩过）。
- 自测清单：`/`、`/app.css`、`/app.js`、`/voice_manifest.json`、`/api/info.json`、`/api/frame.png`、`/media/<文件>` 全 200；
  越界路径 `/media/../../../etc/passwd` 必须 404、`/media/Makefile` 必须 403。
- 验证动作真的变了：抓两张帧 PNG 比对差异像素数，不要只看"接口返回 200"。
- 预览只给 Arena 预览面板，**不拼外部域名**。

### 3.3 素材流水线（禁止手写坐标）
```
AI 生成 → prepare_sprites.py（抠图去噪） → make_anchors.py（量关节锚点）
        → make_parts.py（五官拆件） → make_body_parts.py（身体分段）
        → make_rig.py（生成 rig.json） → check_assets.py（机器验收，不过就重做） → 入库
```
三个把关工具（2026-10-11 新增）：
```bash
# 锚点：从剪影量出 头顶/眼线/嘴线/颈/肩/肘/腕/腰/髋/膝/踝/脚底
~/.imgenv/bin/python tools/make_anchors.py --character xiaoxun --form teen
#   → characters/<id>/forms/<form>/design/anchors.json
#   → logs/asset_qa/anchors_preview.png（人眼复核用，不入库）
# 身体分段：按锚点把单图层身体切成 头/躯干/两臂/两腿 六件，关节留重叠带
~/.imgenv/bin/python tools/make_body_parts.py --character xiaoxun --form teen
#   → sprites/seg_*.png + sprites/body_parts.json
#   → logs/asset_qa/segments_preview.png（人眼复核切线，不入库）
# 验收：形状 IoU / 色卡距离 / 关节对位 / 无损切分 / 关节不露底 / 键色与白边残留
~/.imgenv/bin/python tools/check_assets.py --character xiaoxun --form teen [--strict]
#   退出码非 0 = 不合格；自检第 4 步已接入
```
分段三条铁律（都是实测踩出来的）：
- **横切靠重叠带，竖切靠真实轮廓**。头/腿是横切，留 3% 身高的重叠带就不会露缝；
  手臂在"离身行"（剪影出现 手臂|身体|手臂 三段）以下按真实剪影抠，以上才竖切，
  否则会把外套前襟和裙边一起带走。
- **重叠带里不能存"错的内容"**。躯干顶端那条带原本是下巴，一转头就露出重影下巴；
  必须用颈线那一行向上复制成"脖子桩"（最便宜的关节补图）。
- **腿的切线只在躯干 x 范围内判**：垂在两侧的手也是独立剪影段，不排除就会把裙子
  从髋部劈成两半；还要求连续 8 行、每段够宽，否则 1px 的描边缝隙就能骗过去。
- 色卡是数据：`characters/<id>/design/palette.json`（改配色只改这里，验收自动跟着变）。
- 锚点是数据：拆件、补图、rig 枢轴、换装对位都以 `anchors.json` 为准，**不手写数字**。
- **坐标一律脚本量取**，手写魔法数字必然对不齐（踩过）。
- 改 rig 行为优先改 `tools/make_rig.py` 并重新生成，**不要只改 rig.json**，否则下次重生成就丢。
- 验收不过：重试最多 3 次，仍不过**记录原因、不入库、不标完成**。

### 3.4 配置改动
- 新增配置项 **必须同时**改 `schemas/*.schema.json`，否则自检报"缺少 schema"。
- 配置错误要能定位到文件与字段，不崩溃、不静默忽略。
- 新功能默认**关闭**；涉及费用的要有 token 上限。

### 3.5 语音
```bash
~/.cache/ttsenv/bin/python tools/voice_local.py --voice zh_CN-xiao_ya-medium \
  --text "台词" --out out.wav --pitch 1.2 --shift-method praat --noise-scale 0.45
python3 tools/voice_manifest.py     # 重渲台词后必须重跑，刷新 web/voice_manifest.json
bash tools/voice_setup.sh           # 音色包丢失时一键重建（模型不入库）
```
- **模型文件绝不提交**（`model.onnx` 出过事故，已从仓库与磁盘清掉）。

## 四、交付标准（什么算"做完"）

| 关卡 | 标准 |
| --- | --- |
| 编译 | **零告警**（告警等于没做完） |
| 单测 | `make test` 全通过；新功能必须补单测 |
| 自检 | `bash scripts/selfcheck_all.sh` **八步**全绿（第 1 步是新加的仓库静态自检） |
| 保险 | `make check` = 静态自检 + 单测 + **ASan/UBSan** + 冒烟，一条命令全跑 |
| 互动 | `make smoke` 全过；改了动作/互动/区域/眨眼一定要跑 |
| 手测 | 预览 `http://localhost:5173/test.html` 测试台点一遍（动作/互动/滑杆都在这页） |
| 实测 | 沙箱内能验证的必须真跑一遍并给**数字证据**（帧差像素数、HTTP 码、基频 Hz、文件大小） |
| 文档 | 新机制要写进 `docs/` 对应文件，并在记忆区留指针 |
| 记忆 | `JOURNAL.md` 追加本轮日志；`MEMORY.md` 更新"当前状态"；要求有变更就改 `REQUIREMENTS.md` |
| 汇报 | 中文、无 emoji、带测试标签、给文件路径与任务号、给下一步 |

### 测试标签（必须标，不许含糊）
- `[测试锁]`：单元测试与构建能保证的。
- `[沙箱实测]`：我在沙箱里真跑过（给出命令与结果）。
- `[需真机]`：窗口透明、鼠标穿透、光标、动画观感、音频播放、Windows 持久化、GPU 训练 —— **只能由用户确认，代理不许宣布完成**。

### 四.1 自检与保险（2026-10-12 加，交付前至少跑一轮）

| 命令 | 查什么 | 耗时 |
| --- | --- | --- |
| `make selfcheck` | **仓库静态自检** `tools/selfcheck_repo.py`：41 项。记忆区七件套在不在、JOURNAL 是不是最近更新过、GAPS/TASKS 编号有没有重复、所有 JSON 能不能解析、**rig 里部件/遮罩/motion_from/动作通道 target/参数绑定/物理绑定有没有指向不存在的东西**、服装与语音文件在不在、HTML id 有没有重名、JS 引用的 id 在不在、**代码里的 HTTP 端点有没有写进文档**、重建链引用的工具在不在、Python/Shell 语法、素材有没有漏 git add、logs 有没有误入库 | 1 秒 |
| `make test` | 单测 323 项（含 **2 万帧长稳**：不崩、不发散） | 20 秒 |
| `make asan` | ASan + UBSan 跑单测：越界读写、释放后使用、**内存泄漏**当场失败 | 35 秒 |
| `make smoke` | 端到端 51 项（判据是"画面真的变了"） | 30 秒 |
| `make check` | 上面四件一次跑完 | 约 90 秒 |
| `bash scripts/precommit.sh` | 提交前最小保险（静态自检 + 单测 + 素材验收） | 约 60 秒 |
| `bash scripts/install_hooks.sh` | 把上面那条装成 git pre-commit 钩子（`--no-verify` 可跳过） | — |
| `.github/workflows/ci.yml` | 每次 push/PR 在 GitHub 上重跑全套（静态自检用 `--strict`） | — |

**为什么要加这些**：单测和冒烟只能证明"代码跑得动"，证明不了配置里写错名字、文档和代码对不上、
素材漏提交、记忆区没更新。这些恰恰是真出过事的地方——删了 `*_lid` 部件忘了改动作展开表
（预览启动 exit 3）、`test.html` 两张卡片用了同一个 id、证据数字只写在 json 里没人校。
**第一次跑 `make asan` 就抓出两个真内存错**（`zdeflate.c` PNG 压缩器越界读 1 字节；
测试里手写长度 90 而字面量只有 89 字节），都已修。

## 五、收工三件事（少一件就是没收工）

```bash
bash scripts/memory_append.sh "本轮做了什么（含思考）" "遇到的问题与结论" "下一步"   # 必须 3 个参数
git add -A && git commit -m "中文说明：改了什么、为什么"
git push origin <本会话分支>
```
- push 前若被拒：`git fetch` + `git rebase`，不要 force。
- 日志通道只用 `ci-logs/`（`gh run view` 的域名在沙箱不通）。

## 六、汇报格式（用户要的样子）

1. **先给结论**，再给证据；不写"我将要…"，写"我做了…，证据在…"。
2. 每条结论附**可查落点**：文件路径 / 任务编号 / 命令 / 实测数字。
3. 用户问了几条就答几条，**逐条对位**，不合并、不绕。
4. 不确定的说不确定，不替用户宣布完成。
5. **不用 emoji**；中文；不堆形容词。
6. 结尾固定给"下一步我打算做 A→B→C，有异议现在说"。

## 七、绝对禁止（踩过或用户明令）

1. 禁止 emoji；禁止用 SVG / CSS / 程序绘图当视觉素材；禁止低分辨率放大。
2. 禁止把参考项目源码整体复制进仓库（AGPL 风险）。
3. 禁止提交模型文件（`*.onnx` 等大二进制）。
4. 禁止手写 rig 坐标；禁止直接改生成物而不改生成脚本。
5. 禁止在没跑自检的情况下说"完成"。
6. 禁止替用户宣布 [需真机] 项完成。
7. 禁止擅自改方向、擅自删旧文件。
8. 禁止重复已登记的失败路线（见 `LESSONS.md` 与交接第九节）：整图抠眼皮、闭眼图覆盖底板、羽化椭圆眼皮、颜色分割抠袖、外部部件总表直接入库、整套服装贴一张底板。
9. 禁止把同一批被否的产物换个名字再交一次（例：同底模换参数的 PSOLA 三档）。
10. 禁止给外部拼接的预览域名。

## 八、环境恢复（沙箱重启后）

```bash
# Python 图像环境
python3 -m venv ~/.imgenv && ~/.imgenv/bin/pip install pillow numpy scipy
# 语音环境（praat/parselmouth 等）
bash tools/voice_setup.sh
# 参考源码
bash scripts/fetch_references.sh      # → ~/.cache/zc-refs/（用完 clean_references.sh）
# 构建与自检
make test && bash scripts/selfcheck_all.sh
```
已知环境限制：沙箱 2 核 / 3 GB、**无 GPU**、无 ffmpeg、无 torch；出站只放行 pypi / github / npm；
`~/.cache` 与 `/tmp` **不持久**；GitHub 上的 LFS 大文件下载只会得到 134 B 指针（Kokoro 已验证，不要再试）。

## 九、文件地图（改东西前看这里）

| 要改什么 | 去哪 |
| --- | --- |
| 行为大脑（动作选择、好感、睡眠） | `src/core/zpet.c` |
| 立绘引擎（部件、通道、形变、命中） | `src/core/zrig.c` / `zrig.h` |
| 图像合成（绘制、缩放、**warp 形变**） | `src/core/zimg.c` / `zimg.h` |
| 状态机（优先级、可中断、过期） | `src/core/zsm.c` |
| 配置加载与 schema 校验 | `src/core/zconfig.c` + `schemas/` |
| Windows 平台层 | `src/win32/main_win.c`、`zw32.c` |
| 预览服务器 / Web API | `src/headless/main_headless.c` |
| 网页界面 | `web/index.html`、`app.css`、`app.js` |
| 角色数据 | `characters/<id>/`（`character.json`、`dialogue.json`、`forms/<form>/rig.json`、`outfits/`、`voice/`） |
| 全局配置 | `config/`（`ui.json`、`features.json`、`providers.json`、`voices.json`、`interactions.json`） |
| 素材工具 | `tools/prepare_sprites.py`、`make_parts.py`、`make_rig.py` |
| 语音工具 | `tools/voice_local.py`、`voice_packs.py`、`voice_manifest.py`、`voice_render.py`、`voice_setup.sh` |
| 规划文档 | `docs/PRODUCT_PLAN.md`、`PROJECT_SPEC.md`、`TRAINING.md`、`VOICES.md`、`REFERENCE_NOTES.md` |
| 记忆区 | `docs/memory/`（MEMORY / REQUIREMENTS / WORKFLOW / GAPS / TASKS / JOURNAL / LESSONS） |
