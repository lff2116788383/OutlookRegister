from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from app_config import AppConfig, ensure_runtime_dirs
from controller_factory import build_controller
from database import TaskDB
from logger import logger
from utils import generate_strong_password, random_email


def process_single_task(controller, task_id: int, email: str, password: str, db: TaskDB) -> bool:
    page = None
    try:
        db.update_task_status(task_id, "in_progress")
        page = controller.get_thread_page()
        result = controller.outlook_register(page, email, password)

        if result:
            db.update_task_status(task_id, "success")
            return True

        db.update_task_status(task_id, "failed", "Registration flow returned False")
        return False
    except Exception as exc:
        logger.exception("Task %s failed: %s", task_id, exc)
        db.update_task_status(task_id, "failed", str(exc))
        return False
    finally:
        controller.clean_up(page, "done_browser")


def initialize_tasks(db: TaskDB, config: AppConfig) -> None:
    stats = db.get_stats()
    total_existing = sum(stats.values())
    if total_existing >= config.max_tasks:
        return

    missing = config.max_tasks - total_existing
    logger.info("Initializing %s new tasks in database", missing)
    for _ in range(missing):
        db.create_task(random_email(), generate_strong_password())


def run_cli() -> None:
    config = AppConfig.load()
    ensure_runtime_dirs()
    db = TaskDB()

    logger.info("Starting OutlookRegister production mode")
    initialize_tasks(db, config)
    db.reset_in_progress_tasks()
    controller = build_controller(config)

    try:
        with ThreadPoolExecutor(max_workers=config.concurrent_flows) as executor:
            while True:
                tasks = db.get_pending_tasks(limit=config.concurrent_flows)
                if not tasks:
                    break

                futures = [
                    executor.submit(process_single_task, controller, task_id, email, password, db)
                    for task_id, email, password in tasks
                ]
                for future in futures:
                    future.result()

                logger.info("Progress stats: %s", db.get_stats())
    finally:
        controller.clean_up(type="all_browser")
        logger.info("OutlookRegister finished. Final stats: %s", db.get_stats())


if __name__ == "__main__":
    run_cli()
