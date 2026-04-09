from __future__ import annotations

import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Tuple

from get_token import get_access_token
from logger import logger
from runtime import RuntimeContext, SupportsCleanUp
from utils import generate_strong_password, random_email


class FlowRunner:
    def __init__(self, controller: SupportsCleanUp, context: RuntimeContext):
        self.controller = controller
        self.context = context

    def process_single_flow(self) -> bool:
        return self.process_single_flow_with_credentials(
            email=random_email(),
            password=generate_strong_password(),
        )

    def process_single_flow_with_credentials(self, email: str, password: str) -> bool:
        page = None
        try:
            page = self.controller.get_thread_page()
            if page is None:
                logger.error("Browser page creation failed")
                return False

            result = self.controller.outlook_register(page, email, password)
            if not result:
                return False

            self.context.result_store.save_registered_email(
                email=email,
                password=password,
                oauth_enabled=self.controller.enable_oauth2,
            )
            logger.info("Email registration succeeded for %s@outlook.com", email)

            if not self.controller.enable_oauth2:
                return True

            token_result = get_access_token(page, email, self.context.config)
            if not token_result[0]:
                logger.error("OAuth token acquisition failed for %s@outlook.com", email)
                return False

            refresh_token, access_token, expire_at = token_result
            self.context.result_store.save_token_result(
                email=email,
                password=password,
                refresh_token=refresh_token,
                access_token=access_token,
                expire_at=expire_at,
            )
            logger.info("OAuth token acquisition succeeded for %s@outlook.com", email)
            return True
        except Exception as exc:
            logger.exception("Single flow failed for %s@outlook.com: %s", email, exc)
            return False
        finally:
            self.controller.clean_up(page, "done_browser")

    def run_concurrent_flows(self, concurrent_flows: int, max_tasks: int) -> Tuple[int, int]:
        task_counter = 0
        succeeded_tasks = 0
        failed_tasks = 0

        with ThreadPoolExecutor(max_workers=concurrent_flows) as executor:
            running_futures: set[Future] = set()

            while task_counter < max_tasks or running_futures:
                done_futures = {future for future in running_futures if future.done()}
                for future in done_futures:
                    try:
                        if future.result():
                            succeeded_tasks += 1
                        else:
                            failed_tasks += 1
                    except Exception as exc:
                        failed_tasks += 1
                        logger.exception("Concurrent future failed: %s", exc)
                    running_futures.remove(future)

                while len(running_futures) < concurrent_flows and task_counter < max_tasks:
                    new_future = executor.submit(self.process_single_flow)
                    running_futures.add(new_future)
                    task_counter += 1
                    interval = max(1, max_tasks // 2)
                    if task_counter % interval == 0:
                        logger.info("已提交 %s/%s 任务", task_counter, max_tasks)

                time.sleep(0.5)

        return succeeded_tasks, failed_tasks
