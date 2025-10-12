from PyQt5.QtCore import QPointF, QRectF, QObject, QRunnable, QThread, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QApplication, QWidget, QHBoxLayout
import pyqtgraph as pg
import numpy as np

from .loaded_file_mgmt import CaptureID, LoadedDictAction, AnnotationID, LoadedAnnotationDict
from specview.util import region_from_rectroi

from .app_state import AppState

from .ui_constants import INTERVAL_ROI_COLOR
from .roi_select_viewboxes import RectSelectViewBox

from .labeled_rect_roi import LabeledRectROI
from .annotation_roi_manager import AnnotationROIManager, ROIDimensions
from .chunkwise_compute import (
    ChunkwiseComputedArray, FrequencyDomainChunkwiseComputedArray
)
import threading

import logging
log = logging.getLogger(__name__)

INITIAL_FRAMES_TO_DISPLAY = 1_000

class WaterfallView(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        myvb = RectSelectViewBox()

        # Layout container for waterfall related stuff
        waterfall_layout = QHBoxLayout()

        # Waterfall plot
        self._waterfall = pg.PlotWidget(labels={'left': 'Time [s]', 'bottom': 'Frequency [MHz]'}, viewBox=myvb)
        self._waterfall.plotItem.getViewBox().invertY(True)
        self._imageitem = pg.ImageItem(axisOrder='row-major')
        self._waterfall.addItem(self._imageitem)
        self._waterfall.setMouseEnabled(x=True, y=True)
        waterfall_layout.addWidget(self._waterfall)

        self._waterfall.sigRangeChanged.connect(self._on_range_changed)

        self._data_update_in_progress: WaterfallViewUpdaterWorker|None= None

        # Colorbar for waterfall
        self._colorbar = pg.HistogramLUTWidget()
        self._colorbar.setImageItem(self._imageitem) # connects the bar to the waterfall imageitem
        self._colorbar.item.gradient.loadPreset('viridis') # set the color map, also sets the imageitem
        self._imageitem.setLevels((-30, 20)) # needs to come after colorbar is created for some reason
        waterfall_layout.addWidget(self._colorbar)

        # Freq crosshair
        self._freq_crosshair_x = pg.InfiniteLine(angle=90, movable=False)
        self._waterfall.addItem(self._freq_crosshair_x, ignoreBounds=True)

        self._time_crosshair_y = pg.InfiniteLine(angle=0, movable=False)
        self._waterfall.addItem(self._time_crosshair_y, ignoreBounds=True)

        self._roiPen = pg.mkPen(INTERVAL_ROI_COLOR, width=3)
        #roi = pg.RectROI(pos=(0,0), size=(200,400), sideScalers=True, rotatable=False)
        roi = LabeledRectROI(pos=(0,0), size=(200,400), sideScalers=True, rotatable=False, label_text="Waterfall ROI", label_text_color=(255,255,255), label_fill_color=INTERVAL_ROI_COLOR)
        roi.setPen(self._roiPen)
        roi.setVisible(False) # Initially hidden

        self._roi = roi

        # make sure the rect ROI is updated when the user drags it (in addition to during initial creation with shift-drag)
        self._roi.sigRegionChanged.connect( lambda: self._waterfall_roi_set( region_from_rectroi(self._roi)) )

        myvb.set_plot_and_rect(self._waterfall, self._roi)
        myvb.set_roi_change_callback(self._waterfall_roi_set)

        self._waterfall.addItem(roi)

        self._waterfall.scene().sigMouseMoved.connect(self._on_scene_mouse_moved)

        self.setLayout(waterfall_layout)

        # Initialize the annotation ROI manager for rectangular ROIs
        def roi_factory(**kwargs):
            return LabeledRectROI(sideScalers=True, rotatable=False, **kwargs)
        
        self._annotation_manager = AnnotationROIManager(
            plot_widget=self._waterfall,
            roi_dimensions=ROIDimensions.TIME_AND_FREQUENCY,
        )

        self._current_capture_id: CaptureID|None = None

        self._connect_app_signals()

    def _get_app_state(self) -> AppState:
        return QApplication.instance().app_state

    def _waterfall_roi_set(self, region: tuple[float, float] | None):
        #print(f"{region=}")
        if region is None:
            self._get_app_state().set_frequency_interval(None)
            self._get_app_state().set_time_interval(None)
        else:
            freq_lo_Hz, time_lo_sec, freq_hi_Hz, time_hi_sec = region
            self._get_app_state().set_frequency_interval((freq_lo_Hz, freq_hi_Hz))
            self._get_app_state().set_time_interval((time_lo_sec, time_hi_sec))

    def _connect_app_signals(self):
        app_state = self._get_app_state()
        app_state.cursor_frequency_changed.connect(self._on_cursor_frequency_changed)
        app_state.cursor_time_changed.connect(self._on_cursor_time_changed)

        # TODO: uncommenting either of the below works, but not both
        app_state.time_interval_changed.connect(self._on_interval_changed)
        app_state.frequency_interval_changed.connect(self._on_interval_changed)
        app_state.selected_capture_changed.connect(self._on_selected_capture_changed)

        app_state.annotation_changed.connect(self._on_annotation_changed)
        print("WaterfallView connected to app_state.annotation_changed")

    def _on_selected_capture_changed(self, capture_id: CaptureID):
        self._current_capture_id = capture_id
        self._annotation_manager.set_current_capture(capture_id)
        
        app_state = self._get_app_state()
        capture = app_state.get_capture_by_id(capture_id)

        if capture is None:
            return

        chan = 0 # TODO: select channel from somewhere

        loaded_file = capture.parent_loadedfile
        cca = loaded_file.get_freq_chunkwise_computed_array(selected_channel=chan)

        center_freq_Hz = capture.center_freq_Hz
        sample_rate_Hz = loaded_file.sample_rate_Hz

        freq_axis = cca.get_freq_axis_assuming_center_frequency(center_freq_Hz)
        time_axis = cca.time_axis
        capture_start_time_sec_relto_file = capture.start_sample_idx/sample_rate_Hz

        capture_duration_sec = capture.num_samples / sample_rate_Hz
        initial_display_duration_sec = INITIAL_FRAMES_TO_DISPLAY * cca.delta_t_per_frame
        duration_to_display = min(capture_duration_sec, initial_display_duration_sec)

        # Set the range to show up to MAX_TIME_POINTS_TO_DISPLAY samples
        #  this will cause the _on_range_changed to be called, which will
        #  trigger loading of the data in the background

        rect = QRectF(
            QPointF(freq_axis.min, capture_start_time_sec_relto_file),
            QPointF(freq_axis.max, capture_start_time_sec_relto_file + duration_to_display)
        )

        self._waterfall.setRange(rect=rect, padding=0.0)

        #self._waterfall.setRange(

        #    xRange=(freq_axis.min, freq_axis.max),
        #    yRange=(capture_start_time_sec_relto_file, 
        #            capture_start_time_sec_relto_file + duration_to_display)
        #)
        
    def _on_range_changed(self, plot_widget:pg.PlotWidget, the_range:tuple[tuple[float,float], tuple[float,float]]):
        x_range, y_range = the_range
        y_min_sec, y_max_sec = y_range

        print(f"waterfall: on_range_changed: {y_min_sec=}, {y_max_sec=}")

        # TODO: enforce maximum zoom-out here?

        self._update_displayed_data(y_min_sec, y_max_sec)

    def _on_annotation_changed(self, annotation_id: AnnotationID, action: LoadedDictAction):
        self._annotation_manager.on_annotation_changed(annotation_id, action)


    def _on_interval_changed(self):
        app_state = self._get_app_state()

        time_interval = app_state._time_interval
        freq_interval = app_state._frequency_interval

        if None in (time_interval, freq_interval):
            self._roi.setVisible(False)
        else:
            # both intervals are set, so show the ROI
            self._roi.setVisible(True)
            time_lo_sec, time_hi_sec = time_interval
            f_lo_Hz, f_hi_Hz = freq_interval
            rect_roi = self._roi
            # Update the position and size of the ROI
            rect_roi.setPos((f_lo_Hz, time_lo_sec))
            rect_roi.setSize((f_hi_Hz - f_lo_Hz, time_hi_sec - time_lo_sec))

    def _on_cursor_time_changed(self, t_sec: float):
        self._time_crosshair_y.setPos(t_sec)

    def _on_cursor_frequency_changed(self, f_Hz: float):
        self._freq_crosshair_x.setPos(f_Hz)

    def _on_scene_mouse_moved(self, pos: QPointF):
        #print(f"on_scene_mouse_moved: {args=}, {kwargs=}")
        if self._waterfall.sceneBoundingRect().contains(pos):
            mousePoint = self._waterfall.getViewBox().mapSceneToView(pos)
            freq_Hz = mousePoint.x()
            time_sec = mousePoint.y()
            self._freq_crosshair_x.setPos( freq_Hz )
            self._time_crosshair_y.setPos( time_sec )

            # TODO: handle frequency interval selection later:
            self._get_app_state().set_cursor_frequency(freq_Hz)
            self._get_app_state().set_cursor_time(time_sec)

    def _set_plot_data(self, array_data: np.ndarray, true_start_time_sec_relto_capture: float):
        if self._current_capture_id is None:
            return

        app_state = self._get_app_state()
        capture = app_state.get_capture_by_id(self._current_capture_id)
        if capture is None:
            return 
        loaded_file = capture.parent_loadedfile
        sample_rate_Hz = loaded_file.sample_rate_Hz

        chan = 0 # TODO: select channel from somewhere

        cca = loaded_file.get_freq_chunkwise_computed_array(selected_channel=chan)
        freq_axis = cca.get_freq_axis_assuming_center_frequency( capture.center_freq_Hz )
        time_axis = cca.time_axis

        num_frames, num_freq_bins = array_data.shape

        f_lo_Hz = freq_axis.min
        f_hi_Hz = freq_axis.max
        time_lo_sec = true_start_time_sec_relto_capture
        time_hi_sec = time_lo_sec + num_frames * cca.delta_t_per_frame

        print(f"_set_plot_data: {array_data.shape=}, {f_lo_Hz=}, {f_hi_Hz=}, {time_lo_sec=}, {time_hi_sec=}, {true_start_time_sec_relto_capture=}")

        wf_rect = QRectF(
            f_lo_Hz,
            time_lo_sec, 
            f_hi_Hz - f_lo_Hz,
            time_hi_sec-time_lo_sec,
        )

        self._imageitem.setImage(array_data)
        self._imageitem.setRect(wf_rect)

        # TODO: enforce max zoom-out here?
        #self._waterfall.setYRange( time_lo_sec, time_hi_sec )
        #self._waterfall.setXRange( f_lo_Hz, f_hi_Hz )

    def _update_displayed_data(self, y_min_sec:float, y_max_sec:float):
        if self._current_capture_id is None:
            return

        if self._data_update_in_progress is not None:
            self._data_update_in_progress.canceled.set()

        MARGIN_FRAMES = 10

        app_state = self._get_app_state()
        capture = app_state.get_capture_by_id(self._current_capture_id)
        if capture is None:
            return 
        loaded_file = capture.parent_loadedfile
        sample_rate_Hz = loaded_file.sample_rate_Hz

        # TODO: select channel from somewhere
        chan = 0

        cca = loaded_file.get_freq_chunkwise_computed_array(selected_channel=chan)

        capture_start_time_sec_relto_file = capture.start_sample_idx/sample_rate_Hz
        data_start_time_sec_relto_file = (capture_start_time_sec_relto_file + y_min_sec - MARGIN_FRAMES * cca.delta_t_per_frame )
        data_end_time_sec_relto_file = (capture_start_time_sec_relto_file + y_max_sec + MARGIN_FRAMES * cca.delta_t_per_frame )

        start_idx_relto_file = cca.time_axis.idx_nearest_to_value(data_start_time_sec_relto_file)
        end_idx_relto_file = cca.time_axis.idx_nearest_to_value(data_end_time_sec_relto_file)   

        true_start_time_sec_relto_file = cca.time_axis.value_at_idx(start_idx_relto_file)
        true_start_time_sec_relto_capture = true_start_time_sec_relto_file - capture_start_time_sec_relto_file
        print(f"wf: {true_start_time_sec_relto_capture=}")

        runnable = WaterfallViewUpdaterWorker(
            cca=cca,
            start_idx_relto_file=start_idx_relto_file,
            end_idx_relto_file=end_idx_relto_file,
            true_start_time_sec_relto_capture=true_start_time_sec_relto_capture,
        )

        self._data_update_in_progress = runnable
        runnable.signals.update_data_signal.connect(self._set_plot_data)
        QApplication.instance().thread_pool.start(runnable)


class WaterfallViewUpdaterSignals(QObject):
    update_data_signal = pyqtSignal((np.ndarray, float))

class WaterfallViewUpdaterWorker(QRunnable):
    def __init__(self, 
            cca: ChunkwiseComputedArray,
            start_idx_relto_file: int,
            end_idx_relto_file: int,
            true_start_time_sec_relto_capture: float,
        ):
        super().__init__()

        self._cca = cca
        self._start_idx_relto_file = start_idx_relto_file
        self._end_idx_relto_file = end_idx_relto_file
        self._true_start_time_sec_relto_capture = true_start_time_sec_relto_capture

        self.signals = WaterfallViewUpdaterSignals()
        self.canceled = threading.Event()

    def run(self):
        print(f"WaterfallViewUpdaterWorker running in thread {QThread.currentThread()}")
        try:
            array_data = self._cca.get_range_blocking(
                self._start_idx_relto_file,
                self._end_idx_relto_file
            )

            if not self.canceled.is_set():
                self.signals.update_data_signal.emit( array_data, self._true_start_time_sec_relto_capture )
                print(f"emitted update_data_signal")
            else:
                print(f"canceled, not emitting update_data_signal") # TODO:remove these prints
        except:
            log.exception("Error in WaterfallViewUpdaterWorker")