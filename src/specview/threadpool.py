from PyQt5.QtCore import QThread, QThreadPool, QObject, QRunnable, pyqtSignal

from .spec_types import Spectrogram, TimeSeries, SpectrogramConfig, STFFTConfig

def compute_parallel_chunkwise_stft(stft_config: STFFTConfig, time_series: TimeSeries, chunk_start: int, chunk_end: int) -> Spectrogram:
    """
    Start at multiple points in the time series and compute the STFT for each chunk.
    """
    pass
    
    # haha nice try AI didn't solve this one