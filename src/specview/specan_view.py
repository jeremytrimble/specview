from PyQt5.QtCore import QPointF
from PyQt5.QtWidgets import QApplication, QWidget, QHBoxLayout
import numpy as np
import pyqtgraph as pg

from .ui_constants import INTERVAL_ROI_COLOR
from .roi_select_viewboxes import IntervalSelectViewBox
from .labeled_linear_region_item import LabeledLinearRegionItem
from .annotation_roi_manager import AnnotationROIManager, ROIDimensions
from .spec_types import Spectrogram
from .app_state import AppState, CaptureID, AnnotationID
from .loaded_file_mgmt import LoadedDictAction

class SpecanView(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._sgram : Spectrogram|None = None

        # TODO: make MHz ticks display more nicely
        myvb = IntervalSelectViewBox()

        self._freq_plot = pg.PlotWidget(labels={'left': 'PSD', 'bottom': 'Frequency [MHz]'}, viewBox=myvb)
        self._freq_plot.setMouseEnabled(x=True, y=True)
        self._freq_plot_curve = self._freq_plot.plot([]) 

        self._freq_crosshair_x = pg.InfiniteLine(angle=90, movable=False)

        self._freq_plot.addItem(self._freq_crosshair_x, ignoreBounds=True)

        layout = QHBoxLayout()
        layout.addWidget(self._freq_plot)

        self._freq_plot.scene().sigMouseMoved.connect(self._on_scene_mouse_moved)
        self.setLayout(layout)

        self._time_idx = 0
        self._time_interval: tuple[float,float]|None = None
        self._freq_interval: tuple[float,float]|None = None

        roiPen = pg.mkPen( pg.mkColor(INTERVAL_ROI_COLOR), width=3)
        self._interval_roi = pg.LinearRegionItem( values=(0,1), orientation="vertical", pen=roiPen)
        self._interval_roi.setVisible(False)
        self._freq_plot.addItem(self._interval_roi, ignoreBounds=True)

        myvb.set_plot_and_interval(self._freq_plot, self._interval_roi)
        myvb.set_interval_change_callback( self._freq_interval_set_from_specan )

        # make sure the interval ROI is updated when the user drags it (in addition to during initial creation with shift-drag)
        self._interval_roi.sigRegionChanged.connect( lambda: self._freq_interval_set_from_specan(self._interval_roi.getRegion()) )

        # Initialize the annotation ROI manager for linear ROIs in frequency domain
        def roi_factory(**kwargs):
            return LabeledLinearRegionItem(orientation="vertical", pen=roiPen, **kwargs)
        
        self._annotation_manager = AnnotationROIManager(
            plot_widget=self._freq_plot,
            roi_dimensions=ROIDimensions.FREQUENCY,
        )

        self._connect_app_signals()

    def _get_app_state(self) -> AppState:
        return QApplication.instance().app_state

    def _connect_app_signals(self):
        app_state = self._get_app_state()
        app_state.cursor_frequency_changed.connect(self._on_freq_cursor_changed)
        app_state.cursor_time_changed.connect(self._on_time_cursor_changed)
        app_state.time_interval_changed.connect(self._on_time_interval_changed_from_outside)
        app_state.frequency_interval_changed.connect(self._on_freq_interval_changed_from_outside)
        app_state.selected_capture_changed.connect(self._on_selected_capture_changed)
        app_state.annotation_changed.connect(self._on_annotation_changed)

    def _on_selected_capture_changed(self, capture_id: CaptureID):
        app_state = self._get_app_state()
        loaded_capture_dict = app_state.get_capture_by_id(capture_id)
        tser, sgram = app_state.load_capture_data(
            loaded_capture_dict.parent_loadedfile.file_id,
            loaded_capture_dict.capture_idx_in_file,
            channel_idx=0)   # TODO: handle multiple channels
        self.setDisplayedSpectrogramData(sgram)
        self._annotation_manager.set_current_capture(capture_id)

    def _on_annotation_changed(self, annotation_id: AnnotationID, action: LoadedDictAction):
        self._annotation_manager.on_annotation_changed(annotation_id, action)

    def _freq_interval_set_from_specan(self, freq_interval: tuple[float,float]|None):
        self._get_app_state().set_frequency_interval(freq_interval)

    def _on_freq_interval_changed_from_outside(self, freq_interval: tuple[float,float]|None):
        self._freq_interval = freq_interval
        self._interval_roi.setVisible(self._freq_interval is not None)
        if self._freq_interval is not None:
            self._interval_roi.setRegion(self._freq_interval)

    def _on_time_interval_changed_from_outside(self, time_interval: tuple[float,float]|None):
        self._time_interval = time_interval
        self._redisplay()

    def _on_time_cursor_changed(self, t_sec: float):
        if self._sgram is None:
            return

        self._time_idx = self._sgram.time_sec.idx_nearest_to_value(t_sec)
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

            self._get_app_state().set_cursor_frequency(freq_Hz)

    def _redisplay(self):

        if self._sgram is None:
            return

        # TODO pull channel, time segment, etc
        chan = 0

        f_Hz = self._sgram.freq_Hz
        f_lo_Hz = f_Hz.min
        f_hi_Hz = f_Hz.max

        if self._time_interval is None:
            time_idx = self._time_idx
            trace = self._sgram.mag_dB[chan,time_idx,:]
        else:
            t_lo_sec, t_hi_sec = self._time_interval
            t_idx_lo = self._sgram.time_sec.idx_nearest_to_value(t_lo_sec)
            t_idx_hi = self._sgram.time_sec.idx_nearest_to_value(t_hi_sec)
            num_traces = t_idx_hi-t_idx_lo + 1
            duration_sec = self._sgram.time_sec.value_at_idx(t_idx_hi) - self._sgram.time_sec.value_at_idx(t_idx_lo)

            trace_mean = np.sum(np.abs(self._sgram.data[chan, t_idx_lo:t_idx_hi, :]), axis=0)/num_traces
            trace = 20*np.log10(trace_mean)
            # TODO: display that this is as measured across duration_sec

        self._freq_plot_curve.setData(
            x = f_Hz.array,
            y = trace,
        )
        #self._freq_plot.setAspectLocked(False)

        self._freq_plot.setXRange( f_lo_Hz, f_hi_Hz )

        trace_lo = round(trace.min(), -1)
        trace_hi = round(trace.max(), -1)
        if not np.isfinite(trace_lo):
            trace_lo = -150
        if not np.isfinite(trace_hi):
            trace_hi = +150
        self._freq_plot.setYRange( trace_lo, trace_hi )

        #self._freq_plot.setAspectLocked(True)

    def setDisplayedSpectrogramData(self, sgram:Spectrogram):
        self._sgram = sgram
        self._redisplay()