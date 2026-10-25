# 骨骼体系 v1（humanoid_v1）—— 先做骨骼底层还是先做别的

日期：2026-10-25 ｜ 第六十五问 ｜ 任务 T66 ｜ 契约文件 `characters/<id>/skeleton.json` ｜ 闸 `tools/check_skeleton.py`

---

## 0. 一句话结论

**先做骨骼底层，而且顺序是「契约 → 少女刚体骨接全 → 网格骨（变形器树）接进 rig → 参数/物理驱动 → 服装挂点 → 其余三形态复用」。**
黑边按你说的排到最后。理由不是"骨骼重要"这种空话，而是体检出来的三条事实：

| 事实 | 数字（本机实测） | 后果 |
|---|---|---|
| 引擎已经有变形器树，但 **rig 里一处都没用** | teen 103 个部件里用 `parts[].deformer` 的 **0 个**；chibi 47 件里 **0 个** | 手臂/头发/裙摆现在只能整块刚体转，做不出 Live2D 那种"根骨带动梢部" |
| 四个形态的骨名**对不上** | teen 15 根（含 forearm/elbow_fold/hand）· chibi 9 根（缺 6 根） | 同一套服装/动作写到 Q 版上，那段身体**悄悄不动**，没有任何报错 |
| 骨名没有契约 | 只有 `groups` 里随手起的 id | 换 AI 角色/加配件全都要重编一遍坐标 |

所以这一轮先把「骨」这件事**变成契约 + 闸**（已完成），再往上接。

---

## 1. 现状体检：引擎的"骨"其实有两层，第二层闲置

| 层 | 引擎里的东西 | 能力 | teen 用量 | 备注 |
|---|---|---|---|---|
| **刚体骨** | `rig.json` 的 `groups`（pivot + dx/dy/rot/sx/sy） | 绕关节转/缩/移，父子串联 | 15 根，103 件全部挂满 | 现在所有动作、物理、视线都只作用在这一层 |
| **网格骨** | `rig.json` 的 `deformers`（逐顶点，可 `parent` 成树，可 keyform） | 逐顶点形变、键形插值、父子复合 | 25 个网格，**却都平铺挂在部件上、没有父子、也没被任何部件反向引用** | P0 刚做出来的能力，**还没进内容** |
| 参数/绑定 | `params[].binds`（`group`/`part`/`deformer` + `param`） | 参数 → 骨 | 78 个参数 | 绑到 deformer 的极少 |
| 遮罩 | `parts[].mask` | 二值遮罩（无软边） | 13 件 | 见 §4 的 P1-3 |

一句话：**引擎那层已经就位，缺的是"把内容接上去"和"四形态共用一个骨架语义"。**

---

## 2. 骨架契约（`characters/xiaoxun/skeleton.json`，已入库）

骨架按**语义**定死 id、父级、kind、四形态是否必须有；pivot 仍写在各自 `rig.json` 里（那是素材量出来的）。

### 2.1 刚体骨（`kind: rigid`，四形态 `required: true`）

```
root
├── chest
│   ├── head
│   │   └── (网格骨) hair_side_l / hair_side_r / hair_back / hair_ahoge / hair_tail / brow_l / brow_r / ear_l / ear_r
│   ├── arm_l ─┬── forearm_l ── hand_l ── (socket_wrist_l)
│   │          └── elbow_fold_l
│   └── arm_r ─┬── forearm_r ── hand_r ── (socket_wrist_r)
├── leg_l ── foot_l
└── leg_r ── foot_r
```

### 2.2 网格骨（`kind: mesh`，按形态可选）与语义角色

| 语义角色 | teen 的实际网格 | chibi 的实际网格 |
|---|---|---|
| `hair_side_l/r` | `side_l_s` / `side_r_s` | （无侧发件） |
| `hair_back` | `back_s` | — |
| `hair_ahoge` | `ahoge_s` | `ahoge_s` |
| `hair_tail` | `longhair_mid/tip`、`twintail_l/r_tip`、`pony_mid/tip` | 同左 |
| `brow_l/r` | `brow_l_form` / `brow_r_form` | — |
| `arm_fore_l/r` | `arm_l_fore_slim/long`、`arm_r_fore_slim/long`（T66.17：两张网格都挂在骨链链尾 `fore_?_mid` 下，部件点名链根 `fore_?_root`，枢轴取**肘/腕两个 group 的 pivot** 反算 —— 袖管是斜的，绕矩形中心转袖口会横着甩开） | Q 版整条手臂一件素材：显式豁免 |
| `skirt_sway` / `skirt_hem` / `skirt_lining` / `jacket_hem` | `skirt_sway_x/y`、`skirt_hem_x`、`lining_sway_x`、`jacket_hem_x` | — |
| `tail` | `tail_relaxed_s/up_s/puff_s/tuck_s` | 同左 |

### 2.3 挂点（`kind: socket`）—— 2026-10-25 T66.19 落地

`socket_head_top` / `socket_face` / `socket_ear_l/r` / `socket_neck` / `socket_wrist_l/r` / `socket_back`。
挂点**没有 pivot**：它的位置 = 父骨 pivot + 一根"形态锚点 + 相对偏移"的向量，所以骨一转挂点跟着转，
而挂点的**名字**和所在骨由角色级契约固定。这就是"配件不漂"的机制保证。

四段分工，谁都不许替别人说话：

| 段 | 文件 | 回答什么 |
|---|---|---|
| 声明 | `characters/<角色>/skeleton.json`（`bones[]`，`kind: socket`） | **有哪些**挂点、各自挂在谁的骨上 |
| 位置 | `characters/<角色>/design/sockets.json` | **在哪**（`ref` + `pos_rel` + `unit`，四形态共用一张表） |
| 尺度 | `forms/<形态>/design/anchors.json` | 这个形态的锚点实际在哪（像素尺度） |
| 落地 | `forms/<形态>/rig.json` 的 `sockets` 段：`{id: {group, pos}}` | 引擎唯一认的东西 |

配件挂上来只要两行：

```json
{ "id": "acc_ear_cat_l", "socket": "socket_ear_l", "dpos": [0, 0] }
```

`pos` 由生成器算好一起写进 rig（美术/QA 工具要读它），但**位置只有一个来源**：挂点 + `dpos`。
引擎装载时会核对两者，差 > 1px 就报错 —— 这种不一致不会立刻显形，只会在换装/换形态之后
表现成"配件漂了"，那时候已经没人记得是哪一次改的。

探针：`GET /api/sockets.json` 给每个挂点的 `pos`（骨架摆在哪）与 `screen`（过完父骨矩阵之后
**这一刻**在哪，画布像素 × 当前缩放）。"配件跟着手腕动"能不能机检，就看 `screen` 动没动。

★ 为什么位置不写进 `skeleton.json`：那是角色级契约，一份；形态的尺度在四份 `anchors.json` 里。
把 teen 量出来的像素写进角色级文件，等于让 teen 的像素去将就 chibi（T2.2.0 量过：平均偏 92 画布像素）。

★ 这一节的旧文（2026-10-24）只写了"挂点没有 pivot，位置永远由父骨算出来"——而当时
**没有任何一件配件挂在上面，rig 里连 `sockets` 段都没有**。声明齐全、实现为零，闸也全是绿的。
T66.19 才把它接到地（LESSONS 439）。

### 2.4 豁免（waivers）

Q 版手臂是整件素材，所以 `forearm_l/r`、`elbow_fold_l/r`、`hand_l/r` 六根骨在 chibi 上**显式豁免**，
每条带 `reason` + `task: T66.2`。豁免必须写清原因，**不许悄悄少一根骨** —— 少骨的表现是
"动作里那段不动"，肉眼几乎看不出来。

### 2.5 闸（`make check` 里，13 条负控）

`tools/check_skeleton.py` 逐形态核对 8 类（2026-10-25 加 ⑧b 挂点落地，跑出 **597 项 0 红**、16 条负控）：骨架自身（id 唯一/父先声明/无环）、必需骨齐全、
不许野生骨、父子两边一致、pivot 在画布内、每个部件都挂骨、`deformer` 与 `mesh_bones` 都存在、
挂点父骨可用、每个网格骨都被语义角色收编。跑出来 **429 项 0 红**，并如实打印
**「网格骨绑定覆盖率 0/103」** —— 这条数字就是下一轮要动的靶子。

---

## 3. 施工顺序（这就是"先做什么"的答案）

| 步 | 做什么 | 为什么排在这 | 验收（可机检 + 目视） | 任务 |
|---|---|---|---|---|
| **S0** | 骨架契约 + 闸 | 后面每一步都要照着它做，先立规矩 | `check_skeleton` 0 红 · 13 负控全红 · `make check` 绿 | ✅ T66.1 |
| **S1** | 少女刚体骨接全（四形态骨名统一；Q 版补手/小臂素材或缩豁免） | 刚体骨是现在唯一在动的层，先把它做对 | 四形态骨名集合一致（除豁免）· 逐形态转每根骨目视无穿帮 | T66.2 |
| **S2** | **网格骨接进 rig**：手臂三节、侧发三节、裙摆、呆毛、耳尾 —— 这才是"每部件自己的骨" | 引擎已有能力，缺的只是内容；不做这步，动起来还是整块平移 | 覆盖率 > 0 且逐件叠图；`rot` 拉满时梢部比根部多走 ≥ 2× | **T66.3（下一轮）** |
| **S3** | 参数层接线：`params[].binds` → 骨；物理/视线/表情/口型都通过参数驱动 | "灵动"= 同一根骨被多条来源共同驱动 | 每根骨至少一条参数；关掉物理回原位 | T66.4 |
| **S4** | 服装/配件：新件声明 `bone`；替换件自动继承同名部件的骨 | 这是"服饰可动性"的全部秘密 —— 服装不需要自己造骨 | 换装后骨的绑定不变；新增件挂 socket 不漂 | T66.5 |
| **S5** | 复用规范到萝莉 / 青年女性 / Q 版；**换其他 AI 角色只换素材与 pivot** | 兼容性来自契约，不来自复制粘贴 | 新角色只写 `skeleton.json`（可引用 `humanoid_v1` 模板） | T66.6 |
| **S6** | 黑边/白边/溢色管线 | 用户明确说不急，放最后 | 见 T65.8 | T65.8 |

> 为什么 S2 不能跳到"先做动作"：动作现在只能动 `groups`，而 `groups` 是**整块刚体**。
> 手臂三节骨全接上之后，同一套动作的观感会完全不同 —— 先把骨接对，动作才值得调。

---

## 4. 自制 Live2D 底层还缺什么（体检结论，按优先级）

### P0 —— 不补就做不出"Neuro-sama 级"的动

1. **单网格多骨加权（skinning 权重）**。现在一个网格的位移只能来自**一条** keyform/amount 通路，
   两骨不能同时影响同一片顶点；裙摆要"上缘跟腰、下缘跟摆动"，只能靠多张网格叠。
   → 每顶点 `weights: [{bone, w}]`；验收：两骨反向各 50% 时顶点位移为 0。
2. ~~**父级 warp 位移场传给子**（G58.8）~~ —— **2026-10-25 T66.10 已做**。
   父件网格的位移场按 (cols×rows) 控制点做双线性取样、喂给子件的每个顶点；
   子件没有自己的网格时**借父件的分辨率**现搭一张（"三条带子不用各写网格"）。
   闸：`test_parent_warp_inherit`（三层：父场 → 有网格的子件 → 无网格的子件 + 不挂链对照）。
3. ~~**keyform 插值只有线性**~~ —— **2026-10-25 T66.11 已做**。
   每段可写 `ease`（`linear`/`in`/`out`/`in_out`/`out_back`/`out_elastic`/`out_bounce`）、
   `step`（阶梯），或四个数的三次贝塞尔 timing curve（`[x1,y1,x2,y2]`，x 必须 ∈[0,1]）。
   写错的三种情形（不认识的名字 / 第一组 key 写 ease / 贝塞尔 x 出界）都在加载时报错。
   闸：`test_keyform_ease()`，含手算值对拍（贝塞尔 `[0.25,0.1,0.25,1]` 在 x=0.5 → 0.8024）。
   **还没做**：内容侧还没有一条真 keyform 用上缓动（现有 rig 全是 amount 通路），见 T66.11b。
4. **骨骼继承模式**。Live2D 的 親子付け 有"固定位置/只继承旋转/只继承缩放"等模式；
   现在只有一种（全继承），做"头转但帽子不转"这类件就得多加一根骨。
5. **软边遮罩**。现在 `mask` 是二值（见 LESSONS 408：二值遮罩会把羽化切掉）。

### P1 —— 决定"好不好用"、会不会反复返工

6. **骨架可视化/量骨工具**：在预览上点两下就得到 pivot，并写回 `skeleton.json`。
   现在 pivot 全靠人在图上读坐标 —— 这是最容易量错、也最难发现的一环。
7. **网格编辑/权重涂刷**：哪怕最简版（矩形区域 + 衰减），否则"每根骨独立"只能靠手写控制点表。
8. **参数融合与多绑定优先级**：同一参数驱动多根骨时的叠加顺序（现在按数组顺序）。
9. **混合栈补齐**：`normal/multiply/screen` 已有，还缺 `overlay/add` 与"只在剪影内混合"。
10. **每帧网格采样成本**：103 件 × 平均 3×3 控制点还好，但 512 部件 × 5×5 会变贵 ——
    需要脏标记（参数没变就不重算）。现在每帧全算。

### P2 —— 生态与互操作

11. **`cubism model3.json` 的结构映射**：参数表、动作、物理这三类 json 是公开格式，可以映射进来；
    但 **`.moc3` 的网格数据是专有格式**，需要 Cubism Core（授权），我们不做，也不假装能读。
12. **导出**：把我们的 rig 导成别人能读的形式（图 + 参数曲线），用于社区互换。
13. **多语言/多角色的骨名别名**：不同画师的习惯叫法（`shoulderL` vs `arm_l`）要有映射表，
    否则"兼容其他 AI 形象"每次都要改闸。

---

## 5. 3D 模型与三渲二：在计划里吗？

**分开答，因为两者状态不同：**

| 项 | 在计划里吗 | 现状 | 位置 |
|---|---|---|---|
| **3D 模型（VRM/VRoid）能不能吃进来** | ✅ 在 | 只做了源码/架构预审，**没有加载过任何真实 `.vrm`**；结论是"现在不做主程序集成" | `docs/VRM_SPIKE_REPORT.md`（P1.12）· `ROADMAP` T33（0/3）· `DC42`（自渲 3D 排在 2D 主线之后） |
| **三渲二（3D 渲染成 2D 卡通观感）** | ❌ **不在** | 全仓库只有一处提到"卡通"且与渲染无关；没有任何 toon/描边/色阶 的规划 | 本轮新写：`PRODUCT_PLAN.md` 第十节 + T66.7 |

我们的定位（写进计划，避免以后又争一遍）：

- **主线永远是 2D 分层 Live2D 路线**：CPU 软件合成、零外部依赖、透明小窗、包体小。
  这是已经跑了 1000+ 单测和四形态素材的那条路。
- **3D 是可选第二后端**，前提是：① 2D 主线达标；② 有合法可测的 VRM 样例；
  ③ 用独立预览进程/目录，不把 Unity/VRC SDK 拖进主程序。
- **三渲二** = 3D 后端上的一组着色规则（色阶量化 + 边缘描边 + 单方向硬阴影 + 高光带），
  它的**前置**是 3D 后端存在，所以排在 VRM 之后；但它反过来对 2D 有用：
  同一套"卡通着色规则表"可以给 2D 立绘做**光照一致性**（比如夜里整体压暗、暖光提亮），
  这部分可以提前做（T66.8），不需要 3D 后端。

---

## 6. 验收口径（本轮）

- [测试锁] `tools/check_skeleton.py --root .` **429 项 0 红**；`--self-test` **13 例全红**。
- [测试锁] `python3 tools/selfcheck_repo.py` **576 项 0 红**（新增 ㉑ 两条）。
- [测试锁] `make -s check` 打印「== 全部保险都过了 ==」。
- [需真机] 摆骨观感（S1/S2）只能在真机看，沙箱只给数值与叠图。

---

## 7. S2 施工记录（2026-10-25 本轮）：骨链真的接上了

### 7.1 改了什么

`tools/make_rig.py` 新增 `emit_bone_chains()`（生成器里一处，rig.json 仍是生成物，符合 DC15）：

| 部件 | 链条 | 驱动参数 | lag |
|---|---|---|---|
| `hair_side_l/r` | `hair_side_l_root`(−2.6°/单位) → `hair_side_l_mid`(−5.2°) → `side_l_s` | `ParamHairSide`（根）/ `ParamHairSideS`（中段） | 中段 0.08s |
| `hair_back` | `hair_back_root`(−2.0°) → `hair_back_mid`(−4.0°) → `back_s` | `ParamHairBack` / `ParamHairBackS` | 中段 0.08s |
| `hair_ahoge` | `hair_ahoge_root`(5.0°) → `hair_ahoge_mid`(4.0°) → `ahoge_s` | `ParamHairAhoge` / `ParamHairAhogeS` | 中段 0.08s |
| `acc_tail_cat_*`（四种姿态各一条） | `tail_*_root`(1.4°) → `tail_*_mid`(3.0°) → `tail_*_s` | `ParamAccTail*Swing` | 中段 0.10s |

结果（`check_skeleton` 实测）：teen 网格骨绑定 **18/103**，chibi **9/47**，骨链节点 teen 16 个 / chibi 10 个。

### 7.2 三条踩出来的接线规矩（都写进生成器注释 + 测试）

1. **`parts[].deformer` 要点链的「根」，不是中段。** 引擎有一条校验：纯变换节点（没有 part、没有 parent）
   必须被某个部件点名，否则整份 rig 拒绝加载。第一版点的是中段 → `hair_ahoge_root` 没人引用 →
   teen 加载失败、**静默退回 chibi**（预览 exit 3 才暴露）。
2. **中段骨的绑定必须带 `lag`。** 没有 lag 时根和梢同相位被推，看着是一根刚性钟摆。
   `selfcheck` 里早有这条闸（梢部形变带行波延迟），尾巴那四条就是被它抓出来补的。
3. **绑定表必须按「根→中段→梢」排。** 逐条 `insert(0)` 会把中段排到根前面，闸照样报红；
   现在同一参数的链式绑定整体倒序插入。

### 7.3 验收

- [测试锁] `test_bone_chains()`（新增 5 条断言）：刚装载时 16 个节点严格恒等；每根骨的变换
  **恰好等于「绑定系数 × 参数最终值」**；推出参数时根 −2.6° / 中段 −5.2°（**2.0×**，分层成立）；
  只推根骨整缕也会挪（父包住子）。
- [测试锁] `check_skeleton.py` 新增「形态必须有骨链（`deformers[].parent`）」+ 负控 14 例。
- [沙箱实测] `logs/asset_qa/s2_bone_chain.png`：−1 / 0 / +1 三档，侧发梢明显外甩、
  根不动梢动；剪影量化左缘在 y=170..190 带位移 **5.0px**（−1→+1），骨链之外的老 `bend_x` 也在动。
  「静止不透明 → 极限透明」的洞只有 100~165 个像素（碎边，不是裂缝）；发根处 0 位移 = 分层正确。
- [需真机] 连续动起来的观感（是否够"飘"）只能真机判断。

### 7.4 还没做（下一轮）

- 裙摆没接链：它的网格挂在 `seg_torso` 上，而 A_chain 作用于**整个部件** —— 给裙子接旋转骨会把
  整个上身带飞（G66.6）。得先把裙子/外套下摆拆成独立件（T66.16）。
- 手臂三节骨（`arm_l → forearm_l → hand_l`）已有刚体链，但**没有网格骨**；袖子折叠目前靠
  `arm_*_fore_slim/long` 两张平铺网格（T66.17）。
- ~~网格骨之间**父级逐顶点位移不传子**（G58.8 / T66.10）~~ —— 2026-10-25 已做（见 P0-2）。
- ~~内容侧还没有真正吃这条能力的件~~ —— 2026-10-25 已做（T66.10b）：里布改成
  `inherit_from: skirt_main` + `warp_inherit: 0.35`，自己不再有网格/形变器，逐顶点场
  从表布继承；探针 `GET /api/partmesh.json` 量得到 7.917 → 2.767 px。
  遗留（美术）：里布被表布压住 99.9%，观众看不见"跟得少"，要露内衬得改素材下缘。

---

## 8. S4 施工记录（2026-10-25）：挂点真的接上了（T66.19）

### 8.1 改了什么

| 层 | 改动 |
|---|---|
| 骨架位置表 | 新增 `characters/xiaoxun/design/sockets.json`：8 个挂点各自 `ref` + `pos_rel` + `unit`（`socket_head_top` / `socket_ear_l/r` 的数值就是原来挂件的落点，所以换过去位置一像素不动） |
| 引擎 | `zrig.c`：`zrig` 加 `sockets[]`；`zpart` 加 `socket_id` / `socket`；新增 `load_sockets()`（排在 `load_groups` 之后、`load_parts` 之前）；装载期校验四类错误（未知挂点 / 父骨不存在 / 缺 pos / pos 与挂点不一致）。`zrig.h` 探针：`zrig_socket_count/id/group/pos`、`zrig_part_socket`、`zrig_socket_screen_pos`（过父骨矩阵） |
| 生成器 | `make_rig.emit_sockets()` 把骨架声明的挂点按形态锚点换算成 rig 的 `sockets` 段；`attach_emit()` 支持 `socket` / `dpos_rel`；算式统一放在 `attach_geom.socket_pos()` / `attach_geom.attach_pos()`，生成器、可移植性闸、猫耳朝向闸**共用一份** |
| 内容 | 4 件配件真接线：`acc_ear_cat_l→socket_ear_l`、`acc_ear_cat_r→socket_ear_r`、`acc_hood_up→socket_head_top`（`dpos [0,-5]`）、`acc_hair_crown_long→socket_head_top`；teen 落 8 个挂点，chibi 落 6 个（没有手骨，腕挂点按 `required:false` 跳过） |
| 探针 | `GET /api/sockets.json`：`pos`（静态）+ `screen`（跟骨） |
| 闸 | `check_skeleton` ⑧b（rig 挂点 ↔ 骨架 ↔ 位置表，597 项 / 16 条负控）；`check_form_portable`（挂点也跟着头身比缩放）；`selfcheck` 新增「挂点四段对账」16 项；`test_core` 新增 `test_socket_s4`（22 条断言） |

### 8.2 验收

- [测试锁] `test_core` **1214/0**（新增 22 条：解析成 (父骨, 坐标) / `dpos` 参与 / 父骨转 30° 挂点跟着走
  > 5px / 五类写错在装载期被打回）。
- [测试锁] `check_skeleton` **597/0**（负控 16/16：挂点没落到 rig、rig 挂点父骨与骨架不一致都要判红）。
- [测试锁] 位置不变性：换装前后 teen 104 件、chibi 49 件**逐字段比对，只有 4 件多了 `socket`/`dpos`**，
  `pos` 一个没动 —— 接线是"换出处"，不是"换位置"。
- [沙箱实测] `python3 tools/qa_sockets.py probe`：腕骨转 70.4° 后 `socket_wrist_l` 走
  **26.5~37.2px**（取决于抬手前的初始角），其余 7 个挂点 < 0.6px；`overlay` 出
  `logs/asset_qa/t66_19_sockets.png`（8 个挂点的十字 + 引线 + 坐标画在角色帧上，
  图里能确认 head_top 在呆毛根、ear 在两只耳根、face 在眼线、neck 在领口、
  back 在躯干中线 —— **2D 里"在背后"靠层号表达，不靠坐标**）。
- [需真机] 挂件在拖拽/高速抬手时的观感。

### 8.3 还没做

- **腕带/手链没有任何素材**：`socket_wrist_l/r` 落地了、能量、能挂，但没有一件美术挂在上面。
  模组作者可以直接挂（一张 PNG + 一个挂点名），本体暂时是空挂点。
- chibi 没有 `hand_l/r` 骨（整条手臂一件素材），腕挂点在 Q 版上不存在 —— 要么补分段素材（T66.2），
  要么接受"Q 版没有腕饰"。
- 单网格多骨加权（T66.9）没做：配件现在还只能整体跟一根骨，"袖子在手腕处随腕弯"仍做不到。

## 9. 多角色：脚手架 + 「契约态」（2026-10-26，T66.23）

### 9.1 问题：八个角色里只有一个是"看得见"的

硬需求是**每个 AI 独立形象**（八个角色、四形态、多套服装、多种兽娘）。到这一轮为止的实况：

| 角色 | skeleton.json | forms/*/rig.json | 美术 |
|---|---|---|---|
| xiaoxun | ✅ 39 根骨 | teen / chibi | 全套 |
| 其余 7 个 | ❌ 没有 | 0 | 0（只有 `character.json` + `dialogue.json`） |

这个状态有两个坑，性质完全不同：

1. **手工抄骨架**：想给第二个角色做形象，得照着 xiaoxun 的 `skeleton.json` 抄 39 根骨。
   抄漏一根的表现是「动作里那段不动」，肉眼几乎发现不了 —— 这正是骨架契约存在的理由。
2. **"目录看着像做完了"**：手工建一个 `characters/xxx/` 再拷一份骨架进去，目录结构和做完的角色
   一模一样。闸只查「骨架和 rig 对不对得上」，两边都空着就互相通过了 —— **空对空也是绿**。

### 9.2 解法

| 层 | 改动 |
|---|---|
| 新工具 | `tools/scaffold_character.py`：从 `humanoid_v1` 模板派生 `skeleton.json`（骨名/父子/kind/required/waivers/forms/chains 一字不差）+ `design/sockets.json`（8 个挂点）+ `forms.json`（四形态全 `planned`）+ 一份 `todo` 清单。`--list` 打印八个角色的真实进度 |
| 契约态 | 生成的骨架带 `"status": "contract_only"`：**契约齐了、素材没有**。`todo` 非空，且**不许**已经有形态 rig（有了就该改成 `full`）。`status` 缺省 = `full`，老角色不受影响 |
| 闸 | `check_skeleton` 新增第 ⑧ 条（status 合法 / contract_only 必须有非空 todo / contract_only 不许有 rig / full 必须有 rig），负控 20 例（新增 4 例）；`selfcheck::check_sockets` 对没有 rig 的角色改判「骨架必须标成契约态」，不再误报"至少一个形态落了挂点" |
| 刻意不做 | **不生成任何美术**。没有素材就是没有素材 —— 占位图、程序画的形状都不许拿来充数（用户红线）。`forms.json` 也**不写** `head_body_ratio`：那是 `anchors.json` 量出来的实测值，没量就填等于编数据 |

### 9.3 为什么 `sockets.json` 可以继承，`head_body_ratio` 不行

挂点位置是 (`ref`, `pos_rel`, `unit`) 三元组：`ref` 指向形态锚点（头顶/眼线/腕/腰…），
`pos_rel` 是相对该锚点的偏移，`unit` 说明用头高还是身高归一。**换角色后要重标**，但重标只影响
"配饰挂在哪"，不影响骨、动作、换装 —— 所以继承一份当起点是可接受的，代价写在
`inherited_from` 字段里（谁抄的谁）。头身比不一样：它是给人体比例定标的标量，
`xiaoxun` 就因为"设计稿 1:6 / 实测 1:4.65"翻过一次车，凭空写一个数必然错。

### 9.4 验收

- [测试锁] `check_skeleton` **1740/0**（负控 20/20，新增 4 条：`status` 乱写 / `contract_only` 缺 todo / todo 混空串 / `contract_only` 却有 rig 全判红）。
- [测试锁] `selfcheck_repo` **704/0**、`mod_lint --all-characters` **1834/0**、`check_form_portable` 31/0、`test_core` 1264/0。
- [沙箱实测] `python3 tools/scaffold_character.py --list`：
  `合同+素材 1（xiaoxun）、只有契约 7、还是草案 0` —— 八个角色全部有据可查，没有人是隐形的。
- 还差的（诚实记账）：七个角色**一张素材都没有**，`forms.json` 四条全 `planned`；
  见 `docs/memory/GAPS.md` 的 G66.21 / T66.23b。
