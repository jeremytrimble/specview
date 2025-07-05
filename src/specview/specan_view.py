from PyQt5.QtWidgets import QApplication, QMainWindow, QGridLayout, QWidget, QSlider, QLabel, QHBoxLayout, QVBoxLayout, QPushButton, QComboBox  # tested with PyQt6==6.7.0
import pyqtgraph as pg

from .spec_types import Spectrogram

class SpecanView(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._sgram : Spectrogram|None = None

        # TODO: make MHz ticks display more nicely
        self._freq_plot = pg.PlotWidget(labels={'left': 'PSD', 'bottom': 'Frequency [MHz]'})
        self._freq_plot.setMouseEnabled(x=True, y=True)
        self._freq_plot_curve = self._freq_plot.plot([]) 

        layout = QHBoxLayout()
        layout.addWidget(self._freq_plot)

        self.setLayout(layout)


    def _redisplay(self):

        if self._sgram is None:
            return

        # TODO pull channel, time segment, etc
        chan = 0
        time_idx = 0

        f_Hz = self._sgram.freq_Hz
        f_lo_Hz = f_Hz[0]
        f_hi_Hz = f_Hz[-1]

        trace = self._sgram.data[chan,time_idx,:]

        self._freq_plot_curve.setData(
            x = f_Hz,
            y = self._sgram.data[chan,time_idx,:]
        )
        self._freq_plot.setXRange( f_lo_Hz, f_hi_Hz )

        trace_lo = round(trace.min(), -1)
        trace_hi = round(trace.max(), -1)
        self._freq_plot.setYRange( trace_lo, trace_hi )


    def setDisplayedSpectrogramData(self, sgram:Spectrogram):
        self._sgram = sgram
        self._redisplay()