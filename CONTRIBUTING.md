# Contributing / 参与贡献

[简体中文](#简体中文) · [English](#english)

## 简体中文

感谢你愿意改进 Desktop Focus Companion。提交改动前，请先搜索已有 Issue，避免重复工作。较大的功能或影响数据格式的变更，应先开 Issue 说明用户场景和兼容方案。

### 开发流程

1. Fork 仓库，从最新 `main` 创建短生命周期分支。
2. 使用 Python 3.12 创建虚拟环境并安装 `requirements-dev.txt`。
3. 保持改动聚焦；不要提交数据库、设置、日志、构建目录或真实用户截图。
4. 为行为变更补充测试；界面改动同时覆盖中英文和主题。
5. 运行 `quality.ps1`，确认 Ruff、mypy 和完整 pytest 全部通过。
6. 提交 Pull Request，清楚描述问题、方案、验证结果和可见变化；界面改动请附前后截图。

提交信息建议使用简洁的 Conventional Commit 风格，例如 `fix: preserve timeline hit targets`。提交 Pull Request 即表示你同意按本项目 MIT License 提供贡献。

### 项目约束

- 数据库迁移必须前向、安全、可回滚失败，绝不能通过删除用户数据库“修复”问题。
- 保持 `app.__version__`、安装器版本和发布标签一致。
- 保留本地优先、无账号和无遥测的产品边界，除非先完成公开讨论。
- 不要提交未经授权的图片、字体、图标或其他受版权保护资源。

## English

Thank you for improving Desktop Focus Companion. Search existing issues before starting work. For substantial features or data-format changes, open an issue first and describe the user need and compatibility plan.

### Development workflow

1. Fork the repository and create a short-lived branch from the latest `main`.
2. Create a Python 3.12 virtual environment and install `requirements-dev.txt`.
3. Keep the change focused. Never commit databases, settings, logs, build output, or screenshots containing real user data.
4. Add tests for behavior changes; UI changes should cover both languages and relevant themes.
5. Run `quality.ps1` and require Ruff, mypy, and the full pytest suite to pass.
6. Open a pull request describing the problem, approach, verification, and visible changes. Include before/after images for UI work.

Concise Conventional Commit messages such as `fix: preserve timeline hit targets` are encouraged. By submitting a pull request, you agree that your contribution is licensed under the project's MIT License.

### Project invariants

- Database migrations must be forward-only, failure-safe, and must never “repair” a problem by deleting the user's database.
- Keep `app.__version__`, installer metadata, and release tags aligned.
- Preserve the local-first, account-free, telemetry-free product boundary unless a public design discussion agrees otherwise.
- Do not commit images, fonts, icons, or other copyrighted resources without permission.
