# ZhuoPet 模型格式（zhuopet-layer-rig v1）

小寻的模型是一个**原创的分层 SVG 骨骼模型**。它不是 Live2D Cubism 的 `.moc3`，但参数命名、图层拆分、关节旋转、表情差分和物理摆动的思路与 Live2D 一致，方便以后迁移或替换。

## 1. 模型包

```
public/models/xiaoxun/
├─ character.svg      # 角色所有图层（可动组 + 表情差分 + 发型差分）
├─ model.json         # 部件、pivot、z-order、参数、表情、动作、发型、服装
└─ palettes.json      # 四个角色的配色（CSS 变量）
```

源文件在 `src/assets/character.svg` 和 `src/model/xiaoxun.model.json`，构建时由 `scripts/sync-model.mjs` 同步到 `public/models/xiaoxun/`。

## 2. 坐标系

- `viewBox="0 0 600 820"`，原点左上，y 轴向下。
- 脚底中心 `(300, 780)`，头部旋转中心 `(300, 400)`，胯部 `(300, 600)`。
- 所有 `data-part` 组的 `transform` 由运行时写入；初始值只做静态兜底。

## 3. 部件（parts）

每个部件在 `model.json` 的 `parts[]` 里声明：

```json
{
  "id": "twinL1",
  "label": "左马尾·上段",
  "parent": "hairBackRig",
  "z": 4,
  "pivot": [172, 218],
  "tags": ["hair"],
  "physics": { "type": "spring", "stiffness": 52, "damping": 5.2, "max": 26, "drive": "head+velocity" }
}
```

- `id` 必须和 SVG 里的 `data-part` 完全一致。
- `pivot` 是旋转锚点，运行时用 `rotate(angle cx cy)` 写入。
- `z` 只用于模型工坊排序；真实层级由 SVG 的文档顺序决定。
- `parent` 描述逻辑父子，运行时通过 SVG 的嵌套实现。
- `physics` 描述发梢/尾巴的弹簧参数，由 `engine.ts` 读取（当前引擎按部件 id 绑定，参数与 `model.json` 保持一致）。

### 当前部件（33）

| 组 | 部件 |
| --- | --- |
| 根 | `shadow`、`world` |
| 后发 | `hairBackRig`、`hairBack`、`twinL1/L2`、`twinR1/R2`、`hairTieL/R` |
| 身体 | `tail1/2`、`legL/R`、`skirt`、`neck`、`torso`、`armL/R` |
| 头 | `headRig`、`catEarL/R`、`face`、`blush`、`eyeL/R`、`browL/R`、`mouth`、`hairFront`、`ahoge`、`accessory` |
| 特效 | `starBuddy` |

### 标记

- `data-part="..."`：可动部件，运行时按 id 写入 transform。
- `data-eyeball="L|R"`：虹膜/瞳孔/高光组，运行时按 `ParamGazeX/Y` 平移。右眼在镜像组里，X 方向取反。
- `data-eye="open|closed"`：眼睛开合差分，运行时按 `ParamEyeOpen` 交叉淡化。
- `data-mouth="neutral|smile|cat|open|surprised"`：嘴型差分，运行时按表情 + 张嘴参数设置透明度。
- `data-hairstyle="twin|long|pony"`：发型组，运行时按当前发型显示/隐藏。

## 4. 参数（16）

| 参数 | 含义 | 范围 |
| --- | --- | --- |
| `ParamAngleX` | 头部左右 | -28 ~ 28 |
| `ParamAngleY` | 头部俯仰 | -18 ~ 18 |
| `ParamAngleZ` | 头部歪斜 | -20 ~ 20 |
| `ParamEyeOpen` | 睁眼 | 0 ~ 1.2 |
| `ParamMouthOpen` | 张嘴 | 0 ~ 1 |
| `ParamBrow` | 眉毛 | -1 ~ 1 |
| `ParamBlush` | 脸红 | 0 ~ 1 |
| `ParamGazeX/Y` | 视线 | -1 ~ 1 |
| `ParamArmLA/RA` | 左/右臂 | -150 ~ 40 度 |
| `ParamTwinL/R` | 左/右马尾 | -30 ~ 30 度 |
| `ParamAhoge` | 呆毛 | -35 ~ 35 度 |
| `ParamBreath` | 呼吸 | 0 ~ 1 |
| `ParamBodySway` | 身体摆动 | -8 ~ 8 度 |

## 5. 表情（9）

`neutral / happy / excited / shy / surprised / sad / sleepy / angry / love`

每个表情包含：`eyeOpen`、`mouth`、`mouthOpen`、`brow`、`blush`、`headTilt`、`headY`。引擎会把当前表情平滑插值到目标值，所以切换是渐进的。

## 6. 动作（9）

`headpat / poke / wave / feed / scared / dance / greet / sleep / wake`

动作有持续时间、情绪、手臂角度、弹跳和物理冲量。例如 `wave` 会让右臂抬到 -122° 并左右摆 16°，持续 2.4 秒。

## 7. 发型 / 服装 / 配饰

- 发型：`twin`（双马尾）、`long`（长直发）、`pony`（单马尾）、`short`（短发，只隐藏后发组）。
- 服装：4 套配色（`cream / midnight / sakura / mint`），只覆盖 CSS 变量，不改变几何。
- 配饰：`star`（星星发夹）、`cat`（猫耳 + 星星发夹）、`none`。

## 8. 物理

`engine.ts` 里的 `Spring` 是固定子步长的阻尼弹簧：

```
accel = -stiffness * (value - target) - damping * velocity
velocity += accel * h
value += velocity * h
```

- 双马尾分两段，下段跟随上段，形成鞭甩。
- 呆毛、猫耳、猫尾各有独立弹簧。
- 头部旋转速度会驱动发梢目标，动作会注入冲量。
- 被拖动时腿会摆动；睡着时眼睛闭合、冒 Z。

## 9. 运行时管线

1. `CharacterSvg` 注入 SVG 一次。
2. `PetEngine.update(dt, input)` 计算 `Pose`。
3. `applyPose(svg, pose, form)` 写 transform / opacity。
4. `applyCharacterStyle(svg, style)` 写 CSS 变量、发型、配饰。
5. React 只在 UI 状态变化时重渲染，动画不经过 React。

## 10. 怎么改

### 加一个部件

1. 在 `character.svg` 里加 `<g data-part="myPart">...</g>`，放在正确的层级位置。
2. 在 `model.json` 的 `parts[]` 里加声明（id、pivot、z、parent、tags）。
3. 在 `engine.ts` 里加一个 `Spring`（如果需要物理），在 `update()` 里算目标值。
4. 在 `applyPose.ts` 里加一行 `setTransform(root, 'myPart', ...)`。
5. 跑 `npm run model:check` 和 `npm test`。

### 加一个发型

1. 在 `hairBackRig` 里加 `<g data-hairstyle="myStyle" opacity="0">...</g>`。
2. 在 `model.json` 的 `hairstyles[]` 里加 `{ id, label, description, groups: ["myStyle"] }`。
3. `applyCharacterStyle` 会自动按 `data-hairstyle` 显示/隐藏。

### 加一套服装

在 `model.json` 的 `outfits[]` 里加：

```json
{
  "id": "myOutfit",
  "label": "我的服装",
  "description": "...",
  "palette": { "hoodie-1": "#...", "sleeve-2": "#..." }
}
```

`palette` 的 key 必须是 SVG 里用到的 CSS 变量。

### 加一个表情

在 `model.json` 的 `expressions[]` 里加，并在 `types.ts` 的 `Emotion` 和 `EXPRESSIONS` 里加同名项。

## 11. 导出

- **模型工坊 → 下载模型 JSON**：导出当前模型 + 配色 + 当前姿态。
- **模型工坊 → 下载 SVG 模型**：导出内联了配色的独立 SVG。
- **模型工坊 → 导出 PNG**：把当前姿态渲染成 1200×1640 的 PNG。
- `node scripts/render-model.mjs`：用 resvg 渲染 base/blink/smile/wave/sleep/surprised 和四角色配色图。

## 12. 与 Live2D Cubism 的关系

| | ZhuoPet | Live2D Cubism |
| --- | --- | --- |
| 格式 | 分层 SVG + JSON | `.moc3` + `.model3.json` + `.physics3.json` |
| 参数名 | `ParamAngleX` 等，与 Cubism 对齐 | 同名约定 |
| 网格 | SVG 路径 + 组变换 | ArtMesh 三角网格 |
| 变形 | 关节旋转 + 局部缩放 | Warp Deformer / 曲面变形 |
| 物理 | 弹簧 | 物理组 + 摆锤 |
| 表情 | 差分透明度 | 表情组 + 参数 |
| 开源 | 完全开源 | 运行时授权 |

**可以迁移**：角色拆件、参数命名、表情/动作列表、物理参数。
**不能直接加载**：`.moc3` 是专有二进制格式，需要 Cubism Editor 或官方运行时；本项目不包含，也不宣称兼容。

如果以后要接商业模型，建议增加一个 `mod_moc3` 加载器，把 `.moc3` 解码成统一的 `Pose`，再接 `applyPose`。本项目的参数命名已经为这件事留好了接口。
