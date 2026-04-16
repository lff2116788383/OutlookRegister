from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

from account_io import export_token_accounts, load_email_accounts
from app_config import AppConfig, OAUTH_TOKEN_ACCOUNTS_PATH, PENDING_OAUTH_ACCOUNTS_PATH, ensure_runtime_dirs
from controller_factory import build_controller
from database import TaskDB
from execution_models import ErrorCode, FlowResult, RiskCircuitBreaker, Stage
from flow_runner import FlowRunner
from logger import logger
from mam_client import build_microsoft_account_manager_client
from oauth_account_runner import run_oauth_accounts
from result_store import ResultStore
from runtime import RuntimeContext
from utils import generate_strong_password, random_email


def _create_unique_task(db: TaskDB, max_attempts: int = 200) -> bool:
    for _ in range(max_attempts):
        if db.create_task(random_email(), generate_strong_password()):
            return True
    logger.warning("Unable to generate a unique email after %s attempts", max_attempts)
    return False



def process_single_task(controller, task_id: int, email: str, password: str, retry_mode: str, db: TaskDB, runner: FlowRunner) -> FlowResult:
    db.update_task_status(task_id, "in_progress", stage=Stage.INIT.value)
    result = runner.process_single_flow_with_credentials(
        task_id=task_id,
        email=email,
        password=password,
        retry_mode=retry_mode,
    )
    if result.success:
        db.update_task_status(task_id, "success", stage=result.stage)
        return result

    db.update_task_status(
        task_id,
        "failed",
        result.error_message,
        error_code=result.error_code,
        stage=result.stage,
        risk_detected=result.risk_detected,
    )
    return result



def initialize_tasks(db: TaskDB, config: AppConfig) -> None:
    stats = db.get_stats()
    total_existing = sum(stats.values())
    if total_existing >= config.max_tasks:
        return

    missing = config.max_tasks - total_existing
    created = 0
    logger.info("Initializing %s new tasks in database", missing)
    for _ in range(missing):
        if _create_unique_task(db):
            created += 1
    logger.info("Initialized %s/%s unique tasks in database", created, missing)



def run_cli_register() -> None:
    config = AppConfig.load()
    config.validate()
    ensure_runtime_dirs()
    db = TaskDB()

    logger.info("Starting OutlookRegister register-only mode")
    initialize_tasks(db, config)
    db.reset_in_progress_tasks()
    controller = build_controller(config)
    context = RuntimeContext(config=config, result_store=ResultStore())
    runner = FlowRunner(controller=controller, context=context)
    circuit_breaker = RiskCircuitBreaker(
        max_consecutive_risk=config.risk_control.max_consecutive_risk,
        max_failure_streak=config.risk_control.max_failure_streak,
    )

    try:
        with ThreadPoolExecutor(max_workers=config.concurrent_flows) as executor:
            future_map = {}

            while len(future_map) < config.concurrent_flows and not circuit_breaker.should_stop():
                tasks = db.get_pending_tasks(limit=1)
                if not tasks:
                    break
                task = tasks[0]
                future = executor.submit(process_single_task, controller, task[0], task[1], task[2], task[3], db, runner)
                future_map[future] = task

            while future_map:
                done_futures, _ = wait(future_map.keys(), return_when=FIRST_COMPLETED)
                for future in done_futures:
                    task_id, email, password, retry_mode = future_map.pop(future)
                    try:
                        result = future.result()
                    except Exception as exc:
                        logger.exception("Task %s failed: %s", task_id, exc)
                        result = FlowResult.fail(ErrorCode.UNKNOWN_ERROR, str(exc), Stage.INIT)
                        db.update_task_status(task_id, "failed", str(exc), error_code=result.error_code, stage=result.stage)

                    circuit_breaker.record_result(result)
                    if circuit_breaker.should_stop():
                        logger.warning("Risk circuit breaker triggered: %s", circuit_breaker.stop_reason())
                        break

                    next_tasks = db.get_pending_tasks(limit=1)
                    if next_tasks and not circuit_breaker.should_stop():
                        next_task = next_tasks[0]
                        next_future = executor.submit(
                            process_single_task,
                            controller,
                            next_task[0],
                            next_task[1],
                            next_task[2],
                            next_task[3],
                            db,
                            runner,
                        )
                        future_map[next_future] = next_task

                logger.info("Progress stats: %s", db.get_stats())
                if circuit_breaker.should_stop():
                    break
    finally:
        controller.clean_up(type="all_browser")
        if circuit_breaker.should_stop():
            logger.warning("Execution stopped by risk circuit breaker: %s", circuit_breaker.stop_reason())
        logger.info("OutlookRegister register-only mode finished. Final stats: %s", db.get_stats())



def run_cli_oauth() -> None:
    config = AppConfig.load()
    config.validate()
    ensure_runtime_dirs()
    accounts = load_email_accounts(PENDING_OAUTH_ACCOUNTS_PATH)
    if not accounts:
        logger.warning("No email accounts found in %s", PENDING_OAUTH_ACCOUNTS_PATH)
        return

    logger.info("Starting OAuth-only mode for %s accounts", len(accounts))
    results = run_oauth_accounts(accounts)
    success_accounts = [item.token_account for item in results if item.success and item.token_account is not None]
    export_token_accounts(OAUTH_TOKEN_ACCOUNTS_PATH, success_accounts)

    success_count = len(success_accounts)
    failed_count = len(results) - success_count
    logger.info("OAuth-only mode finished. success=%s failed=%s", success_count, failed_count)
    for item in results:
        if not item.success:
            logger.warning("OAuth failed for %s: %s", item.email, item.error_message)

    if success_accounts and config.microsoft_account_manager.enabled and config.microsoft_account_manager.upload_after_oauth:
        client = build_microsoft_account_manager_client(config)
        upload_result = client.upload_token_accounts(success_accounts)
        if upload_result.ok:
            logger.info("Uploaded token accounts to microsoft-account-manager: %s", upload_result.message)
        else:
            logger.warning("Failed to upload token accounts: %s", upload_result.message)



def run_cli() -> None:
    run_cli_register()


if __name__ == "__main__":
    run_cli()
