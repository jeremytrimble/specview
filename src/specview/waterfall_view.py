from PyQt5.QtCore import QPointF, QRectF
from PyQt5.QtWidgets import QApplication, QMainWindow, QGridLayout, QWidget, QSlider, QLabel, QHBoxLayout, QVBoxLayout, QPushButton, QComboBox  # tested with PyQt6==6.7.0
import pyqtgraph as pg
import dataclasses

from .loaded_file_mgmt import LoadedAnnotationDict, LoadedDictAction, AnnotationID, CaptureID
from specview.util import region_from_rectroi, signals_blocked

from .spec_types import Spectrogram
from .app_state import AppState

from .ui_constants import INTERVAL_ROI_COLOR
from .roi_select_viewboxes import RectSelectViewBox

from .labeled_rect_roi import LabeledRectROI
import sigmf

import logging
log = logging.getLogger(__name__)

@dataclasses.dataclass
class AnnotationROI:
    annotation_id: AnnotationID
    roi: LabeledRectROI
    def update_roi_relative_to_current_capture(self, wfall:"WaterfallView", selected_file_id:str, selected_capture_idx:int):
        app_state: AppState  = QApplication.instance().app_state
        ad: LoadedAnnotationDict = app_state.get_annotation_by_id(selected_file_id, self.annotation_id)

class WaterfallView(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._sgram : Spectrogram|None = None

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

        self._annotation_rois: dict[str, AnnotationROI] = {}

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
        
        app_state = self._get_app_state()
        loaded_capture_dict = app_state.get_capture_by_id(capture_id)

        loaded_capture_dict.parent_loadedfile.file_id
        tser, sgram = app_state.load_capture_data(
            loaded_capture_dict.parent_loadedfile.file_id,
            loaded_capture_dict.capture_idx_in_file,
            channel_idx=0)   # TODO: handle multiple channels
        self.setDisplayedSpectrogramData(sgram)

        # remove annotation rois related to old capture
        self._clear_annotation_rois()

        # create annotation rois for any annotations that overlap the new capture
        for annotation_id in loaded_capture_dict.parent_loadedfile.get_annotations_dict().keys():
            self._create_or_update_annotation_roi_for_annotation_id(annotation_id)

    def _create_or_update_annotation_roi_for_annotation_id(self, annotation_id:AnnotationID):
        if self._current_capture_id is None:
            log.debug(f"Skipping annotation {annotation_id=}, because no capture is selected")
            return

        ad: LoadedAnnotationDict = self._get_app_state().get_annotation_by_id(annotation_id)
        if ad is None:
            log.debug(f"Skipping annotation {annotation_id=} since it seems to have been removed/lost?")
            return 
        del annotation_id

        freq_range_Hz = ad.get_frequency_range_Hz()
        time_range_sec = ad.get_time_range_relative_to_capture(self._current_capture_id)

        if time_range_sec is None:
            log.debug(f"Skipping annotation {ad.annotation_id=} because it does not overlap current capture")
            return

        # TODO: get fields
        log.debug(f"creating/updating ROI for annotation")

        # TODO: is this a good way to display such an annotation?
        if freq_range_Hz is None:
            freq_range_Hz = self._sgram.freq_Hz.min, self._sgram.freq_Hz.max

        freq_lo_Hz, freq_hi_Hz = freq_range_Hz
        time_lo_sec, time_hi_sec = time_range_sec

        print(f"{freq_lo_Hz=}, {freq_hi_Hz=}, {time_lo_sec=}, {time_hi_sec=}")

        if ad.annotation_id not in self._annotation_rois:
            lrroi = LabeledRectROI(
                pos=(freq_lo_Hz, time_lo_sec),
                size=(freq_hi_Hz - freq_lo_Hz, time_hi_sec - time_lo_sec),
                label_text_color=(255, 255, 255),
                label_fill_color=INTERVAL_ROI_COLOR,
            )
            self._waterfall.addItem(lrroi)
            aroi = AnnotationROI(ad.annotation_id, lrroi) 
            self._annotation_rois[ad.annotation_id] = aroi
            
            # Connect the ROI's sigRegionChanged signal to update the annotation
            lrroi.sigRegionChanged.connect(
                lambda roi=lrroi, ann_id=ad.annotation_id: self._on_annotation_roi_changed(ann_id, roi)
            )
        else:
            aroi = self._annotation_rois[ad.annotation_id]
            # Block signals during programmatic updates to prevent infinite loops
            with signals_blocked(aroi.roi):
                aroi.roi.setPos( pos=(freq_lo_Hz, time_lo_sec) )
                aroi.roi.setSize( size=(freq_hi_Hz - freq_lo_Hz, time_hi_sec - time_lo_sec) )

        aroi.roi.setPen(self._roiPen)    # TODO: set this to a different color for annotations
        aroi.roi.setVisible(True)
        aroi.roi.setLabel(ad.label)

    def _clear_annotation_rois(self):
        for annotation_id in self._annotation_rois.keys():
            self._remove_annotation_roi(annotation_id)

    def _remove_annotation_roi(self, annotation_id:AnnotationID):
        if annotation_id in self._annotation_rois:
            ar: AnnotationROI = self._annotation_rois[annotation_id]
            self._waterfall.removeItem(ar.roi)
            del self._annotation_rois[annotation_id]

    def _on_annotation_changed(self, annotation_id:AnnotationID, action: LoadedDictAction):

        log.debug("WaterfallView _on_annotation_changed")
        try:
            if action in (LoadedDictAction.DELETED, LoadedDictAction.CLOSED):
                self._remove_annotation_roi(annotation_id)
            else:
                # getting into trouble here:  we need to add the AnnotationROI
                # but the time and freq ranges might not make sense yet (for the
                # currently-selected capture)
                self._create_or_update_annotation_roi_for_annotation_id(annotation_id)

        except Exception as e:
            log.exception(f"Error in WaterfallView _on_annotation_changed: {e}")

    def _on_annotation_roi_changed(self, annotation_id: AnnotationID, roi: LabeledRectROI):
        """
        Called when an annotation ROI is moved or resized by the user.
        Updates the underlying LoadedAnnotationDict with the new time and frequency ranges.
        """
        try:
            if self._current_capture_id is None:
                log.warning(f"Annotation ROI changed but no capture is selected")
                return
            
            # Get the annotation
            ad: LoadedAnnotationDict = self._get_app_state().get_annotation_by_id(annotation_id)
            if ad is None:
                log.warning(f"Annotation ROI changed but annotation {annotation_id} not found")
                return
            
            # Get ROI position and size
            left, top, right, bottom = region_from_rectroi(roi)
            
            # Update frequency range (x-axis in the waterfall)
            freq_lo_Hz = left
            freq_hi_Hz = right
            ad.update_frequency_range_Hz(freq_lo_Hz, freq_hi_Hz)
            
            # Update time range (y-axis in the waterfall)
            time_lo_sec = top
            time_hi_sec = bottom
            ad.update_time_range_relative_to_capture(self._current_capture_id, time_lo_sec, time_hi_sec)
            
            log.debug(f"Updated annotation {annotation_id}: freq=[{freq_lo_Hz:.2f}, {freq_hi_Hz:.2f}] Hz, time=[{time_lo_sec:.4f}, {time_hi_sec:.4f}] sec")
            
            # Note: The annotation_changed signal is automatically emitted by LoadedAnnotationDict
            # when we update its fields, which will propagate changes to other views
            
        except Exception as e:
            log.exception(f"Error in _on_annotation_roi_changed: {e}")


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

    def _redisplay(self):

        if self._sgram is None:
            return

        # TODO pull channel, time segment, etc
        chan = 0

        f_Hz = self._sgram.freq_Hz
        f_lo_Hz = f_Hz.min
        f_hi_Hz = f_Hz.max

        wfall_data = self._sgram.mag_dB[chan,:,:]

        time_sec = self._sgram.time_sec
        time_lo_sec = time_sec.min
        time_hi_sec = time_sec.max

        wf_rect = QRectF(
            f_lo_Hz,
            time_lo_sec, 
            f_hi_Hz - f_lo_Hz,
            time_hi_sec-time_lo_sec,
        )

        self._imageitem.setImage(wfall_data)
        self._imageitem.setRect(wf_rect)

        self._waterfall.setYRange( time_lo_sec, time_hi_sec )
        self._waterfall.setXRange( f_lo_Hz, f_hi_Hz )

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


    def setDisplayedSpectrogramData(self, sgram:Spectrogram):
        self._sgram = sgram
        self._redisplay()

    
