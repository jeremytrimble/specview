from dataclasses import dataclass
import enum

import numpy as np
from .monotonic_axis import MonotonicAxis


class ComputedDataType(str, enum.Enum):
    TIME_SERIES = "time-series" # dimensions are [channel, time]
    SPECTROGRAM = "spectrogram" # dimensios are [channel, time, freq]


@dataclass
class TimeSeries:
    time_sec: MonotonicAxis    # timestamps, same length as first dimension of data
    channels: list[str] # list of channels in this capture
    data: np.ndarray # [channel, time]
    cdtype: ComputedDataType = ComputedDataType.TIME_SERIES


@dataclass
class Spectrogram:
    channels: list[str] # list of channels in this capture
    time_sec: MonotonicAxis    # timestamps, same length as first dimension of data
    freq_Hz: MonotonicAxis     # frequency, relative to center bin
    center_freq_Hz: float|None  # tuner center frequency if applicable, or None
    data: np.ndarray # [channel, time, freq], raw complex values
    mag_dB: np.ndarray # [channel, time, freq], 20*log10(abs(data))
    cdtype: ComputedDataType = ComputedDataType.SPECTROGRAM


from pydantic import BaseModel, Field

class WindowType(str, enum.Enum):
    HAMMING = "hamming"
    HANN = "hann"
    BLACKMAN = "blackman"
    RECTANGULAR = "rectangular"

class FFTLength(int, enum.Enum):
    N128 = 128
    N256 = 256
    N512 = 512
    N1024 = 1024
    N2048 = 2048
    N4096 = 4096
    N8192 = 8192
    #N16384 = 16384

class HopSize(float, enum.Enum):
    HOP_50 = 0.50
    HOP_75 = 0.75
    HOP_90 = 0.90
    HOP_100 = 1.00

class STFFTConfig(BaseModel):
    NFFT: FFTLength = Field(default=FFTLength.N1024, description="Number of FFT points")
    win_length: int = Field(default=1024, description="Length of the window in samples")    # TODO: is this the right way to think of this?
    win: WindowType = Field(default="hamming", description="Window type for STFFT")     # TODO: use enum.Enum for window types
    hop: HopSize = Field(default=HopSize.HOP_90, description="Hop size for STFFT")      # TODO: specify this in percentage or time?
    #fs: float = Field(default=1.0, description="Sampling frequency in Hz")
    #fft_mode: str = Field(default="centered", description="FFT mode, e.g., 'centered' or 'unshifted'")
