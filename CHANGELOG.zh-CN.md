[English](CHANGELOG.md) | [简体中文](CHANGELOG.zh-CN.md)

# 更新日志

Desktop Focus Companion 的所有重要变更都记录在此。版本号遵循[语义化版本](https://semver.org/lang/zh-CN/)，日期使用 ISO 8601 格式。

## [未发布]

### 变更

- 将全部公共文档、贡献模板、Issue 表单和发行说明拆分为互相链接的英文版与简体中文版。

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

[未发布]: https://github.com/Natsumekawaii/desktop-focus-companion/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/Natsumekawaii/desktop-focus-companion/releases/tag/v1.0.0
