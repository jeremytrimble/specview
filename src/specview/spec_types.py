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