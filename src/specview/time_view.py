from PyQt6.QtCore import QPointF, QObject, QRunnable, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication, QWidget, QHBoxLayout
import pyqtgraph as pg
import numpy as np
import sigmf

from .app_state import AppState, CaptureID, AnnotationID
from .loaded_file_mgmt import LoadedDictAction
from .roi_select_viewboxes import IntervalSelectViewBox
from .ui_constants import INTERVAL_ROI_COLOR
from .labeled_linear_region_item import LabeledLinearRegionItem
from .annotation_roi_manager import AnnotationROIManager, ROIDimensions
import threading

from .chunkwise_compute import ChunkwiseComputedArray
import logging
log = logging.getLogger(__name__)

INITIAL_TIME_POINTS_TO_DISPLAY = 100_000

class TimeView(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        myvb = IntervalSelectViewBox()

        self._time_plot = pg.PlotWidget(labels={'left': 'Amplitude', 'bottom': 'Time [seconds]'}, viewBox=myvb)
        self._time_plot.setMouseEnabled(x=True, y=True)
        self._time_plot.setYRange(-1.1, 1.1)

        self._time_plot_curve_i = self._time_plot.plot([], name="real", pen=pg.mkPen('b')) 
        self._time_plot_curve_q = self._time_plot.plot([], name="imaginary", pen=pg.mkPen('r')) 

        self._time_plot_curve_i.setDownsampling(auto=True, method='peak')
        self._time_plot_curve_q.setDownsampling(auto=True, method='peak')

        self._time_crosshair_x = pg.InfiniteLine(angle=90, movable=False)
        self._time_plot.addItem(self._time_crosshair_x, ignoreBounds=True)

        self._time_plot.scene().sigMouseMoved.connect(self._on_scene_mouse_moved)

        self._time_plot.sigRangeChanged.connect(self._on_range_changed)

        self._selected_capture_id: CaptureID|None = None

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

        # Initialize the annotation ROI manager for linear ROIs
        def roi_factory(**kwargs):
            return LabeledLinearRegionItem(orientation="vertical", pen=roiPen, **kwargs)
        
        self._annotation_manager = AnnotationROIManager(
            plot_widget=self._time_plot,
            roi_dimensions=ROIDimensions.TIME,
        )

        self._data_update_in_progress: TimeViewUpdaterWorker|None = None

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
        app_state.annotation_changed.connect(self._on_annotation_changed)
        app_state.time_view_seek_to_time_requested.connect(self.seek_to_time)
        # TODO: process selected channel changes
        #app_state.selected_channel_changed.connect(self._on_selected_channel_changed)

    def _on_selected_capture_changed(self, capture_id: CaptureID):

        # save which capture we are displaying
        self._selected_capture_id = capture_id  
        self._annotation_manager.set_current_capture(capture_id)

        app_state = self._get_app_state()
        capture = app_state.get_capture_by_id(capture_id)
        loaded_file = capture.parent_loadedfile

        sample_rate_Hz = loaded_file.sigmf_file.get_global_field(sigmf.SigMFFile.SAMPLE_RATE_KEY)
        if sample_rate_Hz is None or sample_rate_Hz <= 0:
            log.error("Invalid or missing sample rate. Cannot display time data.")
            return

        start_time_sec = 0.0
        end_time_sec = min(capture.num_samples / sample_rate_Hz, INITIAL_TIME_POINTS_TO_DISPLAY / sample_rate_Hz)

        # Set the time range to show up to MAX_TIME_POINTS_TO_DISPLAY samples
        #  this will cause the _on_range_changed to be called, which will
        #  trigger loading of the data in the background
        self._time_plot.setXRange(start_time_sec, end_time_sec)

    def _on_annotation_changed(self, annotation_id: AnnotationID, action: LoadedDictAction):
        self._annotation_manager.on_annotation_changed(annotation_id, action)

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

    def _on_range_changed(self, plot_widget:pg.PlotWidget, the_range:tuple[tuple[float,float], tuple[float,float]]):
        x_range, y_range = the_range
        x_min_sec, x_max_sec = x_range
        #plot_widget.setYRange(-1.1, 1.1)  # keep y range fixed, TODO: this is probably not the best way to do this

        # TODO: enforce maximum zoom-out here?

        self._update_displayed_data(x_min_sec, x_max_sec)

    def _on_scene_mouse_moved(self, pos: QPointF):
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

    def _set_plot_data(self, array_data: np.ndarray, true_start_idx_relto_capture: int):

        chan = 0 # TODO: pick out the right channel

        capture = self._get_app_state().get_capture_by_id(self._selected_capture_id)
        if not capture:
            return
        
        sample_rate_Hz = capture.parent_loadedfile.sigmf_file.get_global_field(sigmf.SigMFFile.SAMPLE_RATE_KEY)
        if sample_rate_Hz is None or sample_rate_Hz <= 0:    
            return  

        num_samples = array_data.shape[0]
        time_sec_axis = np.arange(true_start_idx_relto_capture, true_start_idx_relto_capture + num_samples) / sample_rate_Hz    

        self._time_plot_curve_i.setData(
            x = time_sec_axis,
            y = array_data[:,chan].real,
        )
        self._time_plot_curve_q.setData(
            x = time_sec_axis,
            y = array_data[:,chan].imag,
        )

        self._time_plot.setLimits(
            xMin=0.0,
            xMax=capture.duration_sec,
            maxXRange=5.0, #TODO: is this reasonable?
            # TODO: compute exents of data in thread and set limits appropriately
        )

        #self._time_plot.setXRange(time_sec_axis.min(), time_sec_axis.max())
        #self._time_plot.setYRange(-1.1, 1.1)  # reasonable default for normalized data, TODO: make this based on data extents later?

    def seek_to_time(self, time_sec: float):
        """Seek to a specific time in seconds by centering the view on it."""
        if self._selected_capture_id is None:
            return
        
        # Get current view range to determine how much to show around the target time
        x_range, y_range = self._time_plot.viewRange()
        current_width = x_range[1] - x_range[0]
        
        # Center the view on the target time
        half_width = current_width / 2.0
        new_x_min = time_sec - half_width
        new_x_max = time_sec + half_width
        
        self._time_plot.setXRange(new_x_min, new_x_max, padding=0)

    def _update_displayed_data(self, x_min_sec:float, x_max_sec:float):

        if self._selected_capture_id is None:
            return

        if self._data_update_in_progress is not None:
            self._data_update_in_progress.canceled.set()

        MARGIN_SAMPLES = 1000

        app_state = self._get_app_state()
        capture = app_state.get_capture_by_id(self._selected_capture_id)
        if capture is None:
            return
        loaded_file = capture.parent_loadedfile
        sample_rate_Hz = loaded_file.sigmf_file.get_global_field(sigmf.SigMFFile.SAMPLE_RATE_KEY)

        start_idx_relto_capture = capture.time_axis.idx_nearest_to_value(x_min_sec) - MARGIN_SAMPLES
        start_idx_relto_file = max(0, capture.start_sample_idx + start_idx_relto_capture)
        true_start_idx_relto_capture = start_idx_relto_file - capture.start_sample_idx

        end_idx_relto_capture = capture.time_axis.idx_nearest_to_value(x_max_sec) + MARGIN_SAMPLES
        end_idx_relto_file = min(capture.start_sample_idx + end_idx_relto_capture, loaded_file.sigmf_file.sample_count)

        runnable = TimeViewUpdaterWorker(
            cca = loaded_file.get_time_chunkwise_computed_array(),
            true_start_idx_relto_capture=true_start_idx_relto_capture,
            start_idx_relto_file=start_idx_relto_file,
            end_idx_relto_file=end_idx_relto_file,
            sample_rate_Hz=sample_rate_Hz,
        )
        
        self._data_update_in_progress = runnable
        runnable.signals.update_data_signal.connect(self._set_plot_data)
        QApplication.instance().thread_pool.start(runnable)

class TimeViewUpdaterSignals(QObject):
    update_data_signal = pyqtSignal((np.ndarray, int))

class TimeViewUpdaterWorker(QRunnable):
    def __init__(self, 
            cca: ChunkwiseComputedArray,
            true_start_idx_relto_capture:int,
            start_idx_relto_file:int,
            end_idx_relto_file:int,
            sample_rate_Hz:float,
        ):
        super().__init__()

        self._cca = cca
        self._true_start_idx_relto_capture = true_start_idx_relto_capture
        self._start_idx_relto_file = start_idx_relto_file
        self._end_idx_relto_file = end_idx_relto_file
        self._sample_rate_Hz = sample_rate_Hz

        self.signals = TimeViewUpdaterSignals()
        self.canceled = threading.Event()

    def run(self):
        try:
            array_data = self._cca.get_range_blocking(
                self._start_idx_relto_file,
                self._end_idx_relto_file
            )

            if not self.canceled.is_set():
                self.signals.update_data_signal.emit( array_data, self._true_start_idx_relto_capture )
        except:
            log.exception("Error in TimeViewUpdaterWorker")