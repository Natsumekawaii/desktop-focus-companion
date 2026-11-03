[English](CHANGELOG.md) | [简体中文](CHANGELOG.zh-CN.md)

# 更新日志

Desktop Focus Companion 的所有重要变更都记录在此。版本号遵循[语义化版本](https://semver.org/lang/zh-CN/)，日期使用 ISO 8601 格式。

## [未发布]

## [1.0.1] - 2026-11-04

### 修复

- 仅修改备注或专注项目时完整保留原始起止时间、实际专注时长和计时元数据；开始、结束和实际时长可分别编辑。
- 恢复计时前拒绝非法时长，损坏的恢复文件保留诊断副本。
- 使用系统 IANA 时区和 UTC 时间差，正确处理夏令时切换、重复当地时间与跨午夜统计。
- 明确报告启动、持久化和刷新失败，避免将失败操作静默显示为成功。

### 新增

- 隔离的源码开发配置，包含模拟演示数据、显式重置命令和独立实例锁。
- 快速、文档和完整质量检查及耗时报告；构建来源记录、旧产物校验和有超时限制的安装器冒烟测试。

### 变更

- 减少统计的重复读取并隔离 Qt 测试资源，不改变正常界面布局和正式用户数据位置。
- 防止发布流程覆盖已有资产，将本地验证构建与公开安装包区分。
- 将全部公共文档、贡献模板、Issue 表单和发行说明拆分为互相链接的英文版与简体中文版。
- 优化 README 产品导览，通过紧凑的本地化拼图展示全部六套主题。

## [1.0.0] - 2026-09-05

### 新增

- 本地优先的正计时和倒计时专注会话，支持暂停、继续、恢复、备注和手动录入。
- 可移动、可缩放的桌面伙伴，支持自定义图片和应用图标。
- 响应式专注中心，包含概览、真实时间轴、数据分析、月度视图、专注项目、历史记录和每日回放。
- 专注项目颜色、紧凑的管理卡片、自定义选择器、动画提示气泡和轻量页面过渡。
- 简体中文和 English 界面，以及 Default、Lavender、Pink、Blue、Dark 和 Charcoal 六套主题。
- 当前用户 Windows 安装器、开始菜单快捷方式、可选桌面快捷方式、系统托盘集成和安全的升级／卸载行为。
- PyInstaller 和 Inno Setup 构建流程，包含打包运行时与隔离安装器冒烟测试。

### 隐私

- 无账号、云同步、分析遥测或广告服务。
- 用户数据保留在 `%LOCALAPPDATA%\DesktopFocusCompanion`，普通升级和卸载不会删除这些数据。

[未发布]: https://github.com/Natsumekawaii/desktop-focus-companion/compare/v1.0.1...HEAD
[1.0.1]: https://github.com/Natsumekawaii/desktop-focus-companion/releases/tag/v1.0.1
[1.0.0]: https://github.com/Natsumekawaii/desktop-focus-companion/releases/tag/v1.0.0
