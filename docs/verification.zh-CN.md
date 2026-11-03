[English](verification.md) | [简体中文](verification.zh-CN.md)

# 验证指南

本文档记录可重复执行的发布检查，不包含特定电脑路径、个人数据、一次性时间戳或已过期的构建哈希。

## 1. 质量检查

可选助手先运行 `python -m pytest tests/test_agent.py -q`。这些测试使用模拟提供商响应和临时 SQLite 数据库，不使用真实 Key。以模拟对话、来源卡和确认示例检查源码版 AI 页面，覆盖中英文、六主题和 760/1060px 窗口。默认完整检查包含此专项套件。

核对多会话恢复、重启后不执行旧操作、来源展开、安全 Markdown、复制、窄窗收起会话列表、模型核验和仅本次运行 Key 回退。回归不完整的 C 语言课请求、改删前实时读取、确认和取消、事务回滚、重复操作 ID、过期预览及写入成功后断网。真实 DeepSeek 测试需单独同意，并遵循 [本地开发](development.zh-CN.md#可选-deepseek-助手) 中的调用上限；离线通过不代表已验证真实模型行为。

创建 Python 3.12.10 虚拟环境，安装开发依赖，然后运行：

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
- 分发产物不包含正式用户数据库或设置；`build\` 可保留隔离的冒烟测试配置及诊断。

## 4. Windows 安装器

安装 Inno Setup 6.7.3 后运行：

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
- 按源／目标成对比较，Windows 待处理文件操作队列没有新增本应用或测试路径；无关软件变化只警告，绝不修改队列。

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
## 7. 开发加固验收

命令和报告位置见[本地开发](development.zh-CN.md)。验证仅修改备注／项目时无损保存，起止时间与有效时长独立，30 小时记录、秒数和计时元数据保留。覆盖损坏／旧版恢复文件、原子校验、存储／日志／锁故障、IANA 时区切换、夏令时缺失／重复时刻和 23／25 小时日期。每项测试后，共享 QApplication 的测试专属资源必须回到基线。

使用 1,000／10,000／50,000 条模拟记录运行统计基准。项目统计及目标刷新快照各读取一次完整记录；专注中心完整刷新保留一次完整读取及独立有界活动查询。对比中英文、六主题及支持宽度的前后截图和 QSS。编辑窗单独检查，因为结束日期和独立时长属于预期变化。

昂贵构建前检查统一版本、双语发行说明、固定依赖、Python 和 Inno Setup。验证拒绝旧包／被改动的包、已有相同 Release 无操作退出、不同资产拒绝发布、进程超时及重启队列源／目标过滤。本地构建带未发布清单，`-SkipApplicationBuild` 不绕过来源检查。可以等待必要的 PR CI，但运行中日志和 main 检查完成均不是本地开发交付前提。
