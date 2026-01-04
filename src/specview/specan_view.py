from PyQt6.QtCore import QPointF, QRectF, Qt, QObject, pyqtSignal, QRunnable, QThread
from PyQt6.QtWidgets import QApplication, QWidget, QHBoxLayout
import numpy as np
import numpy.typing as npt
import pyqtgraph as pg

from specview.monotonic_axis import MonotonicAxis

from .ui_constants import INTERVAL_ROI_COLOR
from .roi_select_viewboxes import IntervalSelectViewBox
from .labeled_linear_region_item import LabeledLinearRegionItem
from .annotation_roi_manager import AnnotationROIManager, ROIDimensions
from .app_state import AppState, CaptureID, AnnotationID
from .loaded_file_mgmt import LoadedCaptureDict, LoadedDictAction
from .util import freq_format

from .chunkwise_compute import (
    FrequencyDomainChunkwiseComputedArray,
    FrequencyDomainComputationSpec
)

import logging
log = logging.getLogger(__name__)
import threading

class SpecanView(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # TODO: make MHz ticks display more nicely
        myvb = IntervalSelectViewBox()

        self._selected_capture_id: CaptureID|None = None
        self._chunk_holder = ChunkHolder()
        self._chunk_holder.held_data_updated.connect( self._redisplay )

        self._freq_plot = pg.PlotWidget(labels={'left': 'PSD', 'bottom': 'Frequency [Hz]'}, viewBox=myvb)
        self._freq_plot.setMouseEnabled(x=True, y=True)
        self._freq_plot_curve = self._freq_plot.plot([]) 

        self._freq_crosshair_x = pg.InfiniteLine(angle=90, movable=False)

        self._freq_plot.addItem(self._freq_crosshair_x, ignoreBounds=True)

        layout = QHBoxLayout()
        layout.addWidget(self._freq_plot)

        self._freq_plot.scene().sigMouseMoved.connect(self._on_scene_mouse_moved)
        self.setLayout(layout)

        self._cursor_time_relto_capture = 0.0

        self._time_interval: tuple[float,float]|None = None
        self._freq_interval: tuple[float,float]|None = None

        roiPen = pg.mkPen( pg.mkColor(INTERVAL_ROI_COLOR), width=3)
        self._interval_roi = LabeledLinearRegionItem( values=(0,1), orientation="vertical", pen=roiPen, label_fill_color=(0, 0, 255, 128))
        self._interval_roi.setVisible(False)
        self._freq_plot.addItem(self._interval_roi, ignoreBounds=True)

        myvb.set_plot_and_interval(self._freq_plot, self._interval_roi)
        myvb.set_interval_change_callback( self._freq_interval_set_from_specan )

        # make sure the interval ROI is updated when the user drags it (in addition to during initial creation with shift-drag)
        self._interval_roi.sigRegionChanged.connect( lambda: self._freq_interval_set_from_specan(self._interval_roi.getRegion()) )
        self._interval_roi.sigRegionChanged.connect( self._update_freq_interval_roi_label )

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
        app_state.fft_config_changed.connect(self._on_fft_config_changed)

    def _on_selected_capture_changed(self, capture_id: CaptureID):
        self._selected_capture_id = capture_id
        self._annotation_manager.set_current_capture(capture_id)
        # nothing required yet -- will load data when cursor time changes or time interval changes

    def _on_fft_config_changed(self, new_config: FrequencyDomainComputationSpec):
        self._chunk_holder.clear_saved_data()
        self._redisplay()

    def _on_annotation_changed(self, annotation_id: AnnotationID, action: LoadedDictAction):
        self._annotation_manager.on_annotation_changed(annotation_id, action)

    def _freq_interval_set_from_specan(self, freq_interval: tuple[float,float]|None):
        self._get_app_state().set_frequency_interval(freq_interval)
    
    def _update_freq_interval_roi_label(self):
        """Update the interval ROI label with frequency information."""
        if self._selected_capture_id is None:
            return
        
        region = self._interval_roi.getRegion()
        freq_lo_Hz, freq_hi_Hz = region
        bandwidth_Hz = freq_hi_Hz - freq_lo_Hz
        center_freq_Hz = (freq_lo_Hz + freq_hi_Hz) / 2.0
        
        app_state = self._get_app_state()
        capture = app_state.get_capture_by_id(self._selected_capture_id)
        if capture is None:
            return
        
        # Get the capture's center frequency
        capture_center_freq_Hz = capture.center_freq_Hz
        
        # Calculate relative frequency (for complex signals, this can be positive or negative)
        relative_freq_Hz = center_freq_Hz - capture_center_freq_Hz

        # Format the label text
        label_lines = [
            f"Lower: {freq_format(freq_lo_Hz)}",
            f"Center: {freq_format(center_freq_Hz)}",
            f"Upper: {freq_format(freq_hi_Hz)}",
            f"Bandwidth: {freq_format(bandwidth_Hz)}",
            f"Rel. to center: {freq_format(relative_freq_Hz)}"
        ]
        
        label_text = "\n".join(label_lines)
        self._interval_roi.setLabel(label_text)

    def _on_freq_interval_changed_from_outside(self, freq_interval: tuple[float,float]|None):
        self._freq_interval = freq_interval
        self._interval_roi.setVisible(self._freq_interval is not None)
        if self._freq_interval is not None:
            self._interval_roi.setRegion(self._freq_interval)
            self._update_freq_interval_roi_label()

    def _on_time_interval_changed_from_outside(self, time_interval: tuple[float,float]|None):
        self._time_interval = time_interval
        self._redisplay()

    def _on_time_cursor_changed(self, t_sec: float):
        if self._selected_capture_id is None:
            return

        self._cursor_time_relto_capture = t_sec
        self._redisplay()

    def _on_freq_cursor_changed(self, freq_Hz: float):
        self._freq_crosshair_x.setPos(freq_Hz)

    def _on_scene_mouse_moved(self, pos: QPointF):
        if self._freq_plot.sceneBoundingRect().contains(pos):
            mousePoint = self._freq_plot.getViewBox().mapSceneToView(pos)
            freq_Hz = mousePoint.x()
            magnitude_dB = mousePoint.y()
            self._freq_crosshair_x.setPos( freq_Hz )

            self._get_app_state().set_cursor_frequency(freq_Hz)

    def _redisplay(self):

        if self._selected_capture_id is None:
            return

        capture:LoadedCaptureDict = self._get_app_state().get_capture_by_id(self._selected_capture_id)
        if capture is None:
            return

        # TODO pull channel, time segment, etc
        chan = 0

        if self._time_interval is None:
            cursor_time_sec = self._cursor_time_relto_capture

            if cursor_time_sec < 0.0 or cursor_time_sec >= capture.duration_sec:
                return

            rv = self._chunk_holder.get_data_for(
                capture_id=self._selected_capture_id,
                channel=chan,
                time_relto_capture=cursor_time_sec,
                duration_sec=None,
            )
            if rv is None:
                # data not yet available, but chunkholder has started a background load and will re-call us when ready
                return

            arr, freq_axis = rv

            trace = arr[0,:]
        else:
            t_lo_sec, t_hi_sec = self._time_interval

            rv = self._chunk_holder.get_data_for(
                capture_id=self._selected_capture_id,
                channel=chan,
                time_relto_capture=t_lo_sec,
                duration_sec=t_hi_sec - t_lo_sec,
            )
            if rv is None:
                # data not yet available, but chunkholder has started a background load and will re-call us when ready
                return

            arr, freq_axis = rv

            arr = np.power(10, (arr/20.0))
            trace = arr.mean(axis=0, out=arr[0,:])
            trace = 20 * np.log10(trace)

        self._freq_plot_curve.setData(
            x = freq_axis.array,
            y = trace,
        )
        #self._freq_plot.setAspectLocked(False)

        MIN_dB = -180
        MAX_dB = 70

        trace_lo = round(trace.min(), -1) - 3
        trace_hi = round(trace.max(), -1) + 3
        if not np.isfinite(trace_lo) or trace_lo < MIN_dB:
            trace_lo = MIN_dB
        if not np.isfinite(trace_hi) or trace_hi > MAX_dB:
            trace_hi = MAX_dB

        self._freq_plot.setLimits(
            xMin=freq_axis.min,
            xMax=freq_axis.max,
            yMin=MIN_dB,
            yMax=MAX_dB,
            # TODO: compute limits of data in thread and set limits appropriately
        )


class ChunkHolder(QObject):

    held_data_updated = pyqtSignal()

    """
    Caches a chunk of data from a ChunkwiseComputedArray to avoid repeated reads when the user is scrolling nearby.
    """
    def __init__(self):
        super().__init__()
        self._frame_margin = 1000

        self._array: npt.NDArray | None = None
        self._array_channel: int | None = None
        self._array_capture_id: CaptureID|None = None
        self._array_start_time_relto_capture: float = 0.0
        self._array_delta_t_per_frame: float = 0.0
        self._array_freq_axis_Hz: MonotonicAxis | None = None

        self._data_update_in_progress: SpecanViewUpdaterWorker | None = None
    
    def clear_saved_data(self):
        self._array = None

    def get_data_for(self, capture_id: CaptureID, channel:int, time_relto_capture:float, duration_sec:float|None=None) -> tuple[npt.NDArray, MonotonicAxis]|None:

        if duration_sec is not None and duration_sec <= 0:
            raise ValueError("duration_sec must be positive or None")

        if self._array is not None and self._array_capture_id == capture_id and self._array_channel == channel:
            num_frames, _ = self._array.shape

            array_end_time_relto_capture = self._array_start_time_relto_capture + (num_frames-1)*self._array_delta_t_per_frame

            start_frame_idx = None
            if duration_sec is None:
                if time_relto_capture >= self._array_start_time_relto_capture and time_relto_capture < array_end_time_relto_capture:
                    # already have the data we need
                    start_frame_idx = int( (time_relto_capture - self._array_start_time_relto_capture)/self._array_delta_t_per_frame )
                    end_frame_idx = start_frame_idx + 1
            else: # duration_sec is not None
                if time_relto_capture >= self._array_start_time_relto_capture and (time_relto_capture + duration_sec) < array_end_time_relto_capture:
                    # already have the data we need
                    start_frame_idx = int( (time_relto_capture - self._array_start_time_relto_capture)/self._array_delta_t_per_frame )
                    num_frames_needed = int(duration_sec/self._array_delta_t_per_frame) + 1
                    end_frame_idx = start_frame_idx + num_frames_needed
                    del num_frames_needed

            if start_frame_idx is not None:
                return self._array[start_frame_idx:end_frame_idx, :], self._array_freq_axis_Hz

        # if we got here, we need to load new data
        # before returning None, we'll fire off a background load of the data we need
        self._array = None

        if self._data_update_in_progress is not None:
            self._data_update_in_progress.canceled.set()
            self._data_update_in_progress = None

        app_state = QApplication.instance().app_state
        capture :LoadedCaptureDict = app_state.get_capture_by_id(capture_id)
        if capture is None:
            return None 
        loaded_file = capture.parent_loadedfile
        sample_rate_Hz = loaded_file.sample_rate_Hz
        cca = loaded_file.get_freq_chunkwise_computed_array(selected_channel=channel, comp_spec=app_state.get_fft_config())

        capture_start_time_sec_relto_file = capture.start_sample_idx/sample_rate_Hz
        data_start_time_sec_relto_file = (capture_start_time_sec_relto_file + time_relto_capture - self._frame_margin * cca.delta_t_per_frame )
        data_end_time_sec_relto_file = (capture_start_time_sec_relto_file + (time_relto_capture+duration_sec if duration_sec is not None else time_relto_capture) + self._frame_margin * cca.delta_t_per_frame )

        start_idx_relto_file = cca.time_axis.idx_nearest_to_value(data_start_time_sec_relto_file)
        end_idx_relto_file = cca.time_axis.idx_nearest_to_value(data_end_time_sec_relto_file)   

        true_start_time_sec_relto_file = cca.time_axis.value_at_idx(start_idx_relto_file)
        true_start_time_sec_relto_capture = true_start_time_sec_relto_file - capture_start_time_sec_relto_file

        runnable = SpecanViewUpdaterWorker(
            cca=cca,
            start_idx_relto_file=start_idx_relto_file,
            end_idx_relto_file=end_idx_relto_file,
            true_start_time_sec_relto_capture=true_start_time_sec_relto_capture,
            channel=channel,
            capture_id=capture_id,
            center_freq_Hz=capture.center_freq_Hz,
        )
        self._data_update_in_progress = runnable
        runnable.signals.update_data_signal.connect( self._update_held_data )
        QApplication.instance().thread_pool.start(runnable)

    def _update_held_data(self, array_data: npt.NDArray, start_time_sec_relto_capture: float, channel:int, capture_id:CaptureID, delta_t_per_frame:float, freq_axis_Hz:MonotonicAxis):
        self._array = array_data
        self._array_start_time_relto_capture = start_time_sec_relto_capture
        self._array_channel = channel
        self._array_capture_id = capture_id
        self._array_delta_t_per_frame = delta_t_per_frame
        self._array_freq_axis_Hz = freq_axis_Hz

        self._data_update_in_progress = None

        self.held_data_updated.emit()

class SpecanViewUpdaterSignals(QObject):
    update_data_signal = pyqtSignal((
        np.ndarray, float, int, CaptureID, float, MonotonicAxis
    ))

class SpecanViewUpdaterWorker(QRunnable):
    def __init__(self, 
            cca: FrequencyDomainChunkwiseComputedArray,
            start_idx_relto_file: int,
            end_idx_relto_file: int,
            true_start_time_sec_relto_capture: float,
            channel: int,
            capture_id: CaptureID,
            center_freq_Hz: float,
        ):
        super().__init__()

        self._cca = cca
        self._start_idx_relto_file = start_idx_relto_file
        self._end_idx_relto_file = end_idx_relto_file
        self._true_start_time_sec_relto_capture = true_start_time_sec_relto_capture
        self._channel = channel
        self._capture_id = capture_id
        self._center_freq_Hz = center_freq_Hz

        self.signals = SpecanViewUpdaterSignals()
        self.canceled = threading.Event()

    def run(self):
        try:
            array_data = self._cca.get_range_blocking(
                self._start_idx_relto_file,
                self._end_idx_relto_file
            )

            if not self.canceled.is_set():
                self.signals.update_data_signal.emit( 
                    array_data, self._true_start_time_sec_relto_capture, self._channel, self._capture_id, self._cca.delta_t_per_frame, self._cca.get_freq_axis_assuming_center_frequency(self._center_freq_Hz)
                )
        except:
            log.exception("Error in SpecanViewUpdaterWorker")
