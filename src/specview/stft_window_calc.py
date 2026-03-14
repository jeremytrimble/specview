import typing
import numpy as np

import dataclasses

# Takes a tuple of (start_sample, end_sample) and returns an ndarray of the
# input samples in that range. The end_sample is exclusive, i.e., the range is
# [start_sample, end_sample).
FetchInputSamplesCallback = typing.Callable[[int, int], np.ndarray]

@dataclasses.dataclass
class InputSampleRange:
    start_sample_idx: int       # the first sample index in the true input signal that is required to compute a given frame (inclusive), will always be >= 0
    end_sample_idx: int         # the last sample index in the true input signal that is required to compute a given frame (exclusive), will always be <= num_input_samples
    left_padding_samples: int   # number of padding samples (not part of the true signal) to the left of start_sample that are needed for the windowing function
    right_padding_samples: int  # number of padding samples (not part of the true signal) to the right of end_sample that are needed for the windowing function

    @property
    def window_length_samples(self) -> int:
        return self.end_sample_idx - self.start_sample_idx + self.left_padding_samples + self.right_padding_samples

class STFTWindowCalculator:
    """
    The input samples for each frame are computed as:
    half_win = win_length_samples // 2

    frame[p] corresponds to input samples:
    start_sample = p * hop_samples - half_win
    end_sample = start_sample + win_length_samples

    frame is computed as:
    frame[p,:] = STFT( win * input_samples[start_sample:end_sample], NFFT=NFFT) 
    """

    def __init__(self, 
        # Input Parameters
        num_input_samples: int,
        sample_rate_Hz: float,

        # Calculation Parameters
        NFFT: int,
        win_length_samples: int,
        hop_samples: int,
    ):
        self.num_input_samples = num_input_samples
        self.sample_rate_Hz = sample_rate_Hz

        self.NFFT = NFFT
        self.win_length_samples = win_length_samples
        self.hop_samples = hop_samples

        self._half_win = self.win_length_samples // 2

    @property
    def delta_f_Hz(self) -> float:
        """
        Return the frequency resolution of the STFT in Hz.
        This is equal to the sample rate divided by the FFT size.
        """
        return self.sample_rate_Hz / self.NFFT

    @property
    def frame_period_sec(self) -> float:
        """
        Return the time difference between adjacent frames in seconds.
        This could also be called the "frame period".
        """
        return self.hop_samples / self.sample_rate_Hz

    @property
    def num_frames(self) -> int:
        """
        Return the number of frames that can be computed from the input samples.
        """
        return (self.num_input_samples + self.hop_samples - 1) // self.hop_samples

    def calculate_input_sample_range_for_frame(self, frame_index: int) -> InputSampleRange|None:
        """
        Given a frame index, return the start and end input sample indices that are required to compute that frame.
        The end index is exclusive, i.e., the range is [start_sample, end_sample).
        If the frame index is out of bounds, return None.
        """

        if frame_index < 0 or frame_index >= self.num_frames:
            return None

        start_sample = frame_index * self.hop_samples - self._half_win
        end_sample = start_sample + self.win_length_samples

        if start_sample < 0:
            left_padding = -start_sample
            realsig_start_sample = 0
        else:
            left_padding = 0
            realsig_start_sample = start_sample

        if end_sample > self.num_input_samples:
            right_padding = end_sample - self.num_input_samples
            realsig_end_sample = self.num_input_samples
        else:
            right_padding = 0
            realsig_end_sample = end_sample

        return InputSampleRange(
            start_sample_idx=realsig_start_sample,
            end_sample_idx=realsig_end_sample,
            left_padding_samples=left_padding,
            right_padding_samples=right_padding
        )

    def calculate_input_sample_range_for_frame_range(self, start_frame: int, end_frame: int) -> InputSampleRange|None:
        """
        Given a range of frame indices [start_frame, end_frame), return the start and end input sample indices that are required to compute that range of frames.
        The end index is exclusive, i.e., the range is [start_sample, end_sample).
        If the frame range is out of bounds, return None.
        """

        if start_frame < 0 or end_frame > self.num_frames or start_frame >= end_frame:
            return None

        start_range = self.calculate_input_sample_range_for_frame(start_frame)
        end_range = self.calculate_input_sample_range_for_frame(end_frame - 1)

        if start_range is None or end_range is None:
            return None

        return InputSampleRange(
            start_sample_idx=start_range.start_sample_idx,
            end_sample_idx=end_range.end_sample_idx,
            left_padding_samples=start_range.left_padding_samples,
            right_padding_samples=end_range.right_padding_samples
        )

    def calculate_stft_frames_given_required_input_data(
        self,
        input_data: np.ndarray,     # type is expected to be either float32 or complex64
        input_sample_base_idx: int,
        start_frame: int,
        end_frame: int,
        #out: np.ndarray|None = None    #TODO: support this?
    ) -> np.ndarray:
        """
        Given the input data and the base index of the input data, compute the STFT frames for the given frame range [start_frame, end_frame).
        The input_data is assumed to be a 1D array of complex samples.
        The input_sample_base_idx is the index of the first sample in input_data relative to the original input signal.

        The returned array has 2 dimensions: [num_frames, NFFT], where num_frames = end_frame - start_frame.
        """

        first_sample_idx_available = input_sample_base_idx
        last_sample_idx_available = input_sample_base_idx + len(input_data)

        # Calculate the required input sample range for the given frame range
        required_range = self.calculate_input_sample_range_for_frame_range(start_frame, end_frame)
        if required_range is None:
            raise ValueError(f"Frame range [{start_frame}, {end_frame}) is out of bounds.")

        if required_range.start_sample_idx < first_sample_idx_available or required_range.end_sample_idx > last_sample_idx_available:
            raise ValueError(f"Required input sample range [{required_range.start_sample_idx}, {required_range.end_sample_idx}) is not covered by the provided input_data range [{first_sample_idx_available}, {last_sample_idx_available}).")

        windowed_samples = np.zeros(self.win_length_samples, dtype=input_data.dtype)

        # Compute STFT frames
        output_frames = np.empty((end_frame - start_frame, self.NFFT), dtype=np.complex64 if np.iscomplexobj(input_data) else np.float32)

        for stft_idx,frame_index in enumerate(range(start_frame, end_frame)):
            frame_range = self.calculate_input_sample_range_for_frame(frame_index)
            assert frame_range is not None, f"Frame index {frame_index} is out of bounds."  # This should never happen due to the earlier check

            # Extract the relevant samples from input_data
            start_idx = frame_range.start_sample_idx - input_sample_base_idx
            end_idx = frame_range.end_sample_idx - input_sample_base_idx
            frame_samples = input_data[start_idx:end_idx]

            # Apply windowing and compute FFT
            windowed_samples[:] = 0 # this pads with zeros to the left and/or right as required
            windowed_samples[frame_range.left_padding_samples:frame_range.left_padding_samples + len(frame_samples)] = frame_samples
            stft_frame = np.fft.fftshift(np.fft.fft(windowed_samples, n=self.NFFT))
            # TODO: compute magnitude here and always return float32?
            output_frames[stft_idx] = stft_frame

        return output_frames

    def calculate_stft_frames_using_callback(self, start_frame: int, end_frame: int, fetch_input_samples_callback: FetchInputSamplesCallback) -> np.ndarray:
        """
        Given a range of frame indices [start_frame, end_frame), fetch the required input samples using the provided callback and compute the STFT frames for that range.
        The fetch_input_samples_callback is a function that takes a start and end sample index and returns the corresponding input samples as a 1D numpy array.
        """
        # Calculate the required input sample range for the given frame range
        required_range = self.calculate_input_sample_range_for_frame_range(start_frame, end_frame)
        if required_range is None:
            raise ValueError(f"Frame range [{start_frame}, {end_frame}) is out of bounds.")
        
        # Fetch the required input samples using the callback
        input_data = fetch_input_samples_callback(required_range.start_sample_idx, required_range.end_sample_idx)
        input_sample_base_idx = required_range.start_sample_idx

        return self.calculate_stft_frames_given_required_input_data(input_data, input_sample_base_idx, start_frame, end_frame)
