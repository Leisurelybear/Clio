from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import TextIO

_LOGGER_NAME = "vlog_tool"
_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


class _HourlyFileHandler(logging.Handler):
    """按当前小时自动切文件：logs/YYYY-MM-DD-HH.log。"""

    def __init__(self, logs_dir: Path) -> None:
        super().__init__()
        self._logs_dir = logs_dir
        self._current_hour: str | None = None
        self._current_file: TextIO | None = None
        self.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATEFMT))
        self._rotate(datetime.now())

    def _rotate(self, ts: datetime) -> None:
        hour_key = ts.strftime("%Y-%m-%d-%H")
        if hour_key == self._current_hour:
            return
        if self._current_file is not None:
            try:
                self._current_file.close()
            except Exception:
                pass
        self._logs_dir.mkdir(parents=True, exist_ok=True)
        log_path = self._logs_dir / f"{hour_key}.log"
        self._current_file = open(log_path, "a", encoding="utf-8")
        self._current_hour = hour_key

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._rotate(datetime.fromtimestamp(record.created))
            assert self._current_file is not None
            msg = self.format(record) + "\n"
            self._current_file.write(msg)
            self._current_file.flush()
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        if self._current_file is not None:
            try:
                self._current_file.close()
            except Exception:
                pass
            self._current_file = None
        super().close()


class _TeeWriter:
    """把每一次 write 同时写到原始 stream 和 logger。"""

    def __init__(self, original: TextIO, logger: logging.Logger, level: int) -> None:
        self._original = original
        self._logger = logger
        self._level = level

    def write(self, message: str) -> int:
        if not message:
            return 0
        try:
            written = self._original.write(message)
        except Exception:
            written = 0
        for line in message.splitlines():
            if line:
                self._logger.log(self._level, line)
        try:
            self._original.flush()
        except Exception:
            pass
        return written

    def flush(self) -> None:
        try:
            self._original.flush()
        except Exception:
            pass

    def isatty(self) -> bool:
        return bool(getattr(self._original, "isatty", lambda: False)())

    def __getattr__(self, name: str):
        return getattr(self._original, name)


_initialized = False


def setup_logging(logs_dir: Path, level: int = logging.INFO) -> logging.Logger:
    """初始化日志：把 stdout/stderr 同时写到控制台和 logs/YYYY-MM-DD-HH.log。

    - 跨小时自动切到新文件，无需重启
    - 多次调用是幂等的
    - 文件创建失败时退化为只在控制台输出
    """
    global _initialized
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(level)

    if _initialized:
        return logger

    try:
        logger.addHandler(_HourlyFileHandler(logs_dir))
    except Exception as e:
        sys.stderr.write(f"[vlog_tool] 无法创建日志文件: {e}\n")

    sys.stdout = _TeeWriter(sys.stdout, logger, logging.INFO)
    sys.stderr = _TeeWriter(sys.stderr, logger, logging.WARNING)

    _initialized = True
    return logger
