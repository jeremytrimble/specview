from typing import Union, TypeVar, Generic, Dict
from dataclasses import dataclass
import logging
from PyQt5.QtWidgets import QApplication
import pyqtgraph as pg
import sigmf

from .labeled_rect_roi import LabeledRectROI
from .labeled_linear_region_item import LabeledLinearRegionItem
from .loaded_file_mgmt import LoadedAnnotationDict, LoadedDictAction, AnnotationID, CaptureID
from .app_state import AppState
from .ui_constants import ANNOTATION_ROI_COLOR
import enum

log = logging.getLogger(__name__)

ROIType = TypeVar('ROIType', LabeledRectROI, LabeledLinearRegionItem)

@dataclass
class AnnotationROI(Generic[ROIType]):
    """Class to hold an annotation ROI and its metadata"""
    annotation_id: AnnotationID
    roi: ROIType

class ROIDimensions(enum.IntEnum):
    TIME = 1
    FREQUENCY = 2
    TIME_AND_FREQUENCY = 3

class AnnotationROIManager(Generic[ROIType]):
    """
    A class to manage annotation ROIs across different views (Waterfall, Time, Spectrum).
    This class abstracts the common functionality for handling annotations and their visual
    representation as ROIs.
    """
    
    def __init__(self, plot_widget: pg.PlotWidget, roi_dimensions:ROIDimensions):
        """
        Initialize the annotation ROI manager.
        
        Args:
            plot_widget: The plot widget where ROIs will be displayed
            roi_factory: A callable that creates a new ROI (either LabeledRectROI or LabeledLinearRegionItem)
            is_rectangular: True if using rectangular ROIs, False for linear ROIs
        """
        self._plot_widget = plot_widget
        self._roi_dimensions = roi_dimensions

        if self._roi_dimensions in (ROIDimensions.FREQUENCY, ROIDimensions.TIME):
            self._roi_factory = LabeledLinearRegionItem
        elif self._roi_dimensions == ROIDimensions.TIME_AND_FREQUENCY:
            self._roi_factory = LabeledRectROI
        else:
            raise ValueError(f"Unsupported ROI dimension type: {self._roi_dimensions}")

        self._annotation_rois: Dict[str, AnnotationROI[ROIType]] = {}
        self._current_capture_id: CaptureID = None
        self._roiPen = pg.mkPen(ANNOTATION_ROI_COLOR, width=3)
        
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
            
    def _on_rect_roi_changed(self, annotation_id: AnnotationID):
        """Handle changes to rectangular ROIs when they're dragged or resized."""
        aroi = self._annotation_rois[annotation_id]
        rect_roi = aroi.roi
        pos = rect_roi.pos()
        size = rect_roi.size()
        
        annotation_dict = self._get_app_state().get_annotation_by_id(annotation_id)
        if annotation_dict is not None:
            annotation_dict[sigmf.SigMFFile.FLO_KEY] = float(pos[0])
            annotation_dict[sigmf.SigMFFile.FHI_KEY] = float(pos[0] + size[0])

            # Update time range based on current capture
            time_axis = annotation_dict.get_time_axis_for_capture(self._current_capture_id)
            start_sample = time_axis.idx_nearest_to_value(float(pos[1]))
            #length = int(round(size[1] * time_axis._slope))  # Convert time duration to samples
            length = time_axis.idx_nearest_to_value(float(pos[1] + size[1])) - start_sample
            annotation_dict[sigmf.SigMFFile.START_INDEX_KEY] = start_sample
            annotation_dict[sigmf.SigMFFile.LENGTH_INDEX_KEY] = length

    def _on_linear_roi_changed(self, annotation_id: AnnotationID):
        """Handle changes to linear ROIs when they're dragged or resized."""
        aroi = self._annotation_rois[annotation_id]
        linear_roi = aroi.roi
        region = linear_roi.getRegion()
        
        annotation_dict = self._get_app_state().get_annotation_by_id(annotation_id)
        if annotation_dict is not None:
            if self._roi_dimensions == ROIDimensions.FREQUENCY:
                annotation_dict[sigmf.SigMFFile.FLO_KEY] = float(region[0])
                annotation_dict[sigmf.SigMFFile.FHI_KEY] = float(region[1])
            elif self._roi_dimensions == ROIDimensions.TIME:
                # Convert time range to sample indices
                time_axis = annotation_dict.get_time_axis_for_capture(self._current_capture_id)
                start_sample = time_axis.idx_nearest_to_value(float(region[0]))
                end_sample = time_axis.idx_nearest_to_value(float(region[1]))
                annotation_dict[sigmf.SigMFFile.START_INDEX_KEY] = start_sample
                annotation_dict[sigmf.SigMFFile.LENGTH_INDEX_KEY] = end_sample - start_sample

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

        if self._roi_dimensions == ROIDimensions.TIME_AND_FREQUENCY:
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
                    label_fill_color=ANNOTATION_ROI_COLOR,
                )
                self._plot_widget.addItem(roi, ignoreBounds=True)
                roi.sigRegionChanged.connect(lambda: self._on_rect_roi_changed(annotation_id))
                aroi = AnnotationROI(ad.annotation_id, roi)
                self._annotation_rois[ad.annotation_id] = aroi
            else:
                aroi = self._annotation_rois[ad.annotation_id]
                aroi.roi.setPos(pos=(freq_lo_Hz, time_lo_sec))
                aroi.roi.setSize(size=(freq_hi_Hz - freq_lo_Hz, time_hi_sec - time_lo_sec))
        else: # TIME or FREQUENCY
            # Handle linear ROI (Time or Spectrum view)
            if self._roi_dimensions == ROIDimensions.FREQUENCY:
                if freq_range_Hz is None:
                    return
                region = freq_range_Hz
            elif self._roi_dimensions == ROIDimensions.TIME:
                region = time_range_sec
            else:
                raise ValueError(f"Unsupported ROI dimension type: {self._roi_dimensions}")

            if ad.annotation_id not in self._annotation_rois:
                roi = self._roi_factory(
                    values=region,
                    label_text=ad.label,
                    label_text_color=(255, 255, 255),
                    label_fill_color=ANNOTATION_ROI_COLOR,
                )
                self._plot_widget.addItem(roi, ignoreBounds=True)
                roi.sigRegionChanged.connect(lambda: self._on_linear_roi_changed(annotation_id))
                aroi = AnnotationROI(ad.annotation_id, roi)
                self._annotation_rois[ad.annotation_id] = aroi
            else:
                aroi = self._annotation_rois[ad.annotation_id]
                aroi.roi.setRegion(region)

        # TODO: set colors appropriately
        #aroi.roi.setPen(self._roiPen)
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
