from PyQt5.QtCore import QSize, Qt, QThread, pyqtSignal, QObject, QTimer
from PyQt5.QtWidgets import QApplication, QMainWindow, QGridLayout, QWidget, QSlider, QLabel, QHBoxLayout, QVBoxLayout, QPushButton, QComboBox  # tested with PyQt6==6.7.0

from contextlib import contextmanager
import typing

#import enum
#class FreqSelectionType(enum.IntEnum):
#    SINGLE_FREQUENCY = 1
#    FREQUENCY_INTERVAL = 2

class GatedSignal:
    def __init__(self, sig: pyqtSignal):
        self._update_in_progress = False
        self._signal = sig

    def emit(self, *args, **kwargs):
        if self._update_in_progress:
            return
        else:
            self._update_in_progress = True
            self._signal.emit(*args, **kwargs)
            self._update_in_progress = False

    def connect(self, *args, **kwargs):
        self._signal.connect(*args, **kwargs)

class SignalGate:
    def __init__(self):
        self._update_in_progress = False

    @property
    def in_progress(self) -> bool:
        return self._update_in_progress

    @contextmanager
    def updating(self):
        self._update_in_progress = True
        try:
            yield
        finally:
            self._update_in_progress = False


class AppState(QObject):
    #_instance = None

    cursor_frequency_changed = pyqtSignal(float, name="cursor_frequency_changed")
    cursor_time_changed      = pyqtSignal(float, name="cursor_time_changed")

    frequency_interval_changed = pyqtSignal( [object], name="frequency_interval_changed") # tuple[float,float]|None
    time_interval_changed      = pyqtSignal( [object], name="time_interval_changed")    # tuple[float,float]|None

    def __init__(self, parent = ...):
        super().__init__(parent)

        # Items of state:
        # - set of opened sigmf files

        # - selected sigmf file
        # - selected capture
        # - selected annotation
        # - selected channel, or channel math

        # - plot range selections/focus times
        # - 

        # TODO: add getters for these
        self._cursor_frequency: float = 0.0
        self._cursor_time: float = 0.0

        self._time_interval: tuple[float,float]|None = None
        self._frequency_interval: tuple[float,float]|None = None

        # UIP: update in progress
        self._cursor_frequency_gate = SignalGate()
        self._cursor_time_gate = SignalGate()
        self._time_interval_gate = SignalGate()
        self._frequency_interval_gate = SignalGate()

    def set_time_interval(self, time_interval:tuple[float,float]|None ):
        if self._time_interval_gate.in_progress:
            return
        else:
            self._time_interval = time_interval
            with self._time_interval_gate.updating():
                self.time_interval_changed.emit(self._time_interval)

    def set_frequency_interval(self, frequency_interval:tuple[float,float]|None ):
        if self._frequency_interval_gate.in_progress:
            return
        else:
            self._frequency_interval = frequency_interval
            with self._frequency_interval_gate.updating():
                self.frequency_interval_changed.emit(self._frequency_interval)


    def set_cursor_frequency(self, f_Hz:float):
        if self._cursor_frequency_gate.in_progress:
            return
        else:
            self._cursor_frequency = f_Hz
            with self._cursor_frequency_gate.updating():
                self.cursor_frequency_changed.emit( self._cursor_frequency )

    def set_cursor_time(self, t_sec:float):
        if self._cursor_time_gate.in_progress:
            return
        else:
            self._cursor_time = t_sec
            with self._cursor_time_gate.updating():
                self.cursor_time_changed.emit( self._cursor_time )

