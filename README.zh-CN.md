[English](README.md) | [简体中文](README.zh-CN.md)

<a id="desktop-focus-companion"></a>

<div align="center">
  <img src="assets/icons/desktop-focus-companion-128.png" width="96" alt="Desktop Focus Companion 图标">
  <h1>Desktop Focus Companion</h1>
  <p>一款本地优先、配有可自定义桌宠的 Windows 专注记录应用。</p>
  <p>
    <a href="https://github.com/Natsumekawaii/desktop-focus-companion/releases/latest"><strong>下载 Windows 安装包</strong></a>
    ·
    <a href="README.md">English</a>
  </p>
  <p>
    <img src="https://img.shields.io/github/v/release/Natsumekawaii/desktop-focus-companion?display_name=tag&sort=semver" alt="最新版本">
    <img src="https://github.com/Natsumekawaii/desktop-focus-companion/actions/workflows/ci.yml/badge.svg" alt="CI 状态">
    <img src="https://img.shields.io/badge/Windows-10%20%7C%2011-0078D4?logo=windows" alt="Windows 10 与 11">
    <img src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white" alt="Python 3.12">
    <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT 许可证">
  </p>
</div>

---

Desktop Focus Companion 是一款面向 Windows 的本地专注记录应用。它把轻量桌宠、正计时／倒计时、时间轴、趋势分析、月历和历史管理整合在一个安静、清晰的桌面体验里。数据默认只保存在你的电脑上，不需要账号，也不依赖云端服务。

![Desktop Focus Companion 中文概览](docs/images/zh/overview.png)

## 快速开始

1. 打开 [Releases](https://github.com/Natsumekawaii/desktop-focus-companion/releases/latest)，下载 `DesktopFocusCompanion-Setup-*.exe`。
2. 运行安装器。应用采用当前用户安装，通常不需要管理员权限。
3. 安装完成后从开始菜单启动；单击桌宠打开专注面板，右键桌宠打开应用菜单。
4. 在专注面板中选择项目和计时模式，开始第一段专注记录。

> [!NOTE]
> 当前公开构建尚未进行代码签名，Windows SmartScreen 可能在首次运行时显示提醒。请只从本仓库的 Releases 页面下载安装包，并核对 Release 中提供的 SHA-256。

## 功能一览

- **轻量桌宠**：可拖动、缩放、更换 PNG/JPG/JPEG/WEBP 图片，并支持自定义应用图标。
- **两种计时方式**：正计时适合开放式任务；倒计时适合明确的时间盒。
- **安全记录**：暂停、恢复、异常退出恢复与待保存重试，避免意外丢失专注进度。
- **完整洞察**：今日概览、七日趋势、项目分布、专注时段、连续专注、年度活动矩阵和每日回顾。
- **精确时间轴**：按真实起止时间绘制记录，支持短记录、重叠分栏和跨午夜展示。
- **月度视图**：紧凑月历、活跃日、月度总时长、日均、最佳日期和项目排行。
- **记录管理**：新增、编辑、删除人工记录，并在历史表格中保留项目颜色和备注。
- **双语与主题**：简体中文／English，以及 Default、Lavender、Pink、Blue、Dark、Charcoal 六套主题。
- **Windows 集成**：系统托盘、开始菜单、可选桌面快捷方式和可选开机启动。

## 界面预览

<table>
  <tr>
    <td width="50%"><strong>专注面板</strong><br><div align="center"><img src="docs/images/zh/focus-panel.png" height="420" alt="中文专注面板"></div></td>
    <td width="50%"><strong>项目管理</strong><br><div align="center"><img src="docs/images/zh/focus-items.png" height="420" alt="中文项目管理"></div></td>
  </tr>
  <tr>
    <td><strong>数据分析</strong><br><img src="docs/images/zh/analytics.png" alt="中文数据分析"></td>
    <td><strong>月度日历</strong><br><img src="docs/images/zh/monthly.png" alt="中文月度日历"></td>
  </tr>
  <tr>
    <td><strong>专注历史</strong><br><img src="docs/images/zh/history.png" alt="中文专注历史"></td>
    <td><strong>真实时间轴</strong><br><img src="docs/images/zh/timeline.png" alt="中文专注时间轴"></td>
  </tr>
</table>

### 六套全局主题

<a href="docs/images/zh/themes.png"><img src="docs/images/zh/themes.png" alt="Desktop Focus Companion 默认、浅紫色、浅粉色、浅蓝色、深色和炭黑主题"></a>

## 数据与隐私

- 所有专注记录、设置、日志和自定义资源默认保存在 `%LOCALAPPDATA%\DesktopFocusCompanion`。
- 应用不要求登录，不上传专注内容，也不包含遥测或广告服务。
- 普通升级和原生卸载不会删除用户数据库及设置；如需彻底移除数据，请在退出应用后自行删除上述目录。
- 当前版本没有云同步、自动备份或自动更新。重要记录建议定期备份用户数据目录。

更详细的可靠性设计参见 [数据安全说明](docs/data-safety.zh-CN.md) 和 [数据库说明](docs/database.zh-CN.md)。

## 从源码运行

要求：Windows 10/11、64 位 Python 3.12。

```powershell
git clone https://github.com/Natsumekawaii/desktop-focus-companion.git
cd desktop-focus-companion
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe main.py
```

运行全部质量检查：

```powershell
.\quality.ps1
```

构建便携程序与安装包：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\build.ps1
.\build-installer.ps1
```

Inno Setup 6 未安装时，可使用 `build-installer.ps1 -InstallDependencies` 显式安装依赖。生成物位于 `dist\`，不会提交到 Git。

## 项目结构

```text
app/        应用、数据、计时、统计和 Qt 界面
assets/     默认桌宠与 Windows 图标
installer/  Inno Setup 安装器定义与语言文件
scripts/    README 截图等维护工具
tests/      单元、组件、回归与验收测试
docs/       架构、数据库、数据安全和国际化文档
```

## 文档

- [架构说明](docs/architecture.zh-CN.md)
- [数据库结构](docs/database.zh-CN.md)
- [数据安全](docs/data-safety.zh-CN.md)
- [国际化开发指南](docs/i18n.zh-CN.md)
- [验证指南](docs/verification.zh-CN.md)

## 参与项目

- 提交问题前请先阅读 [贡献指南](CONTRIBUTING.zh-CN.md)。
- 安全问题请按照 [安全策略](SECURITY.zh-CN.md) 私下报告，不要公开敏感细节。
- 版本变化记录在 [更新日志](CHANGELOG.zh-CN.md)。
- 本项目采用 [MIT License](LICENSE)。

已知限制：当前只提供 Windows 64 位构建；安装包尚未签名；暂无云同步、网页端或自动更新服务。

[返回顶部](#desktop-focus-companion) · [English](README.md)
