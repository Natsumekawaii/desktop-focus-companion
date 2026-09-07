[English](CONTRIBUTING.md) | [简体中文](CONTRIBUTING.zh-CN.md)

# 参与贡献

感谢你愿意改进 Desktop Focus Companion。开始工作前，请先搜索已有 Issue，避免重复工作。较大的功能或影响数据格式的变更，应先建立 Issue，说明用户需求和兼容方案。

## 开发流程

1. Fork 仓库，从最新 `main` 创建短期分支。
2. 使用 Python 3.12 创建虚拟环境，并安装 `requirements-dev.txt`。
3. 保持改动聚焦。请勿提交数据库、设置、日志、构建产物或含有真实用户数据的截图。
4. 为行为变更补充测试；界面改动应覆盖中英文和相关主题。
5. 运行 `quality.ps1`，确认 Ruff、mypy 和完整 pytest 全部通过。
6. 提交 Pull Request，清楚说明问题、方案、验证结果和可见变化。界面改动请附上前后对比截图。

建议使用简洁的 Conventional Commit 风格，例如 `fix: preserve timeline hit targets`。提交 Pull Request 即表示你同意按本项目的 MIT License 提供贡献。

## 项目约束

- 数据库迁移必须仅向前、失败安全，绝不能通过删除用户数据库来“修复”问题。
- 保持 `app.__version__`、安装器元数据和发布标签一致。
- 除非经过公开的设计讨论，否则应保留本地优先、无账号和无遥测的产品边界。
- 请勿提交未经授权的图片、字体、图标或其他受版权保护的资源。
