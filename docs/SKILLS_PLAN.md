# Skills 区与能力包安全规划（P1.5）

更新：2026-10-24。本文件定义可安装/调用技能的声明和治理要求，不代表 Skill 加载器、市场、沙箱或插件执行能力已实现。Skill 不是“随便运行一段脚本”的安全豁免。

## 1. Skill 定义与信任边界

Skill 是具有明确目标、版本、来源、许可、输入输出和权限声明的可选能力包。其可包含说明、结构化提示/流程和受控工具引用；如果含可执行代码/依赖，必须进入隔离执行路径，不能因安装 Skill 而自动获得代理或代码区全部权限。

- 用户安装不等于每次运行都允许所有副作用。
- AI 阅读 Skill 说明不等于可信；网页/README/示例中的指令仍是不可信数据，不能覆盖系统策略。
- Skills 不得自行注册隐藏工具、扩展自身权限、静默外传信息或阻止卸载。
- 第三方技能与内置技能分开标记；信任等级不能替代权限审批。

## 2. Manifest 必备字段

```yaml
id: vendor.skill-name
name: Human-readable name
version: 1.2.3
summary: Intended function
source: repository/package registry/local file
license: SPDX identifier or UNKNOWN
maintainer: publisher identity
integrity: signed digest or package hash
supported_app_versions: range
inputs: typed schema and sensitivity
outputs: typed schema and validation rules
capabilities: [filesystem.read, network.request, command.run]
scopes: paths, hosts, methods, commands, data classes
execution: declarative | isolated_process | external_service
limits: time, memory, disk, network, steps, cost
side_effects: files, network, account, public posting, billing
dependencies: pinned versions, licenses, scripts
update_policy: manual approval / pinned version
```

缺少许可、来源、权限、完整性或执行方式时标为“未审查”，默认不可运行；不猜测许可证。

## 3. 生命周期

`discover → inspect_metadata → trust_and_license_review → permission_preview → install_quarantined → verify_integrity → user_enable → run_with_scoped_grants → audit → update_or_disable_or_uninstall`

- 发现/搜索时显示来源、维护者、更新时间、版本、依赖、许可证和已知风险；过滤可疑包名/仿冒发布者。
- 安装前计算实际权限差异和依赖树；默认不运行安装脚本，不把包直接放进主应用可写目录。
- 安装后先隔离/验证哈希或签名，静态分析其声明与包实际内容；不可信执行代码仍需沙箱。
- 首次启用逐项展示具体能力和作用范围；用户可按任务单次授予，不必授予永久权限。
- 每次调用附带 Skill ID/版本、task/run ID 和 grant IDs，统一经过权限网关。
- 更新是新版本审批：显示代码/权限/依赖 diff；权限增加、所有者变化或签名变化必须重新审查。
- 禁用立即停止新调用并撤销运行时 token；卸载清理包自身文件和缓存，但先列明可能保留的用户产物。

## 4. 运行隔离与权限

- 声明式/纯文本 Skill 优先，无需执行时不运行代码。
- 可执行 Skill 使用独立低权限进程/沙箱；绑定用户指定工作区或临时目录；设置超时、CPU/内存/磁盘/进程数和输出限额。
- 网络访问默认关闭；如任务确需网络，按具体主机、协议、方法和数据类型审批；禁止透传环境变量/凭据。
- 文件权限按目录和读/写/删除动作分开；默认读写不超出当前任务范围；拒绝路径穿越和符号链接逃逸。
- 禁止访问系统凭据、浏览器密码、Keychain/凭证库和其它 Skill 私有目录；敏感信息不得进入 Skill 输入。
- Skill 输出必须按 schema 验证、大小限制和安全策略过滤；输出中嵌套的指令不能升级权限或自动触发另一个工具。
- Skill 不得后台常驻、跨会话自启动或自行调度循环，除非另行做用户可见自动化授权与频率/预算限制。

## 5. 代理、模板和技能关系

- 代理 profile 声明可选 Skills allowlist；用户每次任务可查看本次将调用哪些 Skills。
- 任务模板只能引用固定 ID/范围的 Skills；技能版本漂移不得悄悄改变已保存模板。
- 代理可建议启用技能，但不能自己安装/更新/改变授权；拒绝后任务需提供无该技能的安全回退或如实阻塞。
- 运行记录展示 Skill 输入摘要、输出验证结果、版本、权限和错误类别；敏感正文脱敏。

## 6. 安全与供应链测试

必须覆盖：仿冒名称/来源、缺失许可证、包哈希不匹配、依赖版本漂移、安装脚本恶意行为、提示注入、目录逃逸、秘密扫描、网络外传、递归工具调用、资源耗尽、超时取消、更新扩权、卸载残留、日志泄密和供应链账号变更。

高风险执行环境不能可靠隔离时，应拒绝执行并给用户可行替代方法，而非以免责声明放行。

## 7. P1.5 验收拆分

**规划验收（本次完成到文档层）**：manifest、许可/来源审查、隔离安装、权限差异、运行限制、更新/禁用/卸载及安全测试均已定义。

**实现验收（尚未开始）**：伪造 manifest、篡改包、越权读写/网络、恶意输出、依赖漏洞、权限扩张、取消/清理、费用上限、日志脱敏和回滚均由假技能安全测试覆盖。

**发布验收**：内置/第三方 Skill 清单明确版本与许可证；不提供未经审查的默认技能市场；用户可以离线禁用所有第三方技能。
