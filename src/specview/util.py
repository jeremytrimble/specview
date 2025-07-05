
import datetime
import logging
import time
from contextlib import contextmanager

from PyQt5.QtWidgets import QWidget

log = logging.getLogger("util")

@contextmanager
def measure_runtime(action:str|None, log_level:int|str=logging.INFO):
    tick = time.monotonic()
    yield
    tock = time.monotonic()

    if action is None:
        action = "something"

    delta = datetime.timedelta(seconds=tock-tick)
    log.log(log_level, f"{action} took {delta}")

@contextmanager
def signals_blocked(widget:QWidget):
    orig = widget.signalsBlocked()
    try:
        widget.blockSignals(True)
        yield
    finally:
        widget.blockSignals(orig)
