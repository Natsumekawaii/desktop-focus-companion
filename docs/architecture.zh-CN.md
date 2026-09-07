[English](architecture.md) | [简体中文](architecture.zh-CN.md)

# Desktop Focus Companion 1.0 架构说明

Desktop Focus Companion 是一套本地优先的 PySide6 个人专注系统。桌面伙伴只承担展示和快捷入口职责，不编码专注状态、目标、连续专注或统计逻辑。

## 组合根

`app/application.py` 构建唯一的规范运行时对象图：

```text
Database
  -> FocusItemRepository
  -> FocusSessionRepository
  -> StatisticsService
  -> GamificationService

FocusTimer + ActiveSessionStore
  -> FocusSessionManager
  -> FocusPanelController

PetWindow -> PetController
DashboardWindow -> DashboardController
SettingsDialog -> preference controllers
TrayController -> shared ordinary application menu
```

任何活动 Controller 都不依赖 `SubjectRepository`、`SessionRepository`、`StudyTimer` 或 `SessionManager`。这些 API 仅保留在明确的 schema 兼容模块和回归测试中。

## 专注领域

`FocusItem` 包含稳定身份、用户定义名称、创建时颜色和时间戳；收藏与归档字段仅为 schema 兼容性保留。`FocusSession` 保存当前项目名称快照、真实起止时间、完整分钟时长、`FocusMode`、可选倒计时目标、可选备注、内部计时器／手动来源及时间戳。

`FocusTimer` 管理基于单调时钟的 `IDLE -> FOCUSING -> PAUSED -> FOCUSING -> IDLE` 状态机。Qt 定时器只刷新界面并请求倒计时归零检查。`FocusSessionManager` 协调项目选择、恢复检查点、恰好一次的完成操作、待保存重试和 Repository 持久化。

手动记录通过 `ManualFocusEntryService` 写入同一个 `FocusSessionRepository`，因此无需特殊聚合逻辑即可进入所有统计、目标、连续专注、回放和分布流程。

## 界面边界

- `PetWindow` 只按精确缩放后的图片尺寸显示一张静态 PNG/JPG/JPEG/WEBP，保持纵横比，接收单击、拖动和右键输入，并发出用户意图；它不拥有或复制计时状态。
- `FocusPanel` 使用内部 `QStackedWidget` 稳定维护空闲选择、开始前和活动状态布局。空闲页显示带标签的每日／每周目标进度，并提供一个按名称排序、仅显示文字的选择器及代码绘制的主题箭头。透明圆角弹层使用专用代理：36px 项目行采用保存的项目颜色，当前项使用柔和圆角背景和矢量勾选标记，键盘候选状态保持独立；40px 管理入口前保留 9px 分隔区，弹层高度严格等于可见行与内边距总和，绝不调用原生项目选中绘制。空闲页还提供正计时／倒计时分段选项、目标和可选备注。活动页在稳定的视觉区域中切换精确到秒的纯文本 `HH:MM:SS` 正计时与现有主题倒计时圆环，并提供暂停／继续／完成操作。
- `FocusItemDialog` 不负责持久化，只发出 create(name, color)、rename 和 delete 意图。等宽统计卡片为只读；16 色调色板仅存在于紧凑的新建对话框。
- `DashboardWindow` 使用按专注、洞察和资料库分组的响应式左侧栏。侧栏驱动单一共享 `QStackedWidget`；宽度低于公共断点时折叠为图标栏，同时保留 Tooltip、无障碍名称、键盘焦点及现有 `show_*` 兼容方法。
- 专注中心和设置页栈共用 `AnimatedPageStack`。可见页面切换会立即更新真实栈索引，把离开页面帧保留在鼠标穿透的覆盖层中，再通过 160ms `OutCubic` 淡入和 4px 上浮归位显示目标页面。快速选择会从当前合成帧重新定向；重复选择、隐藏、缩放、关闭、语言和主题路径会立即结束动画，不重建页面或丢失状态。
- 专注中心页面接收已完成查询或聚合的数据，用于概览、时间轴、回放、分析、分布、专注活动、基于月历的月度统计、专注项目和历史记录；页面本身不执行 SQL。可复用响应式网格会重排密集指标，而非强制固定列数。
- `MonthlyCalendarWidget` 把密集 `DailyTotal` 数据映射到紧凑、只读、周一开始的网格。日期格在完整宽度的星期槽下保持居中，最大 80×72px，并为窄布局保留 50px 安全宽度。日期和 `h/min` 时长使用固定的第一、第二文本槽，因此活动状态不会移动日期基线。所有有记录日期使用同一种由主题生成、以格子中心对称的浅色径向渐变和低对比中性边框；今天和悬停只提供信息反馈，不产生点击选择或持久化查询。
- `SessionEditorDialog` 验证本地手动／编辑字段并返回规范专注值。
- `SettingsDialog` 使用左侧分类栏和 `QStackedWidget` 展示外观、桌面伙伴、计时器、数据和关于页面。它发出原有偏好值，Controller 继续执行即时或防抖的原子持久化。

## 统计数据流

```text
bounded/all-session focus_sessions query
  -> allocate actual duration across local midnight
  -> DailyTotal / FocusItemTotal / HeatmapData / MonthlyStatistics
  -> DailyReplaySummary / FocusAnalyticsSnapshot
  -> Dashboard and Replay widgets
```

每次完整刷新专注中心都会创建一个不可变、仅限本次请求使用的 `DashboardStatisticsSnapshot`。它只读取一次完整专注历史，并从同一有序集合计算今日数据、七日趋势、专注项目排行、分析数据、最近记录和历史记录，刷新完成后立即丢弃。专注活动继续使用独立的有界历史查询；月度和单日时间轴保持有界查询，当前月份适用时会复用快照中的月度结果。不引入跨刷新缓存。

倒计时目标仅为元数据。所有总计都使用完整分钟的 `duration_seconds`；不足一分钟的专注记录不会保存，旧记录通过 schema v5 设置标记执行一次性清理。专注活动、时间轴、环形图和月度绘制绝不在 `paintEvent` 中查询数据库。

数据分析通过一个分段主趋势展示日、周和月视图。周视图和分析页绘制折线／面积趋势；回放将 24 小时总量映射为等高热力带；月度页使用 50–80px 宽的紧凑月历，所有活动日共享与时长无关、由主题生成且中心对称的径向渐变，不显示彩色外框；环形图展示比例分布。月历会针对普通及悬停渐变中对比最弱的色阶选择稳定文字色；非活动格保持纯色，活动仅填充预留的第二行，不移动固定 12pt 日期。专注活动只执行一次有界查询，其名义 365 天起点向前扩展到周一，生成 365–371 个连续日期及稳定的 7×53 矩阵，并保证首列完整。日视图仅提供悬停；周视图将自然周总量映射为自底向上的比例柱；累计视图把逐周累计值映射为单调方格阶梯。切换模式时先把旧格子融合进不透明表面，再通过从左上到右下的柔和逐格波纹显示目标矩阵；快速选择会合并到最后目标且不移动共享月份坐标轴。不透明 RGB 悬停插值指向一天或完整一列，鼠标穿透的提示框锚定在目标上方。目标进度条始终表示语义上的完成进度。

专注项目管理只提供新增、重命名和删除。新建对话框的 16 个色块在内部发出稳定十六进制值，但显示本地化颜色名称；运行时不提供重新着色信号。删除前先查询影响范围；确认后在一个 SQLite 事务中删除关联记录和项目，再刷新所有聚合界面。活动、待保存和可恢复项目受删除保护。

## 恢复与可靠性

活动检查点 v4 保存规范的 `focus_item_id`、`focus_item_name`、模式、实际累计秒数、状态、目标、备注、时间戳和恢复令牌。加载器会把 v1–v3 的 `subject_*`／`study_mode` 字段映射到同一数据类。恢复后进入暂停状态且不计算应用停机时间。待保存记录使用唯一数据库恢复令牌。

设置采用临时写入、flush、fsync 和原子替换。SQLite schema 迁移使用单个显式事务，同时更新版本并执行完整性检查。应用绝不会删除或重建故障用户数据库。

## 桌面与资源

`ApplicationPaths` 是内置默认桌面伙伴和应用图标的唯一来源。冻结构建从 `sys._MEIPASS` 读取内置文件，所有可写文件始终位于 `%LOCALAPPDATA%\DesktopFocusCompanion`。

`PetAssetManager` 和 `AppIconManager` 负责验证、复制、解析和安全回退。运行时不实现 GIF 动画、桌面伙伴状态层或复杂互动机制。活动专注状态保留在 `FocusPanel` 中；专注中心只呈现聚合历史和分析。

`TrayController.menu` 是系统托盘和桌面伙伴右键共用的 `RoundedMenu`。透明顶层画布和自绘圆角表面可避免原生直角伪影，同时保留标准 `QMenu` 操作。菜单提供一个打开现有专注中心的入口，以及设置、桌面伙伴显示和退出。桌面伙伴左键仍是切换专注面板的唯一常规入口；最近项目选择只存在于该面板中。

专注面板在空闲页和活动页之间提供仅属于界面的 `PreFocusCountdownWidget`。静默的 3-2-1 动画开始前会冻结启动参数，但只有完成信号才会调用 `FocusSessionManager.start()`。关闭或隐藏面板会取消待启动请求，因此预备阶段不会改变领域 `TimerState`、SQLite 数据、倒计时目标或恢复检查点。

## 国际化与主题

`LocalizationManager` 管理当前 `QLocale`、JSON 目录查询、键集合一致性校验和 `language_changed`。控件保留原始值，并在该信号发出时重新格式化和翻译。用户输入的名称和备注绝不翻译。

`ThemeManager` 管理六套兼容且经过细化的主题：Default、Lavender、Pink、Blue、Dark 和 Charcoal。Charcoal 是使用纯白主文字和银灰强调色的中性炭黑主题，原有偏紫的 Dark 保持不变。每套主题都提供语义化 Canvas、Surface、Elevated、Accent、文字、交互、焦点、状态、图表色板和热力图 Token。共享尺寸定义字体层级、8pt 间距节奏、控件高度、圆角、图标尺寸、侧栏宽度和响应式断点。现有主题 ID 与持久化设置保持不变，`charcoal` 作为新的稳定 ID 追加。

运行时主题切换使用协调的双快照过渡。每个符合条件的可见应用表面先在活动窗口上保留完整源帧；应用新色板、QSS、图标和自绘颜色后，捕获完整渲染的目标帧并置于下方。源帧随后通过 220ms `OutCubic` 淡出，合成器不会暴露只完成部分重绘的 Qt 后备存储。透明专注面板保留角落 Alpha；快速选择复用当前合成帧；目标捕获失败时回退到同步重绘的即时切换，避免黑帧或空白帧。桌面伙伴和临时弹层不参与该动画。

字体通过 `QApplication.setFont()` 应用，而非单一 QSS 字体族。`ThemeManager.set_language()` 为 zh-CN 依次选择 Microsoft YaHei UI、Microsoft YaHei、DengXian、Noto Sans SC、SimHei；为 en-US 选择 Segoe UI 并附带 CJK 回退字体。创建应用时只连接一次 `LocalizationManager.language_changed`，所以已有控件、菜单、对话框和自绘图表会立即更新，同时保留活动主题和业务状态。

可复用 Qt 基础组件由内部 `component_controls`、`component_layouts`、`component_widgets` 和 `page_transition` 模块实现；`app/ui/components.py` 继续作为稳定兼容门面并重新导出全部现有公开名称。专注中心表格和专注活动内部实现同样位于 `dashboard_widgets`，而 `dashboard.py` 保留既有导入和别名。因此 PageHeader、SectionSurface、MetricStrip、EmptyState、SegmentedControl、IconButton、ListRow、ResponsiveGrid、StatusPill、CircularTimerWidget、ThemedDateEdit 和 DurationPicker 的外部契约保持不变。DurationPicker 通过可独立滚动的小时／分钟选择器暴露现有整数分钟接口。所有组合框式字段继承共享的滚轮安全选择行为：关闭状态的字段不会因滚轮改变值，而会把输入转交给最近的滚动页面。弹层打开时，`AnimatedAnchoredPopup` 会在 Qt 把原生滚轮事件分发给子控件前，先在所属或弹层 `QWindow` 上分类事件；位于锚点字段或弹层表面的手势只浏览相关滚动条而不激活选项，外部页面滚动则关闭弹层并正常继续。日期字段把手势转换为月份浏览，时间字段将其路由到已聚焦或指针所在的小时／分钟列。普通内容表面保持平整并使用浅分隔线；`apply_elevation` 只用于悬浮或有意抬高的表面。中央 QSS 负责应用外壳、两套侧栏、设置区段、专注面板、控件、菜单和对话框的悬停、按下、选中、禁用及键盘焦点状态；生成文本由纯样式片段组成，不改变选择器顺序或字节。`IconSystem` 为专注中心、设置、托盘和桌面伙伴菜单绘制统一的主题线性图标。

旧版等级相关数值继续保留在原有兼容服务中，以保证 schema 和数据行为不变，但任何界面、菜单、通知、回放或分析都不会展示它们。

## 打包

`DesktopFocusCompanion.spec` 包含默认桌面伙伴、全部应用图标、zh-CN／en-US 语言目录、Qt 插件和规范应用模块。它会拒绝通过构建主机 PATH 发现的第三方 ICU DLL，因为 Windows 版 Qt 依赖无版本后缀的系统 ICU API。`build.ps1` 使用 `--clean` 调用 PyInstaller，随后针对隔离配置启动打包后的 EXE，并要求其按预期干净退出；DLL 或导入错误对话框因此会使构建失败。

`build-installer.ps1` 使用 Inno Setup 把 onedir 输出编译为 `dist\installer` 下的当前用户安装器。固定安装器 AppId 是升级边界。程序文件位于 `%LOCALAPPDATA%\Programs\DesktopFocusCompanion`，持久用户状态则独立保存在 `%LOCALAPPDATA%\DesktopFocusCompanion`；升级会完整替换程序目录，卸载删除二进制文件和系统入口，但不删除专注历史或偏好。应用运行期间，单实例保护器还会持有与 Inno Setup `AppMutex` 对应的稳定 Windows 命名互斥量，因此安装和卸载会提示用户从托盘退出，而不是删除占用中的文件或安排重启时清理。安装器验证会使用新的临时 AppId 进行编译，依次安装低版本基线、原位升级、重复安装当前版本，再通过打包运行时检查启动已安装程序，最后验证干净卸载、数据保留，以及 Windows 待处理文件操作队列未发生变化，全程不触碰真实安装或开机启动项。
