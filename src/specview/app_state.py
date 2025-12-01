from __future__ import annotations
from PyQt5.QtCore import QSize, Qt, QThread, pyqtSignal, QObject, QTimer, QSettings
from PyQt5.QtWidgets import QApplication, QMainWindow, QGridLayout, QWidget, QSlider, QLabel, QHBoxLayout, QVBoxLayout, QPushButton, QComboBox, QFileDialog, QMessageBox

from contextlib import contextmanager

import sigmf
from pathlib import Path
import dataclasses
from specview.loaded_file_mgmt import (
    LoadedAnnotationDict, LoadedCaptureDict, LoadedDictAction, LoadedFile, LoadedFileAction, LoadedFilesCollection, FileID, CaptureID, AnnotationID,
)
from specview.util import measure_runtime, first_from_dict
from specview.chunkwise_compute import FrequencyDomainComputationSpec, FFTLength
from specview.ui_constants import SETTINGS_ORGANIZATION, SETTINGS_APPLICATION
import numpy as np

import logging

import shutil

log = logging.getLogger("app_state")

#import enum
#class FreqSelectionType(enum.IntEnum):
#    SINGLE_FREQUENCY = 1
#    FREQUENCY_INTERVAL = 2

class GatedSignal:
    def __init__(self, sig: pyqtSignal):
        self._update_in_progress = False
        self._signal = sig

    def emit(self, *args, **kwargs):
        if self._update_in_progress:
            return
        else:
            self._update_in_progress = True
            self._signal.emit(*args, **kwargs)
            self._update_in_progress = False

    def connect(self, *args, **kwargs):
        self._signal.connect(*args, **kwargs)

class SignalGate:
    def __init__(self):
        self._update_in_progress = False

    @property
    def in_progress(self) -> bool:
        return self._update_in_progress

    @contextmanager
    def updating(self):
        self._update_in_progress = True
        try:
            yield
        finally:
            self._update_in_progress = False

def make_numpy_array_readonly(arr: np.ndarray) -> np.ndarray:
    """
    Convert a numpy array to a read-only array.
    """
    return arr.setflags(write=False)

class AppState(QObject):
    #_instance = None

    cursor_frequency_changed = pyqtSignal(float, name="cursor_frequency_changed")
    cursor_time_changed      = pyqtSignal(float, name="cursor_time_changed")
    fft_config_changed    = pyqtSignal(object, name="fft_config_changed")  # Emits FrequencyDomainComputationSpec

    frequency_interval_changed = pyqtSignal( [object], name="frequency_interval_changed") # tuple[float,float]|None
    time_interval_changed      = pyqtSignal( [object], name="time_interval_changed")    # tuple[float,float]|None

    loaded_files_changed = pyqtSignal([FileID, LoadedFileAction], name='loaded_files_changed') # emitted when a file is opened or closed
    file_save_status_changed = pyqtSignal([FileID, bool], name='file_save_status_changed') # emitted with (FileID, is_saved) when a file's save status changes (if True, the file is saved, if False, it has unsaved changes)
    selected_capture_changed = pyqtSignal([CaptureID], name='selected_capture_changed') # emitted with (CaptureID) when a capture is selected
    selected_channel_changed = pyqtSignal(int, name='selected_channel_changed') # emitted with channel_index when a channel is selected
    selected_annotation_changed = pyqtSignal([object], name='selected_annotation_changed') # emitted with (AnnotationID) or None when an annotation is selected

    annotation_changed = pyqtSignal([AnnotationID,LoadedDictAction], name='annotation_changed')
    recent_files_changed = pyqtSignal([], name='recent_files_changed')

    # Maximum number of recent files to track
    MAX_RECENT_FILES = 10

    def __init__(self, parent):
        super().__init__(parent)

        # Items of state:
        # - set of opened sigmf files

        # Load recent files from settings
        settings = QSettings(SETTINGS_ORGANIZATION, SETTINGS_APPLICATION)
        # TODO: should the type here be `str` or `list[str]`?
        self._recent_files = settings.value("recentFiles", [], type=str) or []

        self._fft_config = FrequencyDomainComputationSpec()

        # - selected sigmf file
        # - selected capture
        # - selected annotation
        # - selected channel, or channel math

        # - plot range selections/focus times
        # - 

        # TODO: add getters for these
        self._cursor_frequency: float = 0.0
        self._cursor_time: float = 0.0

        self._time_interval: tuple[float,float]|None = None
        self._frequency_interval: tuple[float,float]|None = None

        self._selected_capture: CaptureID|None = None
        self._selected_annotation: AnnotationID|None = None

        self._cursor_frequency_gate = SignalGate()
        self._cursor_time_gate = SignalGate()
        self._time_interval_gate = SignalGate()
        self._frequency_interval_gate = SignalGate()

        self._loaded_files = LoadedFilesCollection()
        self._loaded_files.set_file_load_or_unload_callback(self._on_file_load_or_unload)
        self._loaded_files.set_annotation_changed_callback(self._on_annotation_changed)
        self._loaded_files.set_file_saved_status_changed(self._on_file_saved_status_changed)

    def _on_file_saved_status_changed(self, fileid:FileID, is_saved:bool):
        self.file_save_status_changed.emit(fileid, is_saved)

    def _on_file_load_or_unload(self, fileid:FileID, action:LoadedFileAction):
        self.loaded_files_changed.emit(fileid, action)

    def _on_annotation_changed(self, annotation_id:AnnotationID, action:LoadedDictAction):
        self.annotation_changed.emit(annotation_id, action)

    def get_capture_by_id(self, capture_id:CaptureID) -> LoadedCaptureDict|None:
        return self._loaded_files.get_capture_from_id(capture_id)

    def get_annotation_by_id(self, annotation_id:AnnotationID) -> LoadedAnnotationDict|None:
        return self._loaded_files.get_annotation_from_id(annotation_id)

    def set_time_interval(self, time_interval:tuple[float,float]|None ):
        if self._time_interval_gate.in_progress:
            return
        else:
            self._time_interval = time_interval
            with self._time_interval_gate.updating():
                self.time_interval_changed.emit(self._time_interval)

    def set_frequency_interval(self, frequency_interval:tuple[float,float]|None ):
        if self._frequency_interval_gate.in_progress:
            return
        else:
            self._frequency_interval = frequency_interval
            with self._frequency_interval_gate.updating():
                self.frequency_interval_changed.emit(self._frequency_interval)

    def set_cursor_frequency(self, f_Hz:float):
        if self._cursor_frequency_gate.in_progress:
            return
        else:
            self._cursor_frequency = f_Hz
            with self._cursor_frequency_gate.updating():
                self.cursor_frequency_changed.emit( self._cursor_frequency )

    def set_cursor_time(self, t_sec:float):
        if self._cursor_time_gate.in_progress:
            return
        else:
            self._cursor_time = t_sec
            with self._cursor_time_gate.updating():
                self.cursor_time_changed.emit( self._cursor_time )

    def set_selected_capture(self, capture_id: CaptureID):
        old_capture_id = self._selected_capture
        self._selected_capture = capture_id

        if self._selected_capture == old_capture_id:
            return

        self.set_frequency_interval(None)
        self.set_time_interval(None)
        self.set_cursor_time(0.0)
        self.set_cursor_frequency(0.0)

        self.selected_capture_changed.emit( self._selected_capture )
        self.selected_channel_changed.emit(0)  # default to channel 0  TODO: do something with channels

    def set_selected_annotation(self, annotation_id: AnnotationID|None):
        old_annotation_id = self._selected_annotation
        self._selected_annotation = annotation_id

        log.debug(f"AppState: set_selected_annotation: {self._selected_annotation} (was {old_annotation_id})")

        if self._selected_annotation == old_annotation_id:
            return

        self.selected_annotation_changed.emit( self._selected_annotation )


    def get_recent_files(self) -> list[str]:
        """Get the list of recent files."""
        return self._recent_files

    def add_recent_file(self, file_path: Path | str) -> None:
        """Add a file to the recent files list."""
        file_path = str(file_path)
        
        # Remove the file if it's already in the list
        if file_path in self._recent_files:
            self._recent_files.remove(file_path)
            
        # Add the file to the beginning of the list
        self._recent_files.insert(0, file_path)
        
        # Trim the list to maximum size
        if len(self._recent_files) > self.MAX_RECENT_FILES:
            self._recent_files = self._recent_files[:self.MAX_RECENT_FILES]
            
        # Save to settings
        settings = QSettings(SETTINGS_ORGANIZATION, SETTINGS_APPLICATION)
        settings.setValue("recentFiles", self._recent_files)
        
        # Emit signal
        self.recent_files_changed.emit()

    def clear_recent_files(self) -> None:
        """Clear the recent files list."""
        self._recent_files = []
        settings = QSettings(SETTINGS_ORGANIZATION, SETTINGS_APPLICATION)
        settings.setValue("recentFiles", self._recent_files)
        self.recent_files_changed.emit()

    def load_sigmf_file(self, file_path: Path) -> LoadedFile | None:
        """
        Load a SigMF file and return the LoadedFile object.
        Returns None if the file is already loaded.
        """
        is_first_load = len(self._loaded_files.loaded_file_dict) == 0

        loaded_file = self._loaded_files.load_file(file_path)
        if loaded_file is None:
            return None

        # Select the first capture of the newly loaded file
        self.set_selected_capture( first_from_dict(loaded_file._capture_id_to_capture).capture_id )

        # Add to recent files
        self.add_recent_file(file_path)

        return loaded_file

    def save_current_file(self):
        if self._selected_capture is None:
            return

        current_loaded_file = self._loaded_files._capture_id_to_capture[self._selected_capture].parent_loadedfile
        with measure_runtime(f"Save SigMF File: {current_loaded_file.sigmf_data_file_path}", log_level=logging.CRITICAL):
            current_loaded_file.save()

    def save_all_files(self) -> None:
        """
        Save all loaded files that have unsaved changes.
        Emits `loaded_files_changed` for each saved file so UI can refresh.
        """
        files = list(self._loaded_files.loaded_file_dict.values())
        for lf in files:
            try:
                if lf.has_unsaved_changes:
                    with measure_runtime(f"Save SigMF File: {lf.sigmf_data_file_path}", log_level=logging.CRITICAL):
                        lf.save()
                        log.info(f"Saved file: {lf.sigmf_data_file_path.name}")

                        # TODO: shoudln't be necessary now, remove?
                        # # Emit loaded_files_changed so views refresh their displays
                        # try:
                        #     self.loaded_files_changed.emit(lf.file_id, LoadedFileAction.OPENED)
                        # except Exception:
                        #     # If signal emission fails for any reason, continue
                        #     pass
            except Exception as e:
                log.exception(f"Failed to save file {getattr(lf, 'sigmf_data_file_path', lf)}: {e}")

    def check_unsaved_changes_and_prompt(self) -> bool:
        """
        Check all loaded files for unsaved changes and prompt to save.
        
        Returns:
            True if it's safe to continue (all changes saved or discarded), 
            False if the user cancelled
        """
        files_with_unsaved_changes = [
            lf for lf in self._loaded_files.loaded_file_dict.values() 
            if lf.has_unsaved_changes
        ]
        
        if not files_with_unsaved_changes:
            return True
        
        # Build message listing files with unsaved changes
        if len(files_with_unsaved_changes) == 1:
            file_name = files_with_unsaved_changes[0].sigmf_data_file_path.name
            message = f"The file '{file_name}' has unsaved changes.\n\nDo you want to save before closing?"
        else:
            file_list = "\n".join(f"  • {lf.sigmf_data_file_path.name}" 
                                 for lf in files_with_unsaved_changes)
            message = (f"{len(files_with_unsaved_changes)} files have unsaved changes:\n\n"
                      f"{file_list}\n\n"
                      f"Do you want to save all files before closing?")
        
        reply = QMessageBox.question(
            None,
            "Unsaved Changes",
            message,
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save
        )
        
        if reply == QMessageBox.Cancel:
            return False
        elif reply == QMessageBox.Save:
            # Save all files with unsaved changes
            for lf in files_with_unsaved_changes:
                lf.save()
                log.info(f"Saved file: {lf.sigmf_data_file_path.name}")
        
        return True

    def close_file(self, file_id: FileID, prompt_save: bool = True) -> bool:
        """
        Close a file, optionally prompting to save unsaved changes.
        
        Args:
            file_id: The ID of the file to close
            prompt_save: Whether to prompt the user to save unsaved changes
            
        Returns:
            True if the file was closed, False if the user cancelled
        """
        loaded_file = self._loaded_files.get_loaded_file_from_id(file_id)
        if loaded_file is None:
            log.warning(f"File ID {file_id} not found")
            return False
        
        # Check for unsaved changes
        if prompt_save and loaded_file.has_unsaved_changes:
            file_name = loaded_file.sigmf_data_file_path.name
            reply = QMessageBox.question(
                None,
                "Unsaved Changes",
                f"The file '{file_name}' has unsaved changes.\n\nDo you want to save before closing?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save
            )
            
            if reply == QMessageBox.Cancel:
                return False
            elif reply == QMessageBox.Save:
                # Save the file
                loaded_file.save()
        
        # If this file's capture is currently selected, we need to handle selection
        # Check if any of the file's captures are selected
        file_capture_ids = set(loaded_file._capture_id_to_capture.keys())
        if self._selected_capture in file_capture_ids:
            # Find another file to select, if available
            other_files = [f for f_id, f in self._loaded_files.loaded_file_dict.items() if f_id != file_id]
            if other_files:
                # Select the first capture of the first other file
                next_file = other_files[0]
                next_capture = first_from_dict(next_file._capture_id_to_capture)
                self.set_selected_capture(next_capture.capture_id)
            else:
                # No other files, clear selection
                self._selected_capture = None
                self.selected_capture_changed.emit(None)
        
        # Close the file
        self._loaded_files.close_file(file_id)
        log.info(f"Closed file: {loaded_file.sigmf_data_file_path.name}")
        return True

    def get_fft_config(self) -> FrequencyDomainComputationSpec:
        """Get the current FFT configuration."""
        return self._fft_config

    def set_fft_config(self, config: FrequencyDomainComputationSpec):
        """Set a new FFT configuration and emit change signal."""
        if self._fft_config == config:
            return
        self._fft_config = config
        self.fft_config_changed.emit(self._fft_config)

    def get_freq_domain_computation_spec(self) -> FrequencyDomainComputationSpec:
        """Get the frequency domain computation spec from current FFT config."""
        return self._fft_config

    def increase_fft_size(self):
        """Increase the FFT size to the next available size."""
        current_config = self._fft_config
        current_size = current_config.NFFT
        fft_sizes = list(FFTLength.__members__.values())
        try:
            current_idx = fft_sizes.index(current_size)
            if current_idx < len(fft_sizes) - 1:
                new_config = current_config.model_copy()
                new_config.NFFT = fft_sizes[current_idx + 1]
                self.set_fft_config(new_config)
        except ValueError:
            pass

    def decrease_fft_size(self):
        """Decrease the FFT size to the next smaller size."""
        current_config = self._fft_config
        current_size = current_config.NFFT
        fft_sizes = list(FFTLength.__members__.values())
        try:
            current_idx = fft_sizes.index(current_size)
            if current_idx > 0:
                new_config = current_config.model_copy()
                new_config.NFFT = fft_sizes[current_idx - 1]
                self.set_fft_config(new_config)
        except ValueError:
            pass

