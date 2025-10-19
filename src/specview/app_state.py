from __future__ import annotations
from PyQt5.QtCore import QSize, Qt, QThread, pyqtSignal, QObject, QTimer
from PyQt5.QtWidgets import QApplication, QMainWindow, QGridLayout, QWidget, QSlider, QLabel, QHBoxLayout, QVBoxLayout, QPushButton, QComboBox, QFileDialog, QMessageBox

from contextlib import contextmanager

import sigmf
from pathlib import Path
import dataclasses
from specview.loaded_file_mgmt import (
    LoadedAnnotationDict, LoadedCaptureDict, LoadedDictAction, LoadedFile, LoadedFileAction, LoadedFilesCollection, FileID, CaptureID, AnnotationID,
)
from specview.util import measure_runtime, first_from_dict
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

    frequency_interval_changed = pyqtSignal( [object], name="frequency_interval_changed") # tuple[float,float]|None
    time_interval_changed      = pyqtSignal( [object], name="time_interval_changed")    # tuple[float,float]|None

    loaded_files_changed = pyqtSignal([FileID, LoadedFileAction], name='loaded_files_changed') # emitted when a file is opened or closed
    selected_capture_changed = pyqtSignal([CaptureID], name='selected_capture_changed') # emitted with (CaptureID) when a capture is selected
    selected_channel_changed = pyqtSignal(int, name='selected_channel_changed') # emitted with channel_index when a channel is selected

    annotation_changed = pyqtSignal([AnnotationID,LoadedDictAction], name='annotation_changed')

    def __init__(self, parent = ...):
        super().__init__(parent)

        # Items of state:
        # - set of opened sigmf files

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

        self._cursor_frequency_gate = SignalGate()
        self._cursor_time_gate = SignalGate()
        self._time_interval_gate = SignalGate()
        self._frequency_interval_gate = SignalGate()

        self._loaded_files = LoadedFilesCollection()
        self._loaded_files.set_file_load_or_unload_callback(self._on_file_load_or_unload)
        self._loaded_files.set_annotation_changed_callback(self._on_annotation_changed)


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

    def load_sigmf_file(self, file_path: Path) -> LoadedFile:
        """
        Load a SigMF file and return the LoadedFile object.
        """
        file_path = Path(file_path)

        is_first_load = len(self._loaded_files.loaded_file_dict) == 0

        loaded_file = self._loaded_files.load_file(file_path)

        if is_first_load:
            self.set_selected_capture( first_from_dict(loaded_file._capture_id_to_capture).capture_id )

        return loaded_file

    def save_current_file(self):
        if self._selected_capture is None:
            return

        current_loaded_file = self._loaded_files._capture_id_to_capture[self._selected_capture].parent_loadedfile
        smf = current_loaded_file.sigmf_file
        with measure_runtime(f"Save SigMF File: {smf.data_file}", log_level=logging.CRITICAL):
            meta_filename = sigmf.sigmffile.get_sigmf_filenames(current_loaded_file.file_path)["meta_fn"]
            smf.tofile(file_path=meta_filename)

    #def save_as(self, parent):

    #    options = QFileDialog.Options()
    #    options |= QFileDialog.DontConfirmOverwrite
    #    file_name, _ = QFileDialog.getSaveFileName(parent, "Save SigMF File As", "", "SigMF Files (*.sigmf-meta)", options=options)
    #    if file_name:
    #        log.info(f"Selected file for save as: {file_name}")
    #        new_filenames_dict = sigmf.sigmffile.get_sigmf_filenames(file_name)
    #        new_base_fn = new_filenames_dict.pop("base_fn")
    #        existing = [ p for p in new_filenames_dict.values() if p.exists() ]

    #        if existing:
    #            reply = QMessageBox.question(parent, "OK to overwrite?",
    #                    f"SIGMF File(s) already exist with the base name: \n{new_base_fn.name}\n Do you want to overwrite these file(s)?",
    #                    QMessageBox.Yes | QMessageBox.Cancel)
    #            if reply != QMessageBox.Yes:
    #                return
    #            
    #        current_loaded_file = self._loaded_files.loaded_file_dict[self._selected_capture_fileid]
    #        smf = current_loaded_file.sigmf_file

    #        existing_filenames_dict = sigmf.sigmffile.get_sigmf_filenames(current_loaded_file.file_path)

    #        with measure_runtime(f"Save As to {new_base_fn}"):
    #            shutil.copy( 
    #                existing_filenames_dict["data_fn"],
    #                new_filenames_dict["data_fn"],
    #            )
    #            smf.set_data_file( new_filenames_dict["data_fn"] )
    #            smf.tofile( new_filenames_dict["meta_fn"] )

    #            # TODO: reload data content somehow?
    #            current_loaded_file.file_path = new_filenames_dict["meta_fn"]



