# OutlookRegister

当前版本已完成结构化重构，补齐了本地日志、SQLite 任务库、控制器工厂与 [`PySide6`](requirements.txt) 图形界面入口。

## 当前结构

- [`main.py`](main.py)：命令行生产入口，负责从任务库中取任务并执行。
- [`launch_gui.py`](launch_gui.py)：桌面界面启动入口。
- [`start_gui.bat`](start_gui.bat)：Windows 一键检查依赖并启动图形界面。
- [`controller_factory.py`](controller_factory.py)：统一构建浏览器控制器，消除 GUI 与 CLI 对入口模块的耦合。
- [`database.py`](database.py)：基于 SQLite 的本地任务库。
- [`logger.py`](logger.py)：统一日志模块，输出到控制台与 [`Results/app.log`](Results/app.log)。
- [`gui_app.py`](gui_app.py)：PySide6 主窗口，包含配置、日志、结果视图与任务准备功能。
- [`gui_runner.py`](gui_runner.py)：后台线程执行与日志转发。
- [`gui_state.py`](gui_state.py)：界面状态常量与结果文件定义。
- [`app_config.py`](app_config.py)：统一配置模型、持久化与运行目录初始化。
- [`flow_runner.py`](flow_runner.py)：封装单任务与并发任务执行流程。
- [`result_store.py`](result_store.py)：集中处理结果写入。
- [`runtime.py`](runtime.py)：运行期上下文与协议定义。
- [`controllers/base_controller.py`](controllers/base_controller.py)：浏览器控制器基类与公共流程。
- [`controllers/patchright_controller.py`](controllers/patchright_controller.py)：Patchright 控制器实现。
- [`controllers/playwright_controller.py`](controllers/playwright_controller.py)：Playwright 控制器实现。
- [`get_token.py`](get_token.py)：OAuth2 Token 获取流程。
- [`services.py`](services.py)：第三方服务与代理轮换封装。
- [`utils.py`](utils.py)：随机邮箱与密码工具函数。
- [`.gitignore`](.gitignore)：忽略缓存、日志、结果文件与虚拟环境目录。

## 可用性改进

1. 入口解耦：[`gui_app.py`](gui_app.py) 不再依赖 [`main.py`](main.py) 内部函数，而是统一调用 [`controller_factory.py`](controller_factory.py)。
2. 配置统一：[`app_config.py`](app_config.py) 同时兼容旧版字符串代理配置和新版代理轮换字段。
3. 本地任务库：[`database.py`](database.py) 提供任务初始化、状态更新、恢复卡死任务、统计与清空能力。
4. 统一日志：[`logger.py`](logger.py) 使用滚动日志文件，适合长期运行。
5. GUI 增强：支持保存配置、准备任务、查看日志、查看与清空结果文件。
6. 依赖固定：[`requirements.txt`](requirements.txt) 统一为明确版本，降低环境漂移问题。

## 图形界面功能

通过运行 [`launch_gui.py`](launch_gui.py) 或 [`start_gui.bat`](start_gui.bat) 可打开桌面端控制台，包含以下能力：

1. 配置编辑：直接修改 [`config.json`](config.json) 中的常用参数。
2. 日志展示：实时显示任务输出，并写入 [`Results/app.log`](Results/app.log)。
3. 结果浏览：自动刷新查看 [`Results/logged_email.txt`](Results/logged_email.txt)、[`Results/unlogged_email.txt`](Results/unlogged_email.txt)、[`Results/outlook_token.txt`](Results/outlook_token.txt)。
4. 结果清理：支持单个结果窗口清空、全部结果清空、日志文件清空。
5. 任务准备：在 GUI 中重建本地 SQLite 任务库。
6. 受控启动：从界面调用现有执行流程。

## 运行方式

### 命令行运行

1. 安装依赖：`pip install -r requirements.txt`
2. 如需 Playwright 浏览器内核：`playwright install chromium`
3. 按需修改 [`config.json`](config.json)
4. 运行：`python main.py`

### 图形界面运行

1. 安装依赖：`pip install -r requirements.txt`
2. 直接运行：`python launch_gui.py`
3. 或双击运行：[`start_gui.bat`](start_gui.bat)

## 输出目录

运行结果写入 [`Results/`](Results/) 目录下：

- [`Results/logged_email.txt`](Results/logged_email.txt)
- [`Results/unlogged_email.txt`](Results/unlogged_email.txt)
- [`Results/outlook_token.txt`](Results/outlook_token.txt)
- [`Results/app.log`](Results/app.log)
- [`Results/tasks.db`](Results/tasks.db)
