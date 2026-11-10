# `painted_volume_v1` — 中断的隔离负例

**状态：代理已目视拒绝；不是候选、不是隐藏真值、不是修复；不得进 C 或生产。**

这是一个手工程序化“柔和体积”新设计试验，画布以目标 hood-up 长发的可见色料/线流为参考。本人打开 `t67_71_painted_volume_v1_review.png` 后，看到新发层是一团圆钝水滴状的软发块，线条太少，根部没有自然融入可见侧发；左右局部都不合格。

该轮执行被用户中断。当前目录只有部分 underlay、clean front、composite、static registration mock、review board 和部分 ROI crops；没有完成 metrics JSON、完整输出 hash 清单及部分 crops。**不要将现有文件数或 review board 误读成完整交付。**

## 文件

- `make_t67_71_painted_volume_v1.py`：试验脚本，依赖 Pillow；当前系统 Python 默认环境没有 Pillow。之前一次运行通过会话临时 `/tmp/arena_t67_packages`，此依赖不是仓库依赖锁的一部分，也不保证未来可用。
- `t67_71_painted_volume_v1_underlay.png`、`_clean_front.png`、`_composite.png`、`_static_mock.png`：注册 WIP 层/对照。`static_mock` 的手袖来自扁平源，仅用于静态坐标展示，不是真实动作层。
- `t67_71_painted_volume_v1_review.png`：已目视拒绝的复核板。
- 左右 `*_3x.png`：部分局部 crop；非完整对照集。

关键 SHA-256：

- Review：`f45a4653836aae2a4a45d6c68e8deed30dd2adaa855855c6e3afcbed95bad7a4`
- Underlay：`eeb96fa4eddd77287820acbacbf05e817ee92cf48d579642bc0243265420ecd2`
- Composite：`2411545888b09d7a0db21ca1d058134d58a7e3ba6687895e47193f92927749ae`

完整任务状态、授权范围、失败路线和下一道验收门见 `docs/T67_71_HANDOFF_CURRENT_2026-11-05.md`。
