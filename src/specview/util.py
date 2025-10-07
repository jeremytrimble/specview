
import datetime
import logging
import time
from contextlib import contextmanager
#import typing
#from functools import partial
import typing

from PyQt5.QtWidgets import QWidget

import pyqtgraph as pg
import functools
import numpy as np

log = logging.getLogger("util")

def unit_value_to_prefixed_units(unity_value: float, unit_base:str) -> tuple[float, str]:
    if unity_value >= 1e12:
        prefix = "T"
        value = unity_value / 1e12
    elif unity_value >= 1e9:
        prefix = "G"
        value = unity_value / 1e9
    elif unity_value >= 1e6:
        prefix = "M"
        value = unity_value / 1e6
    elif unity_value >= 1e3:
        prefix = "k"
        value = unity_value / 1e3
    elif unity_value >= 1:
        prefix = ""
        value = unity_value
    elif unity_value >= 1e-3:
        prefix = "m"
        value = unity_value * 1e3
    elif unity_value >= 1e-6:
        prefix = "μ"
        value = unity_value * 1e6
    elif unity_value >= 1e-9:
        prefix = "n"
        value = unity_value * 1e9
    elif unity_value >= 1e-12:
        prefix = "p"
        value = unity_value * 1e12
    elif unity_value >= 1e-15:
        prefix = "f"
        value = unity_value * 1e15  # femto
    else:
        return 0.0, unit_base  # If the value is too small, return 0 with the base unit
    return value, prefix + unit_base

def freq_format_with_units(frequency: float) -> tuple[float, str]:
    """
    Format a frequency in Hz into a human-readable string with appropriate SI prefix.
    """
    if np.isnan(frequency):
        return float('nan'), "Hz"
    elif np.isposinf(frequency):
        return float('inf'), "Hz"
    elif np.isneginf(frequency):
        return float('-inf'), "Hz"

    value, unit_str = unit_value_to_prefixed_units(frequency, "Hz")
    return value, unit_str

def freq_format(frequency: float) -> str:
    val, units = freq_format_with_units(frequency)
    return f"{val:.3f} {units}" if val != 0.0 else "0.00 Hz"

def duration_format(seconds: float) -> str:
    """
    Format a duration in seconds into a human-readable string.
    """

    if np.isnan(seconds):
        return "NaN"
    elif np.isposinf(seconds):
        return "∞"
    elif np.isneginf(seconds):
        return "-∞"

    if seconds < 1.0:
        val, unit_str = unit_value_to_prefixed_units(seconds, "s")
        if val == 0.0:
            return "0.0s"
        return f"{val:.1f} {unit_str}"

    prefix = ""
    if seconds < 0:
        prefix = "-"
        seconds = -seconds 
    
    minutes = int(seconds // 60)
    hours =   int(minutes // 60)
    seconds = seconds % 60
    
    out = prefix
    if hours > 0:
        out+=f"{hours:d}h"
    if minutes > 0:
        out+=f"{minutes:02d}m"
    out+=f"{seconds:06.3f}s"
    return out



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

def region_from_rectroi(roi: pg.RectROI) -> tuple[float, float]:
    pos = roi.pos()
    size = roi.size()  # This returns a Point, not a tuple
    # To get the rectangle as (left, top, right, bottom):
    left = pos.x()
    top = pos.y()
    right = left + size.x()
    bottom = top + size.y()
    return (left, top, right, bottom)

#def invoke_with_signals_blocked(widget:QWidget, cb:typing.Callable, *args, **kwargs):
#    with signals_blocked(widget):
#        cb(*args, **kwargs)

Ktype = typing.TypeVar("Ktype")
Vtype = typing.TypeVar("Vtype")
def first_from_dict(d:dict[Ktype,Vtype], return_none_on_empty:bool=True) -> Vtype|None:
    if not d and return_none_on_empty:
        return None
    key0 = list(d.keys())[0]
    return d[key0]