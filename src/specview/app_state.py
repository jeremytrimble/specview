from PyQt5.QtCore import QSize, Qt, QThread, pyqtSignal, QObject, QTimer
from PyQt5.QtWidgets import QApplication, QMainWindow, QGridLayout, QWidget, QSlider, QLabel, QHBoxLayout, QVBoxLayout, QPushButton, QComboBox  # tested with PyQt6==6.7.0

#import enum
#class FreqSelectionType(enum.IntEnum):
#    SINGLE_FREQUENCY = 1
#    FREQUENCY_INTERVAL = 2


class AppState(QObject):
    #_instance = None

    selected_frequencies_changed = pyqtSignal(float,float, name="selected_frequencies_changed")
    selected_times_changed = pyqtSignal(float,float, name="selected_times_changed")

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

        self._selected_frequencies: tuple[float] = (0.0,0.0)
        self._selected_times: tuple[float] = (0.0,0.0)

    def set_selected_frequencies(self, f_lo_Hz:float, f_hi_Hz:float):
        # TODO: validate?
        self._selected_frequencies = (f_lo_Hz, f_hi_Hz)
        f1,f2 = self._selected_frequencies
        self.selected_frequencies_changed.emit(f1,f2)

    def set_selected_times(self, t_lo_sec:float, t_hi_sec:float):
        # TODO: validate?
        self._selected_times = (t_lo_sec, t_hi_sec)
        t1,t2 = self._selected_times
        self.selected_times_changed.emit(t1,t2)

    #@classmethod
    #def instance(cls):
    #    if cls._instance is None:
    #        cls._instance = AppState()
    #    return cls._instance
            


