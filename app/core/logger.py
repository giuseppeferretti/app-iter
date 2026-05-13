"""
Logger com dois handlers:
  - arquivo (sempre): %APPDATA%/Iter/AppAnac/logs/execucao.log
  - UI callback (opcional): registrado via set_ui_callback(fn).
    fn(nivel: str, msg: str) e chamada a cada log.

Pra usar standalone (sem UI), o callback nao e registrado e o log so vai pra
arquivo + console.
"""
import logging
import os
import sys
from pathlib import Path
from typing import Callable, Optional


def _log_dir() -> Path:
    """Pasta de logs em %APPDATA%/Iter/AppAnac/logs (Windows)."""
    base = Path(os.environ.get("APPDATA", Path.home() / ".iter"))
    p = base / "Iter" / "AppAnac" / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _habilitar_ansi_windows() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        kernel32.SetConsoleMode(handle, 7)
    except Exception:
        pass


_habilitar_ansi_windows()


class ColoredFormatter(logging.Formatter):
    RESET, DIM, CYAN, YELLOW, RED, BG_RED = (
        "\033[0m", "\033[90m", "\033[36m", "\033[33m", "\033[31m", "\033[41;97m",
    )
    LEVEL_COLORS = {
        logging.DEBUG: DIM, logging.INFO: CYAN, logging.WARNING: YELLOW,
        logging.ERROR: RED, logging.CRITICAL: BG_RED,
    }

    def format(self, record: logging.LogRecord) -> str:
        cor = self.LEVEL_COLORS.get(record.levelno, "")
        ts = self.formatTime(record, self.datefmt)
        nivel = f"{cor}{record.levelname}{self.RESET}"
        msg = record.getMessage()
        if record.levelno >= logging.ERROR:
            msg = f"{cor}{msg}{self.RESET}"
        elif record.levelno == logging.WARNING:
            msg = f"{self.YELLOW}{msg}{self.RESET}"
        return f"{self.DIM}{ts}{self.RESET} [{nivel}] {msg}"


class _UICallbackHandler(logging.Handler):
    """Encaminha logs para um callback fornecido pela UI."""

    def __init__(self):
        super().__init__()
        self._callback: Optional[Callable[[str, str], None]] = None

    def set_callback(self, fn: Optional[Callable[[str, str], None]]) -> None:
        self._callback = fn

    def emit(self, record: logging.LogRecord) -> None:
        if self._callback is None:
            return
        try:
            self._callback(record.levelname, record.getMessage())
        except Exception:
            pass


_ui_handler = _UICallbackHandler()


def set_ui_callback(fn: Optional[Callable[[str, str], None]]) -> None:
    """A UI chama isso passando uma funcao fn(level, msg)."""
    _ui_handler.set_callback(fn)


def get_logger(name: str = "app_anac") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    fh = logging.FileHandler(_log_dir() / "execucao.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    ))

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(ColoredFormatter(datefmt="%Y-%m-%d %H:%M:%S"))

    _ui_handler.setLevel(logging.INFO)

    logger.addHandler(fh)
    logger.addHandler(ch)
    logger.addHandler(_ui_handler)
    return logger
