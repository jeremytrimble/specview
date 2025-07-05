from PyQt5.QtWidgets import QApplication, QMainWindow, QGridLayout, QWidget, QSlider, QLabel, QHBoxLayout, QVBoxLayout, QPushButton, QComboBox  # tested with PyQt6==6.7.0
import pyqtgraph as pg

from .spec_types import TimeSeries

class TimeView(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._time_plot = pg.PlotWidget(labels={'left': 'Amplitude', 'bottom': 'Time [microseconds]'})
        self._time_plot.setMouseEnabled(x=True, y=True)
        self._time_plot.setYRange(-1.1, 1.1)
        self._time_plot_curve_i = self._time_plot.plot([]) 
        self._time_plot_curve_q = self._time_plot.plot([]) 

        layout = QHBoxLayout()

        layout.addWidget(self._time_plot)
        self.setLayout(layout)

    def _redisplay(self):

        # TODO: pick out the right channel
        chan = 0

        self._time_plot_curve_i.setData(self._time_series.data[chan,:].real)
        self._time_plot_curve_q.setData(self._time_series.data[chan,:].imag)


    def setDisplayedTimeSeries(self, tser: TimeSeries):
        self._time_series = tser
        self._redisplay()

        # TODO: emit event saying data has changed, zoom to right portion of data

