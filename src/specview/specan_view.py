from PyQt5.QtCore import QPointF
from PyQt5.QtWidgets import QApplication, QMainWindow, QGridLayout, QWidget, QSlider, QLabel, QHBoxLayout, QVBoxLayout, QPushButton, QComboBox  # tested with PyQt6==6.7.0
import pyqtgraph as pg

from .spec_types import Spectrogram
from .app_state import AppState

from .util import signals_blocked

from bisect import bisect_left

class SpecanView(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._sgram : Spectrogram|None = None

        # TODO: make MHz ticks display more nicely
        self._freq_plot = pg.PlotWidget(labels={'left': 'PSD', 'bottom': 'Frequency [MHz]'})
        self._freq_plot.setMouseEnabled(x=True, y=True)
        self._freq_plot_curve = self._freq_plot.plot([]) 

        self._freq_crosshair_x = pg.InfiniteLine(angle=90, movable=False)

        self._freq_plot.addItem(self._freq_crosshair_x, ignoreBounds=True)

        layout = QHBoxLayout()
        layout.addWidget(self._freq_plot)

        self._freq_plot.scene().sigMouseMoved.connect(self._on_scene_mouse_moved)

        self.setLayout(layout)

        self._time_idx = 0

        self._connect_app_signals()

    def _get_app_state(self) -> AppState:
        return QApplication.instance().app_state

    def _connect_app_signals(self):
        app_state = self._get_app_state()
        app_state.cursor_frequency_changed.connect(self._on_freq_cursor_changed)
        app_state.cursor_time_changed.connect(self._on_time_cursor_changed)

    def _on_time_cursor_changed(self, t_sec: float):
        # TODO: handle ranges later
        if self._sgram is None:
            return

        # TODO: cache the bisect result
        self._time_idx = bisect_left( self._sgram.time_sec, t_sec )
        self._redisplay()
        

    def _on_freq_cursor_changed(self, freq_Hz: float):
        self._freq_crosshair_x.setPos(freq_Hz)

    def _on_scene_mouse_moved(self, pos: QPointF):
        #print(f"on_scene_mouse_moved: {args=}, {kwargs=}")
        if self._freq_plot.sceneBoundingRect().contains(pos):
            mousePoint = self._freq_plot.getViewBox().mapSceneToView(pos)
            freq_Hz = mousePoint.x()
            magnitude_dB = mousePoint.y()
            self._freq_crosshair_x.setPos( freq_Hz )
            #self.crosshair_y.setPos(mousePoint.y())
            #print(f"Mouse position: x={mousePoint.x()}, y={mousePoint.y()}")

            # TODO: handle frequency interval selection later:
            with signals_blocked(self):
                self._get_app_state().set_cursor_frequency(freq_Hz)

    def _redisplay(self):

        if self._sgram is None:
            return

        # TODO pull channel, time segment, etc
        chan = 0
        time_idx = self._time_idx

        f_Hz = self._sgram.freq_Hz
        f_lo_Hz = f_Hz[0]
        f_hi_Hz = f_Hz[-1]

        trace = self._sgram.data[chan,time_idx,:]

        self._freq_plot_curve.setData(
            x = f_Hz,
            y = trace,
        )
        #self._freq_plot.setAspectLocked(False)

        self._freq_plot.setXRange( f_lo_Hz, f_hi_Hz )

        trace_lo = round(trace.min(), -1)
        trace_hi = round(trace.max(), -1)
        self._freq_plot.setYRange( trace_lo, trace_hi )

        #self._freq_plot.setAspectLocked(True)

    def setDisplayedSpectrogramData(self, sgram:Spectrogram):
        self._sgram = sgram
        self._redisplay()