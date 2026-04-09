from __future__ import annotations

import io
import traceback
from contextlib import redirect_stderr, redirect_stdout
from typing import Callable

from PySide6.QtCore import QObject, QThread, Signal


class GuiLogEmitter(io.TextIOBase):
    def __init__(self, callback: Callable[[str], None]):
        super().__init__()
        self.callback = callback

    def write(self, text: str) -> int:
        if text:
            self.callback(text)
        return len(text)

    def flush(self) -> None:
        return None


class TaskWorker(QObject):
    log_message = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, task_callable: Callable[[], None]):
        super().__init__()
        self.task_callable = task_callable
        self.is_cancelled = False

    def run(self) -> None:
        logger = GuiLogEmitter(self.log_message.emit)
        try:
            with redirect_stdout(logger), redirect_stderr(logger):
                self.task_callable(lambda: self.is_cancelled)
            if self.is_cancelled:
                self.finished.emit(False, "任务已被手动停止")
            else:
                self.finished.emit(True, "任务执行完成")
        except Exception:
            self.log_message.emit(traceback.format_exc())
            self.finished.emit(False, "任务执行失败")
            
    def stop(self) -> None:
        self.is_cancelled = True

class TaskThreadController(QObject):
    log_message = Signal(str)
    task_finished = Signal(bool, str)

    def __init__(self, task_callable: Callable[[], None]):
        super().__init__()
        self.thread = QThread()
        self.worker = TaskWorker(task_callable)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.log_message.connect(self.log_message.emit)
        self.worker.finished.connect(self._handle_finished)
        self.worker.finished.connect(self.thread.quit)
        self.thread.finished.connect(self.thread.deleteLater)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.worker.stop()

    def _handle_finished(self, success: bool, message: str) -> None:
        self.task_finished.emit(success, message)
        self.worker.deleteLater()
