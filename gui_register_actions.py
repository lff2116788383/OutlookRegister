from __future__ import annotations

from PySide6.QtWidgets import QApplication, QMessageBox

from app_config import AppConfig, ConfigValidationError
from controller_factory import build_controller
from database import TaskDB
from execution_models import ErrorCode, FlowResult, RiskCircuitBreaker, Stage
from flow_runner import FlowRunner
from gui_runner import TaskThreadController
from logger import logger
from result_store import ResultStore
from runtime import RuntimeContext
from services import ProxyManager
from utils import generate_strong_password, random_email


def test_proxy_health(window) -> None:
    config = AppConfig.load(window._get_active_config_path())
    try:
        config.validate()
    except ConfigValidationError as exc:
        QMessageBox.warning(window, "配置校验失败", "\n".join(exc.errors))
        window.status_label.setText(f"配置校验失败: {exc.errors[0] if exc.errors else '未知错误'}")
        return

    proxy_manager = ProxyManager(
        static_proxy=config.proxy.url,
        dynamic_proxy_config=config.oauth2.dynamic_residential_proxy,
    )
    result = proxy_manager.check_health()

    lines = [
        f"连通状态: {'正常' if result['connect_ok'] else '失败'}",
        f"认证状态: {'已识别' if result['auth_ok'] else '未识别'}",
        f"出口 IP: {result['ip'] or '-'}",
        f"出口国家: {result['country'] or '-'}",
        f"国家匹配: {result['country_match'] if result['country_match'] is not None else '未配置'}",
        f"粘性会话: {result['sticky_session'] if result['sticky_session'] is not None else '未配置'}",
        f"消息: {result['message']}",
    ]
    QMessageBox.information(window, "代理健康检查", "\n".join(lines))
    window.status_label.setText(f"代理检测完成: {result['message']}")



def create_unique_task(window, db: TaskDB, max_attempts: int = 200) -> bool:
    for _ in range(max_attempts):
        if db.create_task(random_email(), generate_strong_password()):
            return True
    logger.warning("Unable to generate a unique email after %s attempts", max_attempts)
    return False



def create_task_callable(window):
    def task(is_cancelled) -> None:
        config = AppConfig.load(window._get_active_config_path())
        db = TaskDB()
        db.reset_in_progress_tasks()
        controller = build_controller(config)
        context = RuntimeContext(config=config, result_store=ResultStore())
        runner = FlowRunner(controller=controller, context=context)
        circuit_breaker = RiskCircuitBreaker(
            max_consecutive_risk=config.risk_control.max_consecutive_risk,
            max_failure_streak=config.risk_control.max_failure_streak,
        )

        pending_tasks = db.get_pending_tasks(limit=config.max_tasks)
        if not pending_tasks:
            created = 0
            for _ in range(config.max_tasks):
                if window._create_unique_task(db):
                    created += 1
            logger.info("Auto-created %s unique tasks before start", created)
            pending_tasks = db.get_pending_tasks(limit=config.max_tasks)

        success_count = 0
        failed_count = 0

        from threading import Lock
        counter_lock = Lock()

        def process_task(task_item) -> FlowResult:
            nonlocal success_count, failed_count
            task_id, email, password, retry_mode = task_item

            if is_cancelled() or circuit_breaker.should_stop():
                logger.info("任务已被手动停止或风险熔断终止")
                db.update_task_status(
                    task_id,
                    "pending",
                    circuit_breaker.stop_reason() or "Cancelled before execution",
                    error_code=ErrorCode.RISK_STOPPED.value if circuit_breaker.should_stop() else "",
                    stage=Stage.INIT.value,
                    risk_detected=circuit_breaker.should_stop(),
                )
                return FlowResult.fail(
                    ErrorCode.RISK_STOPPED,
                    circuit_breaker.stop_reason() or "Cancelled before execution",
                    Stage.INIT,
                    risk_detected=circuit_breaker.should_stop(),
                )

            db.update_task_status(task_id, "in_progress", stage=Stage.INIT.value)
            result = runner.process_single_flow_with_credentials(
                task_id=task_id,
                email=email,
                password=password,
                retry_mode=retry_mode,
            )
            if result.success:
                db.update_task_status(task_id, "success", stage=result.stage)
                with counter_lock:
                    success_count += 1
                return result

            db.update_task_status(
                task_id,
                "failed",
                result.error_message,
                error_code=result.error_code,
                stage=result.stage,
                risk_detected=result.risk_detected,
            )
            with counter_lock:
                failed_count += 1
            return result

        try:
            from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

            task_iter = iter(pending_tasks)
            max_workers = max(1, config.concurrent_flows)
            if config.choose_browser == "patchright":
                max_workers = 1
                logger.warning("Patchright 同步模式已强制限制为单线程，避免跨线程 greenlet 错误")
            submitted_count = 0

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_map = {}

                while not is_cancelled() and not circuit_breaker.should_stop() and len(future_map) < max_workers:
                    try:
                        task_item = next(task_iter)
                    except StopIteration:
                        break
                    future = executor.submit(process_task, task_item)
                    future_map[future] = task_item
                    submitted_count += 1

                while future_map:
                    done_futures, _ = wait(future_map.keys(), return_when=FIRST_COMPLETED)
                    for future in done_futures:
                        task_item = future_map.pop(future)
                        try:
                            result = future.result()
                            circuit_breaker.record_result(result)
                            if circuit_breaker.should_stop():
                                logger.warning("GUI risk circuit breaker triggered: %s", circuit_breaker.stop_reason())
                        except Exception as exc:
                            task_id, _, _, _ = task_item
                            result = FlowResult.fail(ErrorCode.UNKNOWN_ERROR, str(exc), Stage.INIT)
                            db.update_task_status(
                                task_id,
                                "failed",
                                str(exc),
                                error_code=result.error_code,
                                stage=result.stage,
                            )
                            circuit_breaker.record_result(result)
                            with counter_lock:
                                failed_count += 1
                            logger.exception("GUI task %s failed: %s", task_id, exc)

                        while not is_cancelled() and not circuit_breaker.should_stop() and len(future_map) < max_workers:
                            try:
                                next_task = next(task_iter)
                            except StopIteration:
                                break
                            next_future = executor.submit(process_task, next_task)
                            future_map[next_future] = next_task
                            submitted_count += 1

                    if is_cancelled() or circuit_breaker.should_stop():
                        break

            if circuit_breaker.should_stop():
                logger.warning("检测到风险，任务已自动中止: %s", circuit_breaker.stop_reason())
                if hasattr(window, "risk_status_label"):
                    window.risk_status_label.setText(f"风险状态：已熔断 - {circuit_breaker.stop_reason()}")
                if hasattr(window, "metric_risk_card"):
                    window.metric_risk_card.setText("风险监控\n已熔断")
            elif is_cancelled():
                logger.info("任务已被用户手动停止")
                if hasattr(window, "risk_status_label"):
                    window.risk_status_label.setText("风险状态：用户已停止")
                if hasattr(window, "metric_status_card"):
                    window.metric_status_card.setText("运行状态\n已中止")

            print(f"\n[Result] - 共: {submitted_count}, 成功 {success_count}, 失败 {failed_count}")
        finally:
            controller.clean_up(type="all_browser")

    return task



def start_task(window, show_popup: bool = False) -> None:
    if window.task_controller is not None:
        QMessageBox.information(window, "提示", "已有任务正在执行")
        return

    window.status_label.setText("正在启动任务...")
    QApplication.processEvents()
    try:
        config = AppConfig.load(window._get_active_config_path())
        if hasattr(window, "register_max_tasks_input"):
            config.max_tasks = window.register_max_tasks_input.value()
        if hasattr(window, "register_concurrent_input"):
            config.concurrent_flows = window.register_concurrent_input.value()
        if hasattr(window, "register_email_domain_combo"):
            config.email_domain = window.register_email_domain_combo.currentText().strip().lower()
        config.validate()
        config.save(window._get_active_config_path())
    except ConfigValidationError as exc:
        QMessageBox.warning(window, "配置校验失败", "\n".join(exc.errors))
        window.status_label.setText(f"配置校验失败: {exc.errors[0] if exc.errors else '未知错误'}")
        return
    except Exception as exc:
        QMessageBox.critical(window, "启动失败", f"读取配置文件时发生异常:\n{exc}")
        window.status_label.setText(f"读取配置失败: {exc}")
        return
    window._load_config_to_form(window._get_active_config_path(), show_popup=False)
    if hasattr(window, "register_max_tasks_input"):
        window.register_max_tasks_input.setValue(config.max_tasks)
    if hasattr(window, "register_concurrent_input"):
        window.register_concurrent_input.setValue(config.concurrent_flows)
    window.log_path.parent.mkdir(parents=True, exist_ok=True)
    window.task_controller = TaskThreadController(window._create_task_callable())
    window.task_controller.log_message.connect(window._append_log)
    window.task_controller.task_finished.connect(window._handle_task_finished)
    window.task_controller.start()

    window.start_button.setEnabled(False)
    window.stop_button.setEnabled(True)
    window.status_label.setText(f"任务已启动：任务数 {config.max_tasks} / 并发 {config.concurrent_flows}")
    if hasattr(window, "tabs") and hasattr(window, "register_tab"):
        window.tabs.setCurrentWidget(window.register_tab)



def stop_task(window) -> None:
    if window.task_controller is not None:
        window.status_label.setText("正在停止任务，请等待当前操作完成...")
        if hasattr(window, "metric_status_card"):
            window.metric_status_card.setText("运行状态\n停止中")
        window.stop_button.setEnabled(False)
        window.task_controller.stop()



def handle_task_finished(window, success: bool, message: str) -> None:
    window.status_label.setText(message)
    if hasattr(window, "metric_status_card"):
        window.metric_status_card.setText(f"运行状态\n{'已完成' if success else '已停止'}")
    if success:
        QMessageBox.information(window, "完成", message)
    else:
        QMessageBox.warning(window, "停止/失败", message)

    window.start_button.setEnabled(True)
    window.stop_button.setEnabled(False)
    window.task_controller = None
    window._refresh_result_files()
    window._load_log_file()



