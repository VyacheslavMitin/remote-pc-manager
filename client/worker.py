"""Фоновый worker на QThread: выполняет callable вне GUI-потока.

Сигналы (доставляются в поток Qt, т.е. нужно работающее event loop):
    ok(object)  — результат вызова
    fail(str)   — текст ошибки (str(исключение))

Важно: аргументы вызываемой функции передаются Позиционно после fn,
а владелец (parent) — только как ключевое: Worker(fn, arg1, arg2, parent=win).
"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class Worker(QThread):
    ok = Signal(object)
    fail = Signal(str)

    def __init__(self, fn, /, *args, parent=None, **kwargs):
        super().__init__(parent)
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self) -> None:  # выполняется в отдельном потоке
        try:
            result = self._fn(*self._args, **self._kwargs)
        except Exception as exc:  # noqa: BLE001 — показываем любую ошибку в GUI
            self.fail.emit(f"{exc.__class__.__name__}: {exc}" if str(exc) else exc.__class__.__name__)
        else:
            self.ok.emit(result)
