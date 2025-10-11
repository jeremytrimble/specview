from scipy.signal import ShortTimeFFT
from scipy.signal.windows import get_window
import numpy as np

def generate_cw(num_samples:int, sample_rate_Hz:float, f0_Hz:float) -> np.ndarray:
    """Generate a complex sinusoid for testing."""
    t = np.arange(num_samples) / sample_rate_Hz
    return np.exp(2j * np.pi * f0_Hz * t).astype(np.complex64)

def test1():
    signal = generate_cw(10000, 1e6, 100e3)
    win = get_window("hann", 256)
    stfft_obj = ShortTimeFFT(win=win, hop=128, fs=1e6, fft_mode="centered", scale_to="psd")

    nkp0 = stfft_obj.nearest_k_p(0, left=True)
    nkp1 = stfft_obj.nearest_k_p(1, left=True)
    nkp130 = stfft_obj.nearest_k_p(130, left=True)

    S = stfft_obj.stft(signal)

    num_bins, num_frames = S.shape

    assert num_bins == 256

    print(f"{S.dtype=}, {num_frames = }, nkp0={nkp0}, nkp1={nkp1}, nkp130={nkp130}")

    frame_idx_start = 10
    frame_idx_stop = 42

    ## solve for input sample indexes that produce these frames
    #start_input_sample = frame_idx_start * stfft_obj.hop
    #end_input_sample = (frame_idx_stop) * stfft_obj.hop - 1

    S_chunk = stfft_obj.stft(x=signal, p0=frame_idx_start, p1=frame_idx_stop)

    print(f"S_chunk.shape = {S_chunk.shape}")

    assert np.allclose(S[:,frame_idx_start:frame_idx_stop], S_chunk)
