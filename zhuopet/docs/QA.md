# QA 报告

## 1. 自动化测试

```
npm test
```

结果：**4 个测试文件，48 项全部通过**。

| 文件 | 覆盖 |
| --- | --- |
| `tests/engine.test.ts` | 弹簧收敛/边界、姿态有限、眨眼、睡眠闭眼、说话口型、挥手手臂、减少动画 |
| `tests/brain.test.ts` | 意图识别、记忆抽取/去重/遗忘、名字、回忆、安慰、冒犯、身份、时间、称呼、情绪、时段、主动台词、系统提示词 |
| `tests/model.test.ts` | 模型包完整性、部件与 SVG 对齐、pivot 边界、参数范围、表情、发型组、配色覆盖、服装变量、SVG 无 NaN/undefined、非平凡规模 |
| `tests/app.test.tsx` | 桌面渲染、打开聊天、本地回复、记忆写入与展示、首次引导、设置页签、模型工坊 |

## 2. 模型渲染 QA

```
node scripts/render-model.mjs
node scripts/validate-model.mjs
```

- `docs/qa/model_base_xiaoxun.png`：基础姿态。
- `docs/qa/model_states.png`：待机 / 眨眼 / 微笑 / 挥手 / 睡着 / 惊讶。
- `docs/qa/model_palettes.png`：四个角色配色。
- 模型校验输出：33 部件、16 参数、9 表情、9 动作、4 发型、4 服装、4 配色。

## 3. 真实浏览器 QA

```
node scripts/qa-browser.mjs
```

使用 `@sparticuz/chromium` + `puppeteer-core`，在真实 Chromium 里跑完整流程。最近一次结果：

| 检查 | 结果 |
| --- | --- |
| 控制台错误 | 0 |
| 页面异常 | 0 |
| 桌面溢出 | 无（scrollWidth = innerWidth = 1440） |
| 角色尺寸 | 350 × 478，位于 (545, 225) |
| 部件数 | 34 个 `data-part` |
| 顶栏 / 底部胶囊 | 66px / 546×65，位于底部 18px |
| 聊天抽屉 | 404×720，右侧 15px，底部 100px |
| 消息流程 | 发送后 3 条消息（1 用户 + 2 宠物，含初始问候） |
| 换装栏 | 打开 |
| 设置窗口 | 921×705，居中 |
| 模型工坊 | 打开，预览 SVG 400×547 |
| 移动端 390×844 | 角色 179×245，dock 374×51，无横向溢出 |
| 首次引导 | 显示 → 填写名字 → 关闭，名字保存 |

截图：`docs/qa/qa_onboarding.png`、`qa_desktop.png`、`qa_pet.png`、`qa_chat.png`、`qa_chat_reply.png`、`qa_dressup.png`、`qa_settings.png`、`qa_studio.png`、`qa_mobile.png`。

## 4. 视觉 QA（差异掩码）

`scripts/qa-visual.mjs` 在隐藏角色前后各截一张图，做差得到角色真实轮廓：

- 角色像素 80,401，bbox `(42, 25) - (319, 465)`，在 350×479 的截图内。
- 轮廓呈大头、窄身、双腿的 Q 版比例，头顶有呆毛，右侧有星星伙伴。
- 星星伙伴屏幕位置 `(782, 367)`，62×61，在角色右侧，不再跑出画布。
- SVG `getBBox()` 为 `(57, 24, 492, 771)`，在 600×820 画布内。

颜色分布（角色像素）：

| 色系 | 占比 |
| --- | --- |
| 奶油/白（卫衣、袜子） | 27.3% |
| 淡紫（头发） | 31.0% |
| 肤色 | 19.0% |
| 藏青（裙子） | 14.9% |
| 薄荷绿（袖子、鞋） | 4.4% |
| 深色线稿 | 14.9% |

说明配色变量已正确注入，角色不是空白或单色块。

## 5. 已知问题 / 边界

- 沙箱内没有图形界面，无法做“人眼审美”最终验收；视觉 QA 只能保证几何、配色、布局和渲染正确。角色是否“可爱”需要你在预览里亲自看。
- 浏览器语音合成依赖系统音色；沙箱/部分 Linux 环境可能没有中文音色，此时会静音但不影响文字。
- Electron 二进制在沙箱里没有下载；桌面端代码已就绪，需在本机 `npm install` 后运行。
- 模型是原创 SVG 分层格式，不是 Live2D 官方 `.moc3`。
- 云端大模型需要 Key；不填也能用本地大脑。

## 6. 复现

```bash
cd zhuopet
npm install
npm test
npm run model:check
node scripts/render-model.mjs
# 终端 1
npm run dev
# 终端 2
node scripts/qa-browser.mjs
node scripts/qa-visual.mjs
```
