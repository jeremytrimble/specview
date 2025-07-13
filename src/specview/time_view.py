from PyQt5.QtWidgets import QApplication, QMainWindow, QGridLayout, QWidget, QSlider, QLabel, QHBoxLayout, QVBoxLayout, QPushButton, QComboBox  # tested with PyQt6==6.7.0
import pyqtgraph as pg

from .spec_types import TimeSeries
from .app_state import AppState

from .roi_select_viewboxes import IntervalSelectViewBox
from .util import signals_blocked

from .ui_constants import INTERVAL_ROI_COLOR

class TimeView(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        myvb = IntervalSelectViewBox()

        self._time_plot = pg.PlotWidget(labels={'left': 'Amplitude', 'bottom': 'Time [microseconds]'}, viewBox=myvb)
        self._time_plot.setMouseEnabled(x=True, y=True)
        self._time_plot.setYRange(-1.1, 1.1)
        # TODO: check if downsampling is really helping
        self._time_plot_curve_i = self._time_plot.plot([], downsample=True, name="real", pen=pg.mkPen('b')) 
        self._time_plot_curve_q = self._time_plot.plot([], downsample=True, name="imaginary", pen=pg.mkPen('r')) 

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
        myvb.set_interval_change_callback( self._time_interval_set )

        # make sure the interval ROI is updated when the user drags it (in addition to during initial creation with shift-drag)
        self._interval_roi.sigRegionChanged.connect( lambda: self._time_interval_set(self._interval_roi.getRegion()) )

        self._connect_app_signals()

    def _get_app_state(self) -> AppState:
        return QApplication.instance().app_state

    def _time_interval_set(self, interval: tuple[float,float]|None):
        with signals_blocked(self):
            self._get_app_state().set_time_interval(interval)

    def _connect_app_signals(self):
        app_state = self._get_app_state()

        # TODO: NEXT: START_HERE: Uncommenting this line makes everything crazy-slow -- why?
        #app_state.cursor_time_changed.connect(self._on_time_cursor_changed)

    def _on_time_cursor_changed(self, t_sec:float):
        self._time_crosshair_x.setPos(t_sec)


    def _redisplay(self):

        # TODO: pick out the right channel
        chan = 0

        time_lo_sec = self._time_series.time_sec[0]
        time_hi_sec = self._time_series.time_sec[-1]

        self._time_plot.setXRange(time_lo_sec, time_hi_sec)

        self._time_plot_curve_i.setData(
            x = self._time_series.time_sec,
            y = self._time_series.data[chan,:].real,
        )
        self._time_plot_curve_q.setData(
            x = self._time_series.time_sec,
            y = self._time_series.data[chan,:].imag,
        )


    def setDisplayedTimeSeries(self, tser: TimeSeries):
        self._time_series = tser
        self._redisplay()

        # TODO: emit event saying data has changed, zoom to right portion of data

