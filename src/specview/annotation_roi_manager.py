from typing import Union, TypeVar, Generic, Dict
from dataclasses import dataclass
import logging
from PyQt5.QtWidgets import QApplication
import pyqtgraph as pg

from .labeled_rect_roi import LabeledRectROI
from .labeled_linear_region_item import LabeledLinearRegionItem
from .loaded_file_mgmt import LoadedAnnotationDict, LoadedDictAction, AnnotationID, CaptureID
from .app_state import AppState
from .ui_constants import INTERVAL_ROI_COLOR

log = logging.getLogger(__name__)

ROIType = TypeVar('ROIType', LabeledRectROI, LabeledLinearRegionItem)

@dataclass
class AnnotationROI(Generic[ROIType]):
    """Class to hold an annotation ROI and its metadata"""
    annotation_id: AnnotationID
    roi: ROIType

class AnnotationROIManager(Generic[ROIType]):
    """
    A class to manage annotation ROIs across different views (Waterfall, Time, Spectrum).
    This class abstracts the common functionality for handling annotations and their visual
    representation as ROIs.
    """
    
    def __init__(self, plot_widget: pg.PlotWidget, roi_factory, is_rectangular: bool = False):
        """
        Initialize the annotation ROI manager.
        
        Args:
            plot_widget: The plot widget where ROIs will be displayed
            roi_factory: A callable that creates a new ROI (either LabeledRectROI or LabeledLinearRegionItem)
            is_rectangular: True if using rectangular ROIs, False for linear ROIs
        """
        self._plot_widget = plot_widget
        self._roi_factory = roi_factory
        self._is_rectangular = is_rectangular
        self._annotation_rois: Dict[str, AnnotationROI] = {}
        self._current_capture_id: CaptureID = None
        self._roiPen = pg.mkPen(INTERVAL_ROI_COLOR, width=3)
        
    def _get_app_state(self) -> AppState:
        return QApplication.instance().app_state
    
    def clear_annotation_rois(self):
        """Remove all annotation ROIs from the view."""
        for annotation_id in list(self._annotation_rois.keys()):
            self._remove_annotation_roi(annotation_id)
            
    def _remove_annotation_roi(self, annotation_id: AnnotationID):
        """Remove a specific annotation ROI from the view."""
        if annotation_id in self._annotation_rois:
            ar: AnnotationROI = self._annotation_rois[annotation_id]
            self._plot_widget.removeItem(ar.roi)
            del self._annotation_rois[annotation_id]
            
    def set_current_capture(self, capture_id: CaptureID):
        """Set the current capture and update ROIs accordingly."""
        self._current_capture_id = capture_id
        self.clear_annotation_rois()
        
        # Create annotation ROIs for annotations that overlap the new capture
        loaded_capture_dict = self._get_app_state().get_capture_by_id(capture_id)
        for annotation_id in loaded_capture_dict.parent_loadedfile.get_annotations_dict().keys():
            self._create_or_update_annotation_roi_for_annotation_id(annotation_id)
            
    def _create_or_update_annotation_roi_for_annotation_id(self, annotation_id: AnnotationID):
        """Create or update an annotation ROI based on the annotation ID."""
        if self._current_capture_id is None:
            log.debug(f"Skipping annotation {annotation_id=}, because no capture is selected")
            return

        ad: LoadedAnnotationDict = self._get_app_state().get_annotation_by_id(annotation_id)
        if ad is None:
            log.debug(f"Skipping annotation {annotation_id=} since it seems to have been removed/lost?")
            return

        freq_range_Hz = ad.get_frequency_range_Hz()
        time_range_sec = ad.get_time_range_relative_to_capture(self._current_capture_id)

        if time_range_sec is None:
            log.debug(f"Skipping annotation {ad.annotation_id=} because it does not overlap current capture")
            return

        if self._is_rectangular:
            # Handle rectangular ROI (Waterfall view)
            if freq_range_Hz is None:
                freq_range_Hz = (0, 1)  # This should be replaced with actual frequency range

            freq_lo_Hz, freq_hi_Hz = freq_range_Hz
            time_lo_sec, time_hi_sec = time_range_sec

            if ad.annotation_id not in self._annotation_rois:
                roi = self._roi_factory(
                    pos=(freq_lo_Hz, time_lo_sec),
                    size=(freq_hi_Hz - freq_lo_Hz, time_hi_sec - time_lo_sec),
                    label_text_color=(255, 255, 255),
                    label_fill_color=INTERVAL_ROI_COLOR,
                )
                self._plot_widget.addItem(roi)
                aroi = AnnotationROI(ad.annotation_id, roi)
                self._annotation_rois[ad.annotation_id] = aroi
            else:
                aroi = self._annotation_rois[ad.annotation_id]
                aroi.roi.setPos(pos=(freq_lo_Hz, time_lo_sec))
                aroi.roi.setSize(size=(freq_hi_Hz - freq_lo_Hz, time_hi_sec - time_lo_sec))
        else:
            # Handle linear ROI (Time or Spectrum view)
            if self._is_frequency_view:
                if freq_range_Hz is None:
                    return
                region = freq_range_Hz
            else:
                region = time_range_sec

            if ad.annotation_id not in self._annotation_rois:
                roi = self._roi_factory(
                    values=region,
                    label_text=ad.label,
                    label_text_color=(255, 255, 255),
                    label_fill_color=INTERVAL_ROI_COLOR,
                )
                self._plot_widget.addItem(roi)
                aroi = AnnotationROI(ad.annotation_id, roi)
                self._annotation_rois[ad.annotation_id] = aroi
            else:
                aroi = self._annotation_rois[ad.annotation_id]
                aroi.roi.setRegion(region)

        aroi.roi.setPen(self._roiPen)
        aroi.roi.setVisible(True)
        aroi.roi.setLabel(ad.label)

    def on_annotation_changed(self, annotation_id: AnnotationID, action: LoadedDictAction):
        """Handle annotation changes (creation, updates, deletion)."""
        try:
            if action in (LoadedDictAction.DELETED, LoadedDictAction.CLOSED):
                self._remove_annotation_roi(annotation_id)
            else:
                self._create_or_update_annotation_roi_for_annotation_id(annotation_id)
        except Exception as e:
            log.exception(f"Error in AnnotationROIManager on_annotation_changed: {e}")
