from PyQt5.QtCore import QPointF
from PyQt5.QtWidgets import QApplication, QMainWindow, QGridLayout, QWidget, QSlider, QLabel, QHBoxLayout, QVBoxLayout, QPushButton, QComboBox  # tested with PyQt6==6.7.0
import pyqtgraph as pg
import numpy as np

from .spec_types import TimeSeries
from .app_state import AppState

from .roi_select_viewboxes import IntervalSelectViewBox

from .ui_constants import INTERVAL_ROI_COLOR

class TimeView(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        myvb = IntervalSelectViewBox()

        self._time_plot = pg.PlotWidget(labels={'left': 'Amplitude', 'bottom': 'Time [microseconds]'}, viewBox=myvb)
        self._time_plot.setMouseEnabled(x=True, y=True)
        self._time_plot.setYRange(-1.1, 1.1)

        self._time_plot_curve_i = self._time_plot.plot([], name="real", pen=pg.mkPen('b')) 
        self._time_plot_curve_q = self._time_plot.plot([], name="imaginary", pen=pg.mkPen('r')) 

        self._time_plot_curve_i.setDownsampling(auto=True, method='peak')
        self._time_plot_curve_q.setDownsampling(auto=True, method='peak')

        self._time_crosshair_x = pg.InfiniteLine(angle=90, movable=False)
        self._time_plot.addItem(self._time_crosshair_x, ignoreBounds=True)

        self._time_plot.scene().sigMouseMoved.connect(self._on_scene_mouse_moved)

        self._time_interval: tuple[float,float]|None = None

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
        self._get_app_state().set_time_interval(interval)

    def _connect_app_signals(self):
        app_state = self._get_app_state()
        app_state.cursor_time_changed.connect(self._on_time_cursor_changed)
        app_state.time_interval_changed.connect(self._on_time_interval_changed_from_outside)
        app_state.selected_capture_changed.connect(self._on_selected_capture_changed)
        # TODO: process selected channel changes
        #app_state.selected_channel_changed.connect(self._on_selected_channel_changed)

    def _on_selected_capture_changed(self, fileid: str, cap_idx: int):
        app_state = self._get_app_state()
        tser, sgram = app_state.load_capture_data(fileid, cap_idx, channel_idx=0)   # TODO: handle multiple channels
        self.setDisplayedTimeSeries(tser)

    def _on_time_cursor_changed(self, t_sec:float):
        self._time_crosshair_x.setPos(t_sec)

    def _on_time_interval_changed_from_outside(self, time_interval: tuple[float,float]|None):
        self._time_interval = time_interval
        self._interval_roi.setVisible(self._time_interval is not None)
        if self._time_interval is not None:
            self._interval_roi.setRegion(self._time_interval)

        # TODO: try to zoom to the selected time interval?
        #if self._time_interval is not None:
        #    t_lo_sec, t_hi_sec = time_interval
        #    if np.isfinite(t_lo_sec) and np.isfinite(t_hi_sec):
        #        duration_sec = t_hi_sec - t_lo_sec
        #        buffer_sec = duration_sec*0.05
        #        self._time_plot.setXRange(t_lo_sec-buffer_sec, t_hi_sec+buffer_sec)

    def _on_scene_mouse_moved(self, pos: QPointF):
        #print(f"on_scene_mouse_moved: {args=}, {kwargs=}")
        if self._time_plot.sceneBoundingRect().contains(pos):
            mousePoint = self._time_plot.getViewBox().mapSceneToView(pos)
            time_sec = mousePoint.x()
            self._time_crosshair_x.setPos( time_sec )
            self._get_app_state().set_cursor_time(time_sec)

    def _redisplay(self):

        # TODO: pick out the right channel
        chan = 0

        # TODO: do this when new data is initially displayed
        #time_lo_sec = self._time_series.time_sec.min
        #time_hi_sec = self._time_series.time_sec.max
        #self._time_plot.setXRange(time_lo_sec, time_hi_sec)

        self._time_plot_curve_i.setData(
            x = self._time_series.time_sec.array,
            y = self._time_series.data[chan,:].real,
        )
        self._time_plot_curve_q.setData(
            x = self._time_series.time_sec.array,
            y = self._time_series.data[chan,:].imag,
        )


    def setDisplayedTimeSeries(self, tser: TimeSeries):
        self._time_series = tser
        self._redisplay()

        # TODO: emit event saying data has changed, zoom to right portion of data

