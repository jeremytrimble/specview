from __future__ import annotations

from dataclasses import dataclass
import typing
from pathlib import Path
import enum
import numpy as np
import sigmf
#from sigmf.sigmffile import dtype_info as sigmf_dtype_info
from .sigmf_util import get_annotation_time_bound_relative_to_current_capture, sigmf_type_to_numpy_dtype
from .monotonic_axis import MonotonicAxis
from PyQt6.QtWidgets import QApplication

from .chunkwise_compute import (
    TimeDomainChunkwiseComputedArray,
    TimeDomainComputationSpec,
    RawTimeDomainComputationSpec, 

    FrequencyDomainChunkwiseComputedArray,
    FrequencyDomainComputationSpec, DEFAULT_FREQ_COMPUTATION_SPEC
)

import logging
log = logging.getLogger("loaded_file_mgmt")

import random
rnd = random.Random(42)


# These ids are unique within one run of the application, for internal use only
# Type aliases:
FileID = str
CaptureID = str
AnnotationID = str

class MalformedSigMFFile(ValueError):
    pass

class LoadedThingCounter:
    def __init__(self, prefix:str):
        self._counter:int =0
        self._prefix = prefix
    def get_next_id(self) -> str:
        rv = f"{self._prefix}{self._counter:03d}"
        self._counter += 1
        return rv

loaded_file_counter = LoadedThingCounter(prefix="fid")
loaded_capture_counter = LoadedThingCounter(prefix="cap")
loaded_annotation_counter = LoadedThingCounter(prefix="ann")

del LoadedThingCounter

class LoadedFileAction(enum.Enum):
    OPENED = "opened"
    CLOSED = "closed"
    # TODO: should "saved" be an action here?

class LoadedDictAction(enum.Enum):
    LOADED = "loaded"       # the annotation was loaded from the file initially
    ADDED = "added"         # the annotation was added (newly created)
    MODIFIED = "modified"   # the annotation was changed
    DELETED = "deleted"     # the annotation was deleted (removed from the parent file)
    CLOSED = "closed"       # the parent file was closed, so this annotation is no longer valid

    def __str__(self):
        return self.value

    def __repr__(self):
        return f"LoadedDictAction.{self.value.upper()}"

# TODO: put this somewhere
#        annotation_dict = self._id_to_annotation.get(annotation_id)
#        if annotation_dict is not None:
#            app_state: AppState = QApplication.instance().app_state
#            app_state.annotation_changed.emit(self._open_file_id, annotation_dict, action)


class LoadedFilesCollection:
    """
    A class representing a collection of loaded SigMF files, their LoadedCaptureDict, and LoadedAnnotationDict objects.
    """
    def __init__(self):

        # mapping of all known file IDs to their LoadedFile objects
        #  this mapping is maintained by this LoadedFilesCollection class
        self._fileid_to_loadedfile: dict[FileID, LoadedFile] = {}

        # mapping of all known capture IDs to their LoadedCaptureDict objects
        #  this mapping is maintained by the LoadedFile class
        self._capture_id_to_capture: dict[CaptureID, LoadedCaptureDict] = {}

        # mapping of all known annotation IDs to their LoadedAnnotationDict objects
        #  this mapping is maintained by the LoadedFile class
        self._annotation_id_to_annotations: dict[AnnotationID, LoadedAnnotationDict] = {}

        self._annotation_changed_cb: typing.Callable[[AnnotationID, LoadedDictAction], None]|None = None
        self._file_load_or_unload_cb: typing.Callable[[FileID, LoadedFileAction], None]|None = None

        self._file_saved_status_changed_cb: typing.Callable[[FileID, bool], None]|None = None

    def set_file_saved_status_changed(self, cb: typing.Callable[[FileID, bool], None]) -> None:
        self._file_saved_status_changed_cb = cb

    def set_file_load_or_unload_callback(self, cb: typing.Callable[[FileID, LoadedFileAction], None]) -> None:
        self._file_load_or_unload_cb = cb

    def set_annotation_changed_callback(self, cb: typing.Callable[[AnnotationID, LoadedDictAction], None]) -> None:
        self._annotation_changed_cb = cb

    def load_file(self, file_path: Path) -> LoadedFile | None:

        sigmf_files = resolve_sigmf_filename(file_path)

        # Check if file is already loaded
        for loaded_file in self.loaded_file_dict.values():
            if loaded_file.sigmf_data_file_path == sigmf_files.data_filename:
                log.info(f"File already loaded: {file_path}")
                return None

        loaded_file = LoadedFile(file_path=file_path, parent_loaded_files=self)
        self._fileid_to_loadedfile[loaded_file._file_id] = loaded_file
        if self._file_load_or_unload_cb is not None:
            self._file_load_or_unload_cb(loaded_file._file_id, LoadedFileAction.OPENED)
        return loaded_file

    @property
    def loaded_file_dict(self):     # TODO: remove me in favor of get_loaded_file_from_id()
        return self._fileid_to_loadedfile

    def get_loaded_file_from_id(self, loaded_file_id:FileID) -> LoadedFile|None:
        return self._fileid_to_loadedfile.get(loaded_file_id)

    def get_capture_from_id(self, capture_id:CaptureID) -> LoadedCaptureDict|None:
        return self._capture_id_to_capture.get(capture_id)

    def get_annotation_from_id(self, annotation_id:AnnotationID) -> LoadedAnnotationDict|None:
        return self._annotation_id_to_annotations.get(annotation_id)

    def _on_child_annotation_changed(self, annotation_id:AnnotationID, action:LoadedDictAction) -> None:
        if self._annotation_changed_cb is not None:
            self._annotation_changed_cb(annotation_id, action)

    def _on_loaded_file_changed(self, fileid: FileID, is_saved: bool) -> None:
        if self._file_saved_status_changed_cb is not None:
            self._file_saved_status_changed_cb(fileid, is_saved)

    def close_file(self, fileid: FileID):
        if fileid in self._fileid_to_loadedfile:
            loaded_file = self._fileid_to_loadedfile[fileid]
            loaded_file.close()
            del self._fileid_to_loadedfile[fileid]
            if self._file_load_or_unload_cb is not None:
                self._file_load_or_unload_cb(fileid, LoadedFileAction.CLOSED)
        else:
            # TODO: should this raise an exception or just do nothing?
            raise ValueError(f"File ID {fileid} not found in loaded files.")

class LoadedAnnotationDict(dict):
    """
    A dictionary-like object that represents an annotation loaded from a SigMF file.
    It is tied to a parent LoadedFile and notifies it when the annotation is modified.
    It also provides a method to create a new annotation dictionary, which is
    not intended to be used directly, but rather through the LoadedFile's
    add_annotation method which returns an instance of this class.
    """
    @classmethod
    def create_annotation_dict(cls, parent_loadedfile: LoadedFile, annotation_id:AnnotationID, annotation_content:dict) -> LoadedAnnotationDict:
        rv = cls()
        # TODO: there is probably a more guaranteed-correct way to "wrap" a dictionary 
        rv._underlying_dict = annotation_content
        rv._parent_loadedfile = parent_loadedfile
        rv._annotation_id = annotation_id
        rv._deactivated = False
        rv._is_updating = False  # Instance-level flag to prevent recursive updates
        rv._visible = True  # Annotations are visible by default
        return rv

    @property
    def parent_loadedfile(self) -> LoadedFile:
        return self._parent_loadedfile
    
    def _notify_parent_that_i_was_modified(self):
        if self._parent_loadedfile is not None:
            if not self._is_updating:
                self._is_updating = True
                try:
                    self._parent_loadedfile._on_child_annotation_changed(self._annotation_id, LoadedDictAction.MODIFIED)
                finally:
                    self._is_updating = False

    def __iter__(self):
        return self._underlying_dict.__iter__()

    def __len__(self):
        return self._underlying_dict.__len__()

    def __contains__(self, key):
        return key in self._underlying_dict

    def keys(self):
        return self._underlying_dict.keys()

    def values(self):
        return self._underlying_dict.values()

    def items(self):
        return self._underlying_dict.items()

    def get(self, key, default=None):
        return self._underlying_dict.get(key, default)

    def __getitem__(self, key):
        return self._underlying_dict.__getitem__(key)

    def __setitem__(self, key, value):
        rv = self._underlying_dict.__setitem__(key, value)
        self._notify_parent_that_i_was_modified()
        return rv
    
    def __delitem__(self, key):
        rv = self._underlying_dict.__delitem__(key)
        self._notify_parent_that_i_was_modified()
        return rv   

    def update(self, *args, **kwargs):
        rv = self._underlying_dict.update(*args, **kwargs)
        self._notify_parent_that_i_was_modified()
        return rv

    def pop(self, key, *args):
        rv = self._underlying_dict.pop(key, *args)
        self._notify_parent_that_i_was_modified()
        return rv
    
    def clear(self):
        rv = self._underlying_dict.clear()
        self._notify_parent_that_i_was_modified()
        return rv   

    def delete_annotation(self):
        if not self._deactivated:
            self._parent_loadedfile._on_child_annotation_changed(self._annotation_id, LoadedDictAction.DELETED)
            self._parent_loadedfile = None
        self._deactivated = True

    def close_annotation(self):
        if not self._deactivated:
            self._parent_loadedfile._on_child_annotation_changed(self._annotation_id, LoadedDictAction.CLOSED)
            self._parent_loadedfile = None
        self._deactivated = True

    @property
    def annotation_id(self) -> AnnotationID:
        return self._annotation_id

    @property
    def visible(self) -> bool:
        """
        Get the visibility state of this annotation.
        
        Returns:
            True if the annotation should be visible in the UI, False otherwise
        """
        return self._visible
    
    @visible.setter
    def visible(self, value: bool) -> None:
        """
        Set the visibility state of this annotation.
        
        Args:
            value: True to make the annotation visible, False to hide it
        """
        if self._visible != value:
            self._visible = value
            # Notify parent that the annotation has been modified
            # This will trigger UI updates without changing the underlying dictionary
            # Note: this could be emitted as a different type of signal in the
            # future if we want to separate content changes from visibility
            # changes
            self._notify_parent_that_i_was_modified()

    def get_frequency_range_Hz(self) -> tuple[float,float]|None:
        f_lo = self.get(sigmf.SigMFFile.FLO_KEY)
        f_hi = self.get(sigmf.SigMFFile.FHI_KEY)
        if f_lo is not None and f_hi is not None:
            return (float(f_lo), float(f_hi))
        else:
            return None
    
    def get_time_range_relative_to_capture(self, capture_id:CaptureID) -> tuple[float,float]|None:
        parent: LoadedFile = self._parent_loadedfile
        if capture := parent._capture_id_to_capture.get(capture_id):
            return get_annotation_time_bound_relative_to_current_capture(self, capture.capture_idx_in_file, parent.sigmf_file)
        return None

    def get_time_axis_for_capture(self, capture_id:CaptureID) -> MonotonicAxis:
        """Returns a MonotonicAxis that maps sample indexes to floating-point time in seconds 
        relative to the specified capture.
        
        Args:
            capture_id: The ID of the capture to use as the time reference
            
        Returns:
            MonotonicAxis: An axis that converts sample indexes to time in seconds
        """
        from .monotonic_axis import MonotonicAxis
        parent: LoadedFile = self._parent_loadedfile

        if not capture_id in parent._capture_id_to_capture:
            raise ValueError(f"Capture ID {capture_id} not found in parent LoadedFile {parent.file_id}")

        capture = parent._capture_id_to_capture[capture_id] # TODO: make this not access a private field of LoadedFile

        return capture.time_axis

    @property
    def label(self) -> str:
        label = self.get(sigmf.SigMFFile.LABEL_KEY)
        if label is None:
            return ""
        else:
            return str(label)

    # Time-related getters and setters (methods since they require capture_id parameter)
    def get_start_time_sec(self, capture_id: CaptureID) -> float | None:
        """
        Get the start time in seconds since the beginning of the specified capture.
        
        Args:
            capture_id: The ID of the capture to use as the time reference
            
        Returns:
            Start time in seconds, or None if the annotation is not in the capture
        """
        time_range = self.get_time_range_relative_to_capture(capture_id)
        if time_range is None:
            return None
        return time_range[0]
    
    def set_start_time_sec(self, capture_id: CaptureID, start_time_sec: float) -> None:
        """
        Set the start time in seconds since the beginning of the specified capture.
        This updates the START_INDEX_KEY in the annotation dictionary.
        
        Args:
            capture_id: The ID of the capture to use as the time reference
            start_time_sec: The start time in seconds
        """
        parent: LoadedFile = self._parent_loadedfile
        capture = parent._capture_id_to_capture[capture_id]

        # Update the dictionary (this will trigger notification)
        self[sigmf.SigMFFile.START_INDEX_KEY] = capture.time_axis.idx_nearest_to_value(start_time_sec)
    
    def get_end_time_sec(self, capture_id: CaptureID) -> float | None:
        """
        Get the end time in seconds since the beginning of the specified capture.
        
        Args:
            capture_id: The ID of the capture to use as the time reference
            
        Returns:
            End time in seconds, or None if the annotation is not in the capture
        """
        time_range = self.get_time_range_relative_to_capture(capture_id)
        if time_range is None:
            return None
        return time_range[1]
    
    def set_end_time_sec(self, capture_id: CaptureID, end_time_sec: float) -> None:
        """
        Set the end time in seconds since the beginning of the specified capture.
        This updates the LENGTH_INDEX_KEY in the annotation dictionary.
        
        Args:
            capture_id: The ID of the capture to use as the time reference
            end_time_sec: The end time in seconds
        """
        parent: LoadedFile = self._parent_loadedfile
        capture = parent._capture_id_to_capture[capture_id]

        # Get sample rate
        sample_rate = parent.sigmf_file.get_global_field(sigmf.SigMFFile.SAMPLE_RATE_KEY)
        if sample_rate is None or sample_rate <= 0:
            raise ValueError("Invalid or missing sample rate in parent file")
        
        # Get current start index
        start_index = self.get(sigmf.SigMFFile.START_INDEX_KEY)
        if start_index is None:
            raise ValueError("Cannot set end time without a start index")
        
        # Convert end time to sample index and calculate length
        end_sample_in_capture = int(end_time_sec * sample_rate)
        end_index = capture.start_sample_idx + end_sample_in_capture
        length = end_index - start_index
        
        if length <= 0:
            raise ValueError("End time must be greater than start time")
        
        # Update the dictionary (this will trigger notification)
        self[sigmf.SigMFFile.LENGTH_INDEX_KEY] = length
    
    # Duration getter and setter (property)
    @property
    def duration_sec(self) -> float | None:
        """
        Get the duration in seconds.
        
        Returns:
            Duration in seconds, or None if LENGTH_INDEX_KEY is not set
        """
        length_samples = self.get(sigmf.SigMFFile.LENGTH_INDEX_KEY)
        if length_samples is None:
            return None
        
        parent: LoadedFile = self._parent_loadedfile
        sample_rate = parent.sigmf_file.get_global_field(sigmf.SigMFFile.SAMPLE_RATE_KEY)
        if sample_rate is None or sample_rate <= 0:
            raise ValueError("Invalid or missing sample rate in parent file")
        
        return length_samples / sample_rate
    
    @duration_sec.setter
    def duration_sec(self, duration_sec: float) -> None:
        """
        Set the duration in seconds.
        This updates the LENGTH_INDEX_KEY in the annotation dictionary.
        
        Args:
            duration_sec: The duration in seconds
        """
        if duration_sec <= 0:
            raise ValueError("Duration must be positive")
        
        parent: LoadedFile = self._parent_loadedfile
        sample_rate = parent.sigmf_file.get_global_field(sigmf.SigMFFile.SAMPLE_RATE_KEY)
        if sample_rate is None or sample_rate <= 0:
            raise ValueError("Invalid or missing sample rate in parent file")
        
        # Convert duration to samples
        length_samples = int(duration_sec * sample_rate)
        
        # Update the dictionary (this will trigger notification)
        self[sigmf.SigMFFile.LENGTH_INDEX_KEY] = length_samples
    
    # Center frequency getter and setter (property)
    @property
    def center_frequency_Hz(self) -> float | None:
        """
        Get the center frequency in Hz.
        
        Returns:
            Center frequency in Hz, or None if FLO_KEY or FHI_KEY is not set
        """
        f_lo = self.get(sigmf.SigMFFile.FLO_KEY)
        f_hi = self.get(sigmf.SigMFFile.FHI_KEY)
        
        if f_lo is None or f_hi is None:
            return None
        
        return (f_lo + f_hi) / 2.0
    
    @center_frequency_Hz.setter
    def center_frequency_Hz(self, center_freq_Hz: float) -> None:
        """
        Set the center frequency in Hz.
        This updates both FLO_KEY and FHI_KEY based on the current bandwidth.
        If bandwidth is not set, it defaults to 0 (making FLO_KEY = FHI_KEY = center_freq_Hz).
        
        Args:
            center_freq_Hz: The center frequency in Hz
        """
        # Get current bandwidth (if it exists)
        current_bandwidth = self.bandwidth_Hz
        if current_bandwidth is None:
            current_bandwidth = 0.0
        
        half_bw = current_bandwidth / 2.0
        
        # Update FLO and FHI (this will trigger notification for each update)
        self[sigmf.SigMFFile.FLO_KEY] = center_freq_Hz - half_bw
        self[sigmf.SigMFFile.FHI_KEY] = center_freq_Hz + half_bw

    
    @property
    def low_frequency_Hz(self) -> float | None:
        return self.get(sigmf.SigMFFile.FLO_KEY)
    @low_frequency_Hz.setter
    def low_frequency_Hz(self, low_freq_Hz: float) -> None:
        self[sigmf.SigMFFile.FLO_KEY] = low_freq_Hz

    @property
    def high_frequency_Hz(self) -> float | None:
        return self.get(sigmf.SigMFFile.FHI_KEY)
    @high_frequency_Hz.setter
    def high_frequency_Hz(self, hi_freq_Hz: float) -> None:
        self[sigmf.SigMFFile.FHI_KEY] = hi_freq_Hz

    
    # Bandwidth getter and setter (property)
    @property
    def bandwidth_Hz(self) -> float | None:
        """
        Get the bandwidth in Hz.
        
        Returns:
            Bandwidth in Hz, or None if FLO_KEY or FHI_KEY is not set
        """
        f_lo = self.get(sigmf.SigMFFile.FLO_KEY)
        f_hi = self.get(sigmf.SigMFFile.FHI_KEY)
        
        if f_lo is None or f_hi is None:
            return None
        
        return f_hi - f_lo
    
    @bandwidth_Hz.setter
    def bandwidth_Hz(self, bandwidth_Hz: float) -> None:
        """
        Set the bandwidth in Hz.
        This updates both FLO_KEY and FHI_KEY based on the current center frequency.
        If center frequency is not set, this will raise a ValueError.
        
        Args:
            bandwidth_Hz: The bandwidth in Hz
        """
        if bandwidth_Hz < 0:
            raise ValueError("Bandwidth must be non-negative")
        
        # Get current center frequency
        current_center = self.center_frequency_Hz
        if current_center is None:
            raise ValueError("Cannot set bandwidth without a center frequency (FLO_KEY and FHI_KEY must be set)")
        
        half_bw = bandwidth_Hz / 2.0
        
        # Update FLO and FHI (this will trigger notification for each update)
        self[sigmf.SigMFFile.FLO_KEY] = current_center - half_bw
        self[sigmf.SigMFFile.FHI_KEY] = current_center + half_bw

@dataclass
class SigMFFilenames:
    meta_filename: Path
    data_filename: Path

def resolve_sigmf_filename(file_path: Path) -> SigMFFilenames:
    sigmf_files_dict = sigmf.sigmffile.get_sigmf_filenames(file_path)
    data_file_path: Path = Path(sigmf_files_dict['data_fn']).resolve()
    meta_file_path: Path = Path(sigmf_files_dict['meta_fn']).resolve()
    return SigMFFilenames(meta_filename=meta_file_path, data_filename=data_file_path)

class LoadedFile:
    """
    A class representing a loaded SigMF file.
    It contains the file path, the SigMFFile object, and a dictionary of annotations.
    It also provides methods to add annotations and get the annotations.
    It emits signals when annotations are added, modified, or deleted.
    """
    def __init__(self, file_path: Path, parent_loaded_files: LoadedFilesCollection):
        # Note: file_path is the path to the .sigmf-meta file
        # sigmf_file is the SigMFFile object loaded from that file
        self._parent_loaded_files = parent_loaded_files

        # TODO: change this if we decide to support collections or archives
        sigmf_files = resolve_sigmf_filename(file_path)
        self._sigmf_data_file_path: Path = sigmf_files.data_filename
        self._sigmf_meta_file_path: Path = sigmf_files.meta_filename

        if not self._sigmf_data_file_path.exists():
            raise FileNotFoundError(f"SigMF data file not found: {self._sigmf_data_file_path}")
        if not self._sigmf_meta_file_path.exists():
            raise FileNotFoundError(f"SigMF meta file not found: {self._sigmf_meta_file_path}")

        # TODO: checksum computation is skipped to improve load time -- verify checksum in background?
        returned_file = sigmf.sigmffile.fromfile(self._sigmf_data_file_path, skip_checksum=True)
        assert isinstance(returned_file, sigmf.SigMFFile), "Loaded SigMF file is not a SigMFFile instance"
        self._sigmf_file = returned_file

        # Set initial saved state.
        # Note: Don't modify this variable directly, use _set_state_to_saved/unsaved methods instead.
        self._has_unsaved_changes = False

        self._enforce_sigmf_metadata_invariants()

        # "CCAs": Chunkwise Computed Arrays
        self._time_ccas: dict[TimeDomainComputationSpec, TimeDomainChunkwiseComputedArray] = {}
        self._freq_ccas: dict[FrequencyDomainComputationSpec, FrequencyDomainChunkwiseComputedArray] = {}

        # This is the path to the .sigmf-data file
        self._file_id: FileID = loaded_file_counter.get_next_id()

        self._capture_idx_to_capture: dict[int, LoadedCaptureDict] = {}
        self._capture_id_to_capture: dict[CaptureID, LoadedCaptureDict] = {}
        self._annotation_id_to_annotation: dict[AnnotationID, LoadedAnnotationDict] = {}

        for cap_idx, cap_dict in enumerate(self._sigmf_file.get_captures()):
            capture_id = self._get_next_capture_id()
            lcd = LoadedCaptureDict.create_capture_dict(parent_loadedfile=self, capture_idx=cap_idx, capture_id=capture_id, capture_content=cap_dict)
            self._capture_id_to_capture[capture_id] = lcd
            self._capture_idx_to_capture[cap_idx] = lcd
            self._parent_loaded_files._capture_id_to_capture[capture_id] = lcd  # store in the global mapping

        for annotation_dict in self._sigmf_file.get_annotations():
            annotation_id = self._get_next_annotation_id()
            lad = LoadedAnnotationDict.create_annotation_dict(parent_loadedfile=self, annotation_id=annotation_id, annotation_content=annotation_dict)
            self._annotation_id_to_annotation[annotation_id] = lad
            self._parent_loaded_files._annotation_id_to_annotations[annotation_id] = lad  # store in the global mapping

        for annotation_id in self._annotation_id_to_annotation:
            self._on_child_annotation_changed(annotation_id, LoadedDictAction.LOADED)

    def _enforce_sigmf_metadata_invariants(self):
        smf: sigmf.sigmffile.SigMFFile = self._sigmf_file

        #if smf.get_global_field(sigmf.SigMFFile.SAMPLE_RATE_KEY) is None:
        #    raise MalformedSigMFFile("SigMF file is missing required global field: sample_rate")

        for capture_idx, capture in enumerate(smf.get_captures()):
            if sigmf.SigMFFile.FREQUENCY_KEY not in capture:
                log.warning(f"Capture index {capture_idx} is missing required field: frequency. Setting to 0 Hz.")
                capture[sigmf.SigMFFile.FREQUENCY_KEY] = 0.0  # default to 0 Hz if missing

    def _set_state_to_unsaved(self):
        previous_unsaved = self._has_unsaved_changes
        self._has_unsaved_changes = True
        if previous_unsaved != self._has_unsaved_changes:
            self._parent_loaded_files._on_loaded_file_changed(self.file_id, not self._has_unsaved_changes)

    def _set_state_to_saved(self):
        previous_unsaved = self._has_unsaved_changes
        self._has_unsaved_changes = False
        if previous_unsaved != self._has_unsaved_changes:
            self._parent_loaded_files._on_loaded_file_changed(self.file_id, not self._has_unsaved_changes)

    @property
    def sigmf_file(self) -> sigmf.SigMFFile:
        return self._sigmf_file

    @property
    def sample_rate_Hz(self) -> float:
        # TODO: make this used everywhere instead of accessing sigmf_file directly
        rv = self._sigmf_file.get_global_field(sigmf.SigMFFile.SAMPLE_RATE_KEY)
        if rv is None:
            raise ValueError("Sample rate not found in SigMF file") # we are super broken if this happens
        return rv

    @property
    def num_channels(self) -> int:
        # TODO: make this used everywhere instead of accessing sigmf_file directly
        return self._sigmf_file.get_global_field(sigmf.SigMFFile.NUM_CHANNELS_KEY, 1)

    @property
    def has_unsaved_changes(self) -> bool:
        return self._has_unsaved_changes

    def _sort_annotations_in_sigmf_file(self):
        annotations_list : list[dict] = self._sigmf_file.get_annotations()
        annotations_list.sort(key=lambda ann: ann.get(sigmf.SigMFFile.START_INDEX_KEY, 0))

    def save(self):
        self._sort_annotations_in_sigmf_file()
        self._sigmf_file.tofile(self.sigmf_meta_file_path)
        self._set_state_to_saved()

    # TODO: support save-as?

    @property
    def sigmf_meta_file_path(self) -> Path:
        return self._sigmf_meta_file_path

    @property
    def sigmf_data_file_path(self) -> Path:
        return self._sigmf_data_file_path

    @property
    def file_id(self) -> FileID:
        return self._file_id

    @property
    def num_captures(self) -> int:
        return len(self._capture_idx_to_capture)

    def _on_child_annotation_changed(self, annotation_id:AnnotationID, action:LoadedDictAction) -> None:
        """
        Called when one of our children annotations has changed.
        Emits the annotation_changed signal with the file ID and the set of changed annotations.
        """
        self._parent_loaded_files._on_child_annotation_changed(annotation_id, action)
        if action in (LoadedDictAction.ADDED, LoadedDictAction.DELETED, LoadedDictAction.MODIFIED):
            self._set_state_to_unsaved()
        
        if action in (LoadedDictAction.DELETED, LoadedDictAction.CLOSED):
            log.debug(f"Removing annotation ID {annotation_id} from LoadedFile {self.file_id} due to action {action}")
            self._parent_loaded_files._annotation_id_to_annotations.pop(annotation_id, None) # remove from the global mapping
            annotation = self._annotation_id_to_annotation.pop(annotation_id, None) # remove from our own mapping
            if annotation is not None:
                self._remove_annotation_from_sigmf_file(annotation)

    def _remove_annotation_from_sigmf_file(self, annotation: LoadedAnnotationDict) -> None:
        annotations_list : list[dict] = self._sigmf_file.get_annotations()
        idx = annotations_list.index(annotation._underlying_dict)
        if idx >= 0:
            log.debug(f"Removing annotation at index {idx} from SigMFFile for LoadedFile {self.file_id}")
            # deletes from the list held by the SigMFFile in-place, there is no
            # need to re-set the annotations list
            del annotations_list[idx]   


    def _get_next_capture_id(self) -> CaptureID:
        """
        Returns the next capture ID, in a global namespace.
        """
        return loaded_capture_counter.get_next_id()

    def _get_next_annotation_id(self) -> AnnotationID:
        """
        Returns the next annotation ID, in a global namespace.
        """
        return loaded_annotation_counter.get_next_id()

    def _add_and_return_annotation_dict(self, start_index:int, length:int|None=None, metadata:dict|None=None) -> dict:
        # HACK: sigmf doesn't return the annotation dict back to us, so we have
        # to "mark" it in a way that we can find after insertion and sorting.
        # Longer-term, maybe we need to write our own sigmf file implementation...

        INSERTION_MARKER_KEY = "_specview_insertion_marker"
        INSERTION_MARKER_VALUE = rnd.randint(0,1000000)
        metadata = dict(metadata)
        metadata[INSERTION_MARKER_KEY] = INSERTION_MARKER_VALUE
        self._sigmf_file.add_annotation(start_index=start_index, length=length, metadata=metadata)

        annotation_list = self._sigmf_file.get_annotations()
        annotation_dict = None
        for ad in annotation_list:
            if ad.get(INSERTION_MARKER_KEY) == INSERTION_MARKER_VALUE:
                # found it
                del ad[INSERTION_MARKER_KEY]
                annotation_dict = ad
                break
        if annotation_dict is None:
            # this shouldn't happen
            raise ValueError("Failed to find newly added annotation in SigMF file.")
        return annotation_dict

    def add_annotation(self, start_index:int, length:int|None=None, metadata:dict|None=None) -> LoadedAnnotationDict:
        """
        Add a new annotation to this file.
        Returns the AnnotationDict for the new annotation.
        """
        annotation_dict = self._add_and_return_annotation_dict(start_index=start_index, length=length, metadata=metadata)

        annotation_id = self._get_next_annotation_id()
        new_annotation = LoadedAnnotationDict.create_annotation_dict(self, annotation_id, annotation_dict)
        self._annotation_id_to_annotation[annotation_id] = new_annotation
        self._parent_loaded_files._annotation_id_to_annotations[annotation_id] = new_annotation  # store in the global mapping
        self._set_state_to_unsaved()
        self._on_child_annotation_changed(annotation_id, LoadedDictAction.ADDED)
        return new_annotation

    def get_annotations_dict(self) -> dict[str, LoadedAnnotationDict]:
        """
        Returns a dictionary of annotations for this file.
        The keys are the annotation IDs and the values are the LoadedAnnotationDict objects.
        """
        return dict(self._annotation_id_to_annotation)

    def _close_annotations(self) -> None:
        all_annotations = list(self._annotation_id_to_annotation.values())
        for ad in all_annotations:
            ad.close_annotation()

    def close(self) -> None:
        self._close_annotations()
        self._sigmf_file = None
        for cap in self._capture_id_to_capture.values():
            del self._parent_loaded_files._capture_id_to_capture[cap.capture_id]
        self._capture_id_to_capture.clear()

    def get_time_chunkwise_computed_array(self, comp_spec: TimeDomainComputationSpec = RawTimeDomainComputationSpec()) -> TimeDomainChunkwiseComputedArray:
        if comp_spec not in self._time_ccas:
            sample_dtype: np.dtype = sigmf_type_to_numpy_dtype( self.sigmf_file.get_global_info()[sigmf.SigMFFile.DATATYPE_KEY] ) 
            num_channels = self.sigmf_file.get_global_field(sigmf.SigMFFile.NUM_CHANNELS_KEY, 1 )

            cca = TimeDomainChunkwiseComputedArray(
                signal_file = self.sigmf_data_file_path,
                signal_file_datatype = sample_dtype,
                comp_spec= comp_spec,
                num_channels=num_channels,
            )
            self._time_ccas[comp_spec] = cca

        return self._time_ccas[comp_spec]

    def get_freq_chunkwise_computed_array(self, selected_channel:int, comp_spec: FrequencyDomainComputationSpec | None ) -> FrequencyDomainChunkwiseComputedArray:
        if comp_spec is None:
            # Get config from AppState
            app_state = QApplication.instance().app_state
            comp_spec = app_state.get_freq_domain_computation_spec()
            
        key = (comp_spec.model_dump_json(), selected_channel)

        if key not in self._freq_ccas:
            sample_dtype: np.dtype = sigmf_type_to_numpy_dtype( self.sigmf_file.get_global_info()[sigmf.SigMFFile.DATATYPE_KEY] ) 
            sample_rate_Hz: float = self.sigmf_file.get_global_field(sigmf.SigMFFile.SAMPLE_RATE_KEY)
            num_channels = self.sigmf_file.get_global_field(sigmf.SigMFFile.NUM_CHANNELS_KEY, 1 )

            cca = FrequencyDomainChunkwiseComputedArray(
                signal_file= self.sigmf_data_file_path,
                signal_file_datatype= sample_dtype,
                comp_spec= comp_spec,
                num_input_channels= num_channels,
                target_output_channel = selected_channel,
                sample_rate_Hz= sample_rate_Hz,
            )
            self._freq_ccas[key] = cca

        return self._freq_ccas[key]

class LoadedCaptureDict(dict):
    @classmethod
    def create_capture_dict(cls, parent_loadedfile: LoadedFile, capture_idx:int, capture_id:CaptureID, capture_content:dict) -> LoadedCaptureDict:
        # TODO: don't instantiate a second dictionary -- rather, wrap the existing dictionary with methods that access the underlying
        rv = cls(capture_content)
        rv._parent_loadedfile = parent_loadedfile
        rv._capture_idx = capture_idx
        rv._capture_id = capture_id
        return rv

    @property
    def parent_loadedfile(self) -> LoadedFile:
        return self._parent_loadedfile

    @property
    def capture_id(self) -> CaptureID:
        return self._capture_id

    @property
    def capture_idx_in_file(self) -> int:
        return self._capture_idx

    @property
    def start_sample_idx(self) -> int:
        """
        Returns the first sample index of this capture within the parent file.
        """
        return self[sigmf.SigMFFile.START_INDEX_KEY]

    @property
    def num_samples(self) -> int:
        """
        Returns the number of samples in this capture.
        """
        total_samples_in_file = self.parent_loadedfile.sigmf_file.sample_count

        next_capture = self.parent_loadedfile._capture_idx_to_capture.get(self.capture_idx_in_file + 1)

        if next_capture is not None:
            return next_capture[sigmf.SigMFFile.START_INDEX_KEY] - self[sigmf.SigMFFile.START_INDEX_KEY]
        else:
            return total_samples_in_file - self[sigmf.SigMFFile.START_INDEX_KEY]

    @property
    def time_axis(self) -> MonotonicAxis:
        """
        Returns a MonotonicAxis that maps sample indexes to floating-point time in seconds
        relative to this capture.
        """
        parent: LoadedFile = self._parent_loadedfile

        sample_rate = parent.sigmf_file.get_global_field(sigmf.SigMFFile.SAMPLE_RATE_KEY, 0.0)
        if sample_rate <= 0.0:
            raise ValueError(f"Invalid or missing sample rate in capture {self.capture_id}")

        return MonotonicAxis(slope=1.0/sample_rate, num_points=self.num_samples, intercept=self.start_sample_idx)

    @property
    def center_freq_Hz(self) -> float:
        return self.get(sigmf.SigMFFile.FREQUENCY_KEY, 0.0)

    @property
    def duration_sec(self) -> float:
        return self.num_samples / self.parent_loadedfile.sample_rate_Hz