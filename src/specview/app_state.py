from __future__ import annotations
from PyQt5.QtCore import QSize, Qt, QThread, pyqtSignal, QObject, QTimer
from PyQt5.QtWidgets import QApplication, QMainWindow, QGridLayout, QWidget, QSlider, QLabel, QHBoxLayout, QVBoxLayout, QPushButton, QComboBox, QFileDialog, QMessageBox

from contextlib import contextmanager

import sigmf
from pathlib import Path
import dataclasses
from specview.disk_cache import dcache
from specview.loaded_file_mgmt import (
    LoadedAnnotationDict, LoadedCaptureDict, LoadedDictAction, LoadedFile, LoadedFileAction, LoadedFilesCollection, FileID, CaptureID, AnnotationID,
)
from specview.monotonic_axis import MonotonicAxis
from specview.spec_types import Spectrogram, TimeSeries
from specview.util import measure_runtime
from specview.smf import smf_get_field_cap_or_global
import scipy.signal, scipy.signal.windows
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


def get_annotation_time_bound_relative_to_current_capture(adict: dict, current_capture_idx:int, sigmf_file: sigmf.SigMFFile, return_none_if_disjoint:bool=True ) -> tuple[float,float]|None:

    ann_start_idx = adict.get(sigmf.SigMFFile.START_INDEX_KEY)
    ann_length_samples = adict.get(sigmf.SigMFFile.LENGTH_INDEX_KEY)

    if ann_start_idx is None or ann_length_samples is None:
        return None
    
    ann_start_idx = int(ann_start_idx)
    ann_length_samples = int(ann_length_samples)

    if ann_start_idx < 0 or ann_length_samples <= 0:
        return None

    sample_rate_Hz = sigmf_file.get_global_field(sigmf.SigMFFile.SAMPLE_RATE_KEY)
    if sample_rate_Hz is None:
        raise ValueError("Global SAMPLE_RATE_KEY not found in SigMF file.")

    # Get the start index from the annotation dictionary or the capture
    captures_array = sigmf_file.get_captures()
    cdict = captures_array[current_capture_idx]
    # Note: LENGTH_INDEX_KEY is only defined in annotations, never in captures
    # Note: START_INDEX_KEY is REQUIRED in all captures
    capture_start_idx = cdict[sigmf.SigMFFile.START_INDEX_KEY]

    if current_capture_idx + 1 < len(captures_array):
        next_cdict = captures_array[current_capture_idx + 1]
        capture_end_idx = next_cdict[sigmf.SigMFFile.START_INDEX_KEY]
        del next_cdict
    else:
        capture_end_idx = sigmf_file.sample_count   # this is the total number of samples in the data file
    capture_duration_sec = (capture_end_idx - capture_start_idx) / sample_rate_Hz
    if capture_duration_sec <= 0:
        raise ValueError("Capture has non-positive duration.")

    samples_from_beginning_of_capture = ann_start_idx - capture_start_idx

    start_time_sec = samples_from_beginning_of_capture / sample_rate_Hz
    end_time_sec = (samples_from_beginning_of_capture + ann_length_samples) / sample_rate_Hz

    if return_none_if_disjoint:
        # if both start and end are before the capture start, or both are after the capture end, then return None
        if end_time_sec < 0 and start_time_sec < 0:
            return None
        if start_time_sec > capture_duration_sec and end_time_sec > capture_duration_sec:
            return None

    return start_time_sec, end_time_sec

def make_numpy_array_readonly(arr: np.ndarray) -> np.ndarray:
    """
    Convert a numpy array to a read-only array.
    """
    return arr.setflags(write=False)

@dcache.memoize()
# note: Path not hashable repeatably
def load_capture(smf:sigmf.SigMFFile, cap_idx:int, channel_idx:int = 0) -> tuple[TimeSeries, Spectrogram]:
    with measure_runtime("entirety of load_capture"):
        #sample_rate_Hz = cap.get(sigmf.SigMFFile.SAMPLE_RATE_KEY) or smf.get_global_field(sigmf.SigMFFile.SAMPLE_RATE_KEY)

        #TODO: I think that SAMPLE_RATE_KEY should only be defined in the global fields, not in the capture fields, right?
        sample_rate_Hz = smf_get_field_cap_or_global(smf, cap_idx, sigmf.SigMFFile.SAMPLE_RATE_KEY)
        center_freq_Hz = smf_get_field_cap_or_global(smf, cap_idx, sigmf.SigMFFile.FREQUENCY_KEY, 0.0)

        # TODO: capture as SpectrogramConfig pa.rameter
        NFFT = 512 
        win = scipy.signal.windows.hamming(NFFT)
        f = scipy.signal.ShortTimeFFT(
            win=win,
            hop=len(win)-len(win)//4,
            fs=sample_rate_Hz,
            fft_mode="centered",
        )

        with measure_runtime("timeseries loading"):
            timedomain_data = smf.read_samples_in_capture(cap_idx)    # TODO: this seems to return a wrong/arbitrary number of samples in some cases
            make_numpy_array_readonly(timedomain_data)
            # TODO: handle multiple channels correctly here
            assert channel_idx == 0, "Only channel 0 is currently supported in load_capture"
        t = MonotonicAxis(slope=1/sample_rate_Hz, num_points=len(timedomain_data))

        with measure_runtime("FFT"):
            S = f.stft(timedomain_data)
            S = S.T # transpose so that now S.shape = [num_times x num_bins]
        Smag_dB = 20*np.log10(np.abs(S))

        make_numpy_array_readonly(S)
        make_numpy_array_readonly(Smag_dB)

        tdat = TimeSeries(
            time_sec=t,
            channels=["ch0"], #TODO
            data=timedomain_data.reshape([1,len(timedomain_data)]),
        )

        spec_freq_Hz = f.f
        spec_time_sec = f.t(len(timedomain_data))

        #print(f"{Smag_dB.shape=}")
        #print(f"{len(spec_time_sec)=}, {len(spec_freq_Hz)=}")
        assert Smag_dB.shape == (len(spec_time_sec), len(spec_freq_Hz))

        spec_freq_Hz = MonotonicAxis( slope = spec_freq_Hz[1] - spec_freq_Hz[0], num_points = len(spec_freq_Hz), intercept = spec_freq_Hz[0] + center_freq_Hz )
        spec_time_sec = MonotonicAxis( slope = spec_time_sec[1] - spec_time_sec[0], num_points = len(spec_time_sec), intercept = spec_time_sec[0] )

        spec = Spectrogram(
            channels=["ch0"],    #TODO
            time_sec = spec_time_sec,
            freq_Hz=spec_freq_Hz,
            center_freq_Hz=center_freq_Hz,
            data = S.reshape([1,len(spec_time_sec),len(spec_freq_Hz)]),
            mag_dB = Smag_dB.reshape([1,len(spec_time_sec),len(spec_freq_Hz)]),
        )

        return tdat, spec

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
            self.set_selected_capture(loaded_file._captures[0].capture_id )

        return loaded_file

    
    def load_capture_data(self, loaded_fileid: str, cap_idx: int, channel_idx: int) -> tuple[TimeSeries, Spectrogram]:
        """
        Load a capture from a SigMF file and return the TimeSeries and Spectrogram objects.
        """
        loaded_file = self._loaded_files.loaded_file_dict.get(loaded_fileid)
        if loaded_fileid is None:
            raise ValueError(f"Loaded file ID {loaded_fileid} not found in loaded files.")
        tser, sgram = load_capture(loaded_file.sigmf_file, cap_idx, channel_idx)
        return tser, sgram

    def save_current_file(self):
        if self._selected_capture_fileid is None:
            return

        current_loaded_file = self._loaded_files.loaded_file_dict[self._selected_capture_fileid]
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



