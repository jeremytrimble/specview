
import scipy.signal
import scipy.signal.windows

import pytest

def test_chunkwise_fft1():

    sample_rate_Hz = 10e6



    NFFT = 1024
    win = scipy.signal.windows.hamming(NFFT)
    scipy.signal.ShortTimeFFT(
        win = win,
        hop = NFFT-(NFFT//4),
        fft_mode="twosided",
    )
