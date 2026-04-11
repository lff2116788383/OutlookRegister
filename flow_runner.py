from __future__ import annotations

import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable, Tuple

from execution_models import ErrorCode, FlowResult, RiskCircuitBreaker, Stage
from get_token import get_access_token
from logger import logger
from runtime import RuntimeContext, SupportsCleanUp
from utils import build_email_address, generate_strong_password, random_email


class FlowRunner:
    def __init__(self, controller: SupportsCleanUp, context: RuntimeContext):
        self.controller = controller
        self.context = context

    def _log_event(
        self,
        *,
        task_id: int,
        email: str,
        stage: str,
        status: str,
        message: str,
        error_code: str = "",
    ) -> None:
        email_address = build_email_address(email, self.context.config.email_domain)
        self.context.result_store.save_task_event(
            {
                "task_id": task_id,
                "email": email_address,
                "stage": stage,
                "status": status,
                "message": message,
                "error_code": error_code,
                "timestamp": time.time(),
            }
        )

    def _save_final_result(self, task_id: int, email: str, result: FlowResult, started_at: float, traffic_stats: dict | None = None) -> None:
        email_address = build_email_address(email, self.context.config.email_domain)
        traffic_stats = traffic_stats or {}
        self.context.result_store.save_task_result(
            {
                "task_id": task_id,
                "email": email_address,
                "success": result.success,
                "stage": result.stage,
                "error_code": result.error_code,
                "error_message": result.error_message,
                "risk_detected": result.risk_detected,
                "duration_ms": int((time.time() - started_at) * 1000),
                "request_count": int(traffic_stats.get("request_count", 0) or 0),
                "response_count": int(traffic_stats.get("response_count", 0) or 0),
                "blocked_count": int(traffic_stats.get("blocked_count", 0) or 0),
                "request_bytes": int(traffic_stats.get("request_bytes", 0) or 0),
                "response_bytes": int(traffic_stats.get("response_bytes", 0) or 0),
            }
        )

    def process_single_flow(self) -> FlowResult:
        return self.process_single_flow_with_credentials(
            task_id=0,
            email=random_email(),
            password=generate_strong_password(),
        )

    def process_single_flow_with_credentials(self, task_id: int, email: str, password: str, retry_mode: str = "full") -> FlowResult:
        page = None
        traffic_stats = None
        started_at = time.time()
        max_duration_seconds = self.context.config.risk_control.max_task_duration_seconds
        effective_email = email
        self._log_event(task_id=task_id, email=email, stage=Stage.INIT.value, status="started", message=f"任务开始（模式: {retry_mode}）")
        try:
            page = self.controller.get_thread_page()
            traffic_stats = getattr(page, "_traffic_stats", None) if page is not None else None
            if page is None:
                result = FlowResult.fail(
                    ErrorCode.BROWSER_LAUNCH_FAILED,
                    "Browser page creation failed",
                    Stage.BROWSER,
                )
                self._log_event(
                    task_id=task_id,
                    email=email,
                    stage=result.stage,
                    status="failed",
                    message=result.error_message,
                    error_code=result.error_code,
                )
                self._save_final_result(task_id, email, result, started_at, traffic_stats)
                return result

            if retry_mode == "oauth_only":
                final_email = email
                final_email_address = build_email_address(final_email, self.context.config.email_domain)
                logger.info("Retrying OAuth only for %s", final_email_address)
            else:
                result = self.controller.outlook_register(page, email, password)
                if not result.success:
                    self._log_event(
                        task_id=task_id,
                        email=email,
                        stage=result.stage,
                        status="failed",
                        message=result.error_message,
                        error_code=result.error_code,
                    )
                    self._save_final_result(task_id, email, result, started_at, traffic_stats)
                    return result

                if time.time() - started_at > max_duration_seconds:
                    result = FlowResult.fail(
                        ErrorCode.TASK_TIMEOUT,
                        f"Task exceeded duration budget: {max_duration_seconds}s",
                        Stage.POST_REGISTER,
                    )
                    self._log_event(
                        task_id=task_id,
                        email=email,
                        stage=result.stage,
                        status="failed",
                        message=result.error_message,
                        error_code=result.error_code,
                    )
                    self._save_final_result(task_id, email, result, started_at, traffic_stats)
                    return result

                final_email = str(result.metadata.get("final_email", email) or email)
                final_email_address = str(
                    result.metadata.get("email_address")
                    or build_email_address(final_email, self.context.config.email_domain)
                )
                effective_email = final_email
                self.context.result_store.save_registered_email(
                    email=final_email,
                    password=password,
                    oauth_enabled=self.controller.enable_oauth2,
                    domain=self.context.config.email_domain,
                )
                logger.info("Email registration succeeded for %s", final_email_address)
                self._log_event(
                    task_id=task_id,
                    email=final_email,
                    stage=Stage.POST_REGISTER.value,
                    status="success",
                    message=f"邮箱注册成功: {final_email_address}",
                )

                if not self.controller.enable_oauth2:
                    final_result = FlowResult.ok(stage=Stage.POST_REGISTER.value)
                    self._save_final_result(task_id, final_email, final_result, started_at, traffic_stats)
                    return final_result

            token_result = get_access_token(page, final_email, self.context.config)
            if not token_result[0]:
                result = FlowResult.fail(
                    ErrorCode.OAUTH_FAILED,
                    "OAuth token acquisition failed",
                    Stage.OAUTH,
                )
                self._log_event(
                    task_id=task_id,
                    email=final_email,
                    stage=result.stage,
                    status="failed",
                    message=result.error_message,
                    error_code=result.error_code,
                )
                self._save_final_result(task_id, final_email, result, started_at, traffic_stats)
                return result

            refresh_token, access_token, expire_at = token_result
            self.context.result_store.save_token_result(
                email=final_email,
                password=password,
                client_id=self.context.config.oauth2.client_id,
                refresh_token=refresh_token,
                access_token=access_token,
                expire_at=expire_at,
                domain=self.context.config.email_domain,
            )
            logger.info(
                "OAuth token acquisition succeeded for %s",
                final_email_address,
            )
            self._log_event(
                task_id=task_id,
                email=final_email,
                stage=Stage.OAUTH.value,
                status="success",
                message=f"OAuth token 获取成功: {final_email_address}",
            )
            final_result = FlowResult.ok(
                stage=Stage.OAUTH.value,
                metadata={
                    "final_email": final_email,
                    "email_address": final_email_address,
                },
            )
            self._save_final_result(task_id, final_email, final_result, started_at, traffic_stats)
            return final_result
        except Exception as exc:
            logger.exception(
                "Single flow failed for %s: %s",
                build_email_address(effective_email, self.context.config.email_domain),
                exc,
            )
            result = FlowResult.fail(
                ErrorCode.UNKNOWN_ERROR,
                str(exc),
                Stage.INIT,
            )
            self._log_event(
                task_id=task_id,
                email=effective_email,
                stage=result.stage,
                status="failed",
                message=result.error_message,
                error_code=result.error_code,
            )
            self._save_final_result(task_id, effective_email, result, started_at, traffic_stats)
            return result
        finally:
            self.controller.clean_up(page, "done_browser")

    def run_concurrent_flows(
        self,
        concurrent_flows: int,
        max_tasks: int,
        should_stop: Callable[[], bool] | None = None,
        circuit_breaker: RiskCircuitBreaker | None = None,
    ) -> Tuple[int, int]:
        task_counter = 0
        succeeded_tasks = 0
        failed_tasks = 0

        with ThreadPoolExecutor(max_workers=concurrent_flows) as executor:
            running_futures: set[Future] = set()

            while task_counter < max_tasks or running_futures:
                if should_stop and should_stop():
                    break
                if circuit_breaker and circuit_breaker.should_stop():
                    break

                done_futures = {future for future in running_futures if future.done()}
                for future in done_futures:
                    try:
                        result = future.result()
                        if result.success:
                            succeeded_tasks += 1
                        else:
                            failed_tasks += 1
                        if circuit_breaker:
                            circuit_breaker.record_result(result)
                    except Exception as exc:
                        failed_tasks += 1
                        logger.exception("Concurrent future failed: %s", exc)
                    running_futures.remove(future)

                while len(running_futures) < concurrent_flows and task_counter < max_tasks:
                    if should_stop and should_stop():
                        break
                    if circuit_breaker and circuit_breaker.should_stop():
                        break
                    new_future = executor.submit(self.process_single_flow)
                    running_futures.add(new_future)
                    task_counter += 1
                    interval = max(1, max_tasks // 2)
                    if task_counter % interval == 0:
                        logger.info("已提交 %s/%s 任务", task_counter, max_tasks)

                time.sleep(0.5)

        return succeeded_tasks, failed_tasks
