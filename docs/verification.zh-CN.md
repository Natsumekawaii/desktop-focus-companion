[English](verification.md) | [简体中文](verification.zh-CN.md)

# 验证指南

本文档记录可重复执行的发布检查，不包含特定电脑路径、个人数据、一次性时间戳或已过期的构建哈希。

## 1. 质量检查

创建 Python 3.12 虚拟环境，安装开发依赖，然后运行：

```powershell
.\quality.ps1
```

命令必须在不修改受 Git 跟踪文件的前提下通过以下三项检查：

1. `ruff check .`
2. `mypy app main.py`
3. `pytest -q`

测试覆盖持久化、schema 迁移、专注项目与记录、恢复、统计、响应式 Qt 控件、主题、国际化、提示气泡、页面过渡、Windows 集成、打包及安装器行为。

## 2. README 截图

截图必须使用隔离的合成测试配置生成，绝不能读取真实用户数据库：

```powershell
.\.venv\Scripts\python.exe -m scripts.capture_readme_screenshots --language zh-CN
.\.venv\Scripts\python.exe -m scripts.capture_readme_screenshots --language en-US
```

确认 `README.md` 和 `README.zh-CN.md` 引用的每张图片都存在、语言正确、不包含个人数据，并能在 GitHub 上清晰显示。

## 3. 便携程序

安装构建依赖并运行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\build.ps1
```

只有满足以下条件才接受构建结果：

- `dist\DesktopFocusCompanion\DesktopFocusCompanion.exe` 存在；
- 打包运行时冒烟测试使用隔离配置并成功退出；
- Qt 平台与图片插件、翻译、图标和内置桌面伙伴图片齐全；
- `build\` 与 `dist\` 均不包含用户数据库或设置文件。

## 4. Windows 安装器

安装 Inno Setup 6 后运行：

```powershell
.\build-installer.ps1
```

编译器缺失时，必须由开发者明确选择安装依赖：

```powershell
.\build-installer.ps1 -InstallDependencies
```

安装器冒烟测试必须验证：

- 应用运行时，命名互斥量会阻止安装或卸载，并清楚提示从托盘退出；
- 低版本安装可原位升级；
- 重装当前版本不会产生重复应用；
- 过期程序文件会被替换；
- 安装后的应用能够成功启动；
- 卸载会删除程序文件和快捷方式，同时保留隔离的用户数据标记；
- 测试前后的 Windows 待处理文件操作队列保持不变。

## 5. 发布文件

版本 `X.Y.Z` 的发布工作流必须生成：

```text
DesktopFocusCompanion-Setup-X.Y.Z.exe
DesktopFocusCompanion-Portable-X.Y.Z.zip
SHA256SUMS.txt
```

确认 Git 标签为 `vX.Y.Z`、`app.__version__` 为 `X.Y.Z`，且安装器元数据使用同一版本。从已发布的 GitHub Release 下载每个文件，并在正式公告前根据 `SHA256SUMS.txt` 验证 SHA-256。

发行说明必须同时提供英文默认版 `.github/release-notes/vX.Y.Z.md` 和简体中文版 `.github/release-notes/vX.Y.Z.zh-CN.md`。GitHub Release 正文默认使用英文，并链接到对应标签提交中的中文文档。

## 6. 手动发布冒烟测试

在干净的 Windows 测试配置中：

1. 在无需管理员权限的情况下安装。
2. 从开始菜单启动，验证托盘图标和桌面伙伴。
3. 打开专注控制、专注中心、设置和专注项目管理。
4. 切换语言和全部六套主题。
5. 分别完成一条正计时和一条倒计时记录。
6. 重启应用，确认设置和历史记录保持不变。
7. 卸载应用，确认程序目录被删除而用户数据目录保留。

未签名的发布文件可能触发 Windows SmartScreen。在项目采用可信代码签名证书前，这是预期行为。
