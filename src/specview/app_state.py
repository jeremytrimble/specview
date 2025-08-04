from __future__ import annotations
from PyQt5.QtCore import QSize, Qt, QThread, pyqtSignal, QObject, QTimer
from PyQt5.QtWidgets import QApplication, QMainWindow, QGridLayout, QWidget, QSlider, QLabel, QHBoxLayout, QVBoxLayout, QPushButton, QComboBox  # tested with PyQt6==6.7.0

from contextlib import contextmanager
import typing

import sigmf
from pathlib import Path
import dataclasses
import enum
from specview.disk_cache import dcache
from specview.monotonic_axis import MonotonicAxis
from specview.spec_types import Spectrogram, TimeSeries
from specview.util import measure_runtime
from specview.smf import smf_get_field_cap_or_global
import scipy.signal, scipy.signal.windows
import numpy as np

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


class LoadedFileCounter:
    def __init__(self):
        self._counter:int =0
    def get_next_open_file_id(self) -> str:
        rv = f"fid{self._counter:03d}"
        self._counter += 1
        return rv
LFC = LoadedFileCounter()
del LoadedFileCounter

@dataclasses.dataclass
class LoadedFile:
    file_path: Path
    sigmf_file: sigmf.SigMFFile
    open_file_id: str = dataclasses.field(default_factory=LFC.get_next_open_file_id)

class LoadedFileAction(enum.Enum):
    OPENED = "opened"
    CLOSED = "closed"

class LoadedFiles:
    def __init__(self, app_state: AppState = None):
        self._app_state = app_state
        self._fileid_to_loadedfile: dict[str, LoadedFile] = {}

    def load_file(self, file_path: Path) -> LoadedFile:
        sigmf_file = sigmf.sigmffile.fromfile(file_path)
        loaded_file = LoadedFile(file_path=file_path, sigmf_file=sigmf_file)
        is_first_load = len(self._fileid_to_loadedfile) == 0
        self._fileid_to_loadedfile[loaded_file.open_file_id] = loaded_file
        self._app_state.loaded_files_changed.emit( loaded_file.open_file_id, LoadedFileAction.OPENED )  
        if is_first_load:
            self._app_state.selected_capture_changed.emit( loaded_file.open_file_id, 0 )
            self._app_state.selected_channel_changed.emit(0)  # default to channel 0

        return loaded_file
    def close_file(self, fileid: str):
        if fileid in self._fileid_to_loadedfile:
            loaded_file = self._fileid_to_loadedfile[fileid]
            del self._fileid_to_loadedfile[fileid]
            self._app_state.loaded_files_changed.emit( (loaded_file.open_file_id, LoadedFileAction.CLOSED) )
        else:
            # TODO: should this raise an exception or just do nothing?
            raise ValueError(f"File ID {fileid} not found in loaded files.")

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
        sample_rate_Hz = smf_get_field_cap_or_global(smf, cap_idx, sigmf.SigMFFile.SAMPLE_RATE_KEY)
        center_freq_Hz = smf_get_field_cap_or_global(smf, cap_idx, sigmf.SigMFFile.FREQUENCY_KEY, None)

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

        spec_freq_Hz = MonotonicAxis( slope = spec_freq_Hz[1] - spec_freq_Hz[0], num_points = len(spec_freq_Hz), intercept = spec_freq_Hz[0] )
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

    loaded_files_changed = pyqtSignal([str, LoadedFileAction], name='loaded_files_changed') # emitted when a file is opened or closed
    selected_capture_changed = pyqtSignal([str,int], name='selected_capture_changed') # emitted with (fileid, index) when a capture is selected
    selected_channel_changed = pyqtSignal(int, name='selected_channel_changed') # emitted with channel_index when a channel is selected

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

        self._cursor_frequency_gate = SignalGate()
        self._cursor_time_gate = SignalGate()
        self._time_interval_gate = SignalGate()
        self._frequency_interval_gate = SignalGate()

        self._loaded_files = LoadedFiles(app_state=self)

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

    def load_sigmf_file(self, file_path: Path) -> LoadedFile:
        """
        Load a SigMF file and return the LoadedFile object.
        """
        return self._loaded_files.load_file(file_path)
    
    def load_capture_data(self, loaded_fileid: str, cap_idx: int, channel_idx: int) -> tuple[TimeSeries, Spectrogram]:
        """
        Load a capture from a SigMF file and return the TimeSeries and Spectrogram objects.
        """
        loaded_file = self._loaded_files._fileid_to_loadedfile.get(loaded_fileid)
        if loaded_fileid is None:
            raise ValueError(f"Loaded file ID {loaded_fileid} not found in loaded files.")
        tser, sgram = load_capture(loaded_file.sigmf_file, cap_idx, channel_idx)
        return tser, sgram

