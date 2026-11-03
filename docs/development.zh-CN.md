[English](development.md) | [简体中文](development.zh-CN.md)

# 本地开发

## 可选 DeepSeek 助手

本分支在专注中心原六页之后增加**尚未发布**的 AI 助手页。运行 `dev.ps1`，打开专注中心 → AI 助手 → AI 配置，在本地输入自己的 Key，阅读说明并点击验证保存。官方模型列表必须包含所选模型，默认 `deepseek-flash`，也可选 `deepseek-v4-pro`；深度思考需显式开启，不会在模型不可用时偷偷换模型。软件不内置开发者 Key，自动测试不发送付费请求。

聊天和设置位于 `.dev-data/agent`，Windows 凭据按该配置隔离。不要向开发者发送 Key，不要粘贴到聊天、截图或为此功能创建的环境文件中。移除 Key 或停用 AI 后，其他功能仍可离线使用。参见 [数据安全](data-safety.zh-CN.md#可选-ai-与离开设备的数据)。

```powershell
.\quality.ps1 -Mode Fast -Tests tests/test_agent.py
```

测试使用模拟网络客户端和临时数据库，覆盖 SSE、工具授权、超过 1000 条历史分页、夏令时、确认与取消、整批回滚、执行回执、配置隔离和双语主题控件。`scripts/capture_ui_baseline.py` 的确定性截图也会包含追加的新页面。CI 中不能以真实 API 调用替代模拟测试。

单独约定真实联调后，仅使用 `.dev-data` 模拟数据，整次测试最多 **6 次对话请求**，模型列表验证另计，到上限就停止。建议场景：一次带来源卡的数据查询；一次不完整的补记请求及补齐 YYYY-MM-DD、HH:MM、项目；一次确认后修改备注。重试操作前先停止并核对结果。每轮程序硬上限为 8 次，是防循环限制，不代表联调会用满。停止可阻止后续请求，但无法退回已发送请求的费用或撤销已提交记录。

自然语言校验采用保守策略：无法可靠识别日期时间时，请用户补充明确日期和 HH:MM，不能猜测。项目必须是用户选定的已有项目。完整聊天在本地保留，仅近期完整轮次进入有大小限制的请求上下文。Key 的安全存储不等于聊天备注没有隐私内容。

## 快速验证循环

使用 Windows 和 Python **3.12.10**，在项目目录执行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\dev.ps1
```

源码启动器首次在 `.dev-data` 中生成模拟演示数据，之后保留开发状态。开发配置使用独立实例锁及 Windows 互斥量，窗口标题和托盘标注 `[DEV]`，禁用真实的 Windows 开机启动注册操作。已安装的正式版可以继续运行。

修改代码后，从开发版托盘退出，再运行 `dev.ps1` 即可。日常源码验证**无需下载、打包或重新安装**，不提供热重载。

```powershell
.\dev.ps1 -ResetDemo
```

重置必须显式执行，持有开发锁，并且只允许作用于校验后的项目专属开发目录；拒绝符号链接或目录联接。不会清空正式版 AppData 配置、终止正式版进程，也不会在普通构建时删除开发数据。

## 分层检查

```powershell
.\quality.ps1 -Mode Fast
.\quality.ps1 -Mode Fast -Tests tests/test_record_hardening.py,tests/test_recovery_hardening.py
.\quality.ps1 -Mode Docs
.\quality.ps1                         # 默认 Full
```

三种模式均先运行 Ruff 和 mypy。Fast 选择持久化、计时、恢复、统计和工程核心测试；Docs 运行公共文档契约测试；Full 运行全部测试。指定测试路径会覆盖默认 pytest 集合。分项耗时、报告及最慢的 25 项测试保存在 `artifacts/quality/`。

Qt 测试共享一个 QApplication，但每项测试独立拥有并销毁运行时对象、窗口、定时器和动画；保留或恢复全局主题、语言及共享 Tooltip。动画中间帧优先主动设置时间，只保留少量有截止时间的真实时序集成检查。

## 性能与视觉对照

```powershell
.\.venv\Scripts\python.exe -m scripts.benchmark_statistics
.\.venv\Scripts\python.exe -m scripts.capture_ui_baseline artifacts/visual-before
# 修改实现，不改变模拟数据集及日期。
.\.venv\Scripts\python.exe -m scripts.capture_ui_baseline artifacts/visual-after
```

基准测试使用包含 1,000、10,000、50,000 条记录的临时 SQLite 数据库，检查新旧结果等价性，保存三次运行的中位耗时及查询次数。视觉采集覆盖中英文、六主题、专注中心各页、设置及专注面板。比较 PNG 与 `qss.json`，结构重构不应产生可见变化。

## 本地构建，不是发布

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\build-installer.ps1
```

使用 Inno Setup **6.7.3**。缺失依赖不会被静默安装；`-InstallDependencies` 表示明确选择安装。安装器命令已经包含程序 clean build 和启动检查；除非只需要便携包，否则不必先单独运行 `build.ps1`。

本地安装器带 `-local-validation.exe` 后缀。便携目录中的 `build-manifest.json` 标注 **UNPUBLISHED local validation**，记录统一版本、源码与产物摘要、Git 提交及工作区状态、工具和已解析依赖版本。这些用于诊断，不承诺不同环境下逐字节相同。

`-SkipApplicationBuild` 仅接受版本、源码摘要、产物摘要均匹配的现有包。安装验证使用随机身份、隔离数据及有超时的子进程，并保留诊断日志；绝不修改 Windows 待重启队列。正式数据和安装身份保持不变。

只有独立的标签工作流负责发布。已有 Release 资产不会被覆盖：资产集合及内容完全一致时无操作退出，缺失或不一致则失败。开发任务不等于获得推送、打标签、合并或发布的授权。

## CI 约定

`Windows quality gate` 始终运行。纯文档变更选择 Docs；代码、依赖、工作流、构建以及无法确定范围的变更选择 Full。Ruff、mypy、pytest 分步显示，并保存诊断报告。

不要持续轮询 CI，也不要在运行时读取日志；失败后再检查失败日志。必要时等待 PR 的合并门禁，但合并成功后不等待随后触发的 main 检查。

构建来源记录要求 Git 在 PATH 中可用；日常源码开发本身无需准备打包工具链。
