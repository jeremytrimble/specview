from PyQt5.QtCore import QSize, Qt, QThread, pyqtSignal, QObject, QTimer
from PyQt5.QtWidgets import QApplication, QMainWindow, QGridLayout, QWidget, QSlider, QLabel, QHBoxLayout, QVBoxLayout, QPushButton, QComboBox  # tested with PyQt6==6.7.0

#import enum
#class FreqSelectionType(enum.IntEnum):
#    SINGLE_FREQUENCY = 1
#    FREQUENCY_INTERVAL = 2


class AppState(QObject):
    #_instance = None

    cursor_frequency_changed = pyqtSignal(float, name="cursor_frequency_changed")
    cursor_time_changed      = pyqtSignal(float, name="cursor_time_changed")

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

        self._cursor_frequency: float = 0.0
        self._cursor_time: float = 0.0

    def set_cursor_frequency(self, f_Hz:float):
        self._cursor_frequency = f_Hz
        self.cursor_frequency_changed.emit( self._cursor_frequency )

    def set_cursor_time(self, t_sec:float):
        self._cursor_time = t_sec
        self.cursor_time_changed.emit( self._cursor_time )

    #@classmethod
    #def instance(cls):
    #    if cls._instance is None:
    #        cls._instance = AppState()
    #    return cls._instance
            


