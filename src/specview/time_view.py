from PyQt5.QtWidgets import QApplication, QMainWindow, QGridLayout, QWidget, QSlider, QLabel, QHBoxLayout, QVBoxLayout, QPushButton, QComboBox  # tested with PyQt6==6.7.0
import pyqtgraph as pg

from .spec_types import TimeSeries
from .app_state import AppState

from .interval_select_viewbox import IntervalSelectViewBox

from .ui_constants import INTERVAL_ROI_COLOR

class TimeView(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        myvb = IntervalSelectViewBox()

        self._time_plot = pg.PlotWidget(labels={'left': 'Amplitude', 'bottom': 'Time [microseconds]'}, viewBox=myvb)
        self._time_plot.setMouseEnabled(x=True, y=True)
        self._time_plot.setYRange(-1.1, 1.1)
        self._time_plot_curve_i = self._time_plot.plot([]) 
        self._time_plot_curve_q = self._time_plot.plot([]) 

        self._time_crosshair_x = pg.InfiniteLine(angle=90, movable=False)
        self._time_plot.addItem(self._time_crosshair_x, ignoreBounds=True)

        layout = QHBoxLayout()

        layout.addWidget(self._time_plot)
        self.setLayout(layout)

        roiPen = pg.mkPen( pg.mkColor(INTERVAL_ROI_COLOR), width=3)
        self._interval_roi = pg.LinearRegionItem( values=(0,1), orientation="vertical", pen=roiPen)
        self._interval_roi.setVisible(False)
        self._time_plot.addItem(self._interval_roi, ignoreBounds=True)

        myvb.set_plot_and_interval(self._time_plot, self._interval_roi)

        self._connect_app_signals()

    def _get_app_state(self) -> AppState:
        return QApplication.instance().app_state

    def _connect_app_signals(self):
        app_state = self._get_app_state()

        # TODO: NEXT: START_HERE: Uncommenting this line makes everything crazy-slow -- why?
        #app_state.selected_times_changed.connect(self._on_time_cursor_changed)

    def _on_time_cursor_changed(self, t_sec:float):
        self._time_crosshair_x.setPos(t_sec)


    def _redisplay(self):

        # TODO: pick out the right channel
        chan = 0

        self._time_plot_curve_i.setData(self._time_series.data[chan,:].real)
        self._time_plot_curve_q.setData(self._time_series.data[chan,:].imag)


    def setDisplayedTimeSeries(self, tser: TimeSeries):
        self._time_series = tser
        self._redisplay()

        # TODO: emit event saying data has changed, zoom to right portion of data

