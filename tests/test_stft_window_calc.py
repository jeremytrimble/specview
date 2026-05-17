import numpy as np
import pytest

from specview.chunkwise_compute import STFTWindowCalculator, WindowType


def test_num_frames_uses_floor_division() -> None:
    calc = STFTWindowCalculator(
        num_input_samples=10,
        sample_rate_Hz=1.0,
        NFFT=8,
        win_length_samples=6,
        win_type=WindowType.HAMMING,
        hop_samples=4,
    )

    assert calc.num_frames == 3
    assert calc.frame_period_sec == 4.0


def test_calculate_input_sample_range_for_frame_handles_edge_padding() -> None:
    calc = STFTWindowCalculator(
        num_input_samples=10,
        sample_rate_Hz=1.0,
        NFFT=8,
        win_length_samples=6,
        win_type=WindowType.HAMMING,
        hop_samples=4,
    )

    first = calc.calculate_input_sample_range_for_frame(0)
    assert first is not None
    assert first.start_sample_idx == 0
    assert first.end_sample_idx == 3
    assert first.left_padding_samples == 3
    assert first.right_padding_samples == 0
    assert first.window_length_samples == 6

    last = calc.calculate_input_sample_range_for_frame(2)
    assert last is not None
    assert last.start_sample_idx == 5
    assert last.end_sample_idx == 10
    assert last.left_padding_samples == 0
    assert last.right_padding_samples == 1
    assert last.window_length_samples == 6


@pytest.mark.parametrize(
    ("start_frame", "end_frame"),
    [(-1, 1), (0, 0), (0, 4), (2, 1)],
)
def test_calculate_input_sample_range_for_frame_range_rejects_invalid_ranges(
    start_frame: int,
    end_frame: int,
) -> None:
    calc = STFTWindowCalculator(
        num_input_samples=10,
        sample_rate_Hz=1.0,
        NFFT=8,
        win_length_samples=6,
        win_type=WindowType.HAMMING,
        hop_samples=4,
    )

    assert calc.calculate_input_sample_range_for_frame_range(start_frame, end_frame) is None


def test_calculate_stft_frames_using_callback_matches_direct_path() -> None:
    calc = STFTWindowCalculator(
        num_input_samples=16,
        sample_rate_Hz=1.0,
        NFFT=8,
        win_length_samples=6,
        win_type=WindowType.HAMMING,
        hop_samples=4,
    )

    signal = (
        np.arange(16, dtype=np.float32) + 1j * np.arange(100, 116, dtype=np.float32)
    ).astype(np.complex64)

    start_frame = 1
    end_frame = 3
    required_range = calc.calculate_input_sample_range_for_frame_range(start_frame, end_frame)
    assert required_range is not None

    direct = calc.calculate_stft_frames_given_required_input_data(
        input_data=signal[required_range.start_sample_idx : required_range.end_sample_idx],
        input_sample_base_idx=required_range.start_sample_idx,
        start_frame=start_frame,
        end_frame=end_frame,
    )

    def fetch_input_samples(start: int, end: int) -> np.ndarray:
        return signal[start:end]

    via_callback = calc.calculate_stft_frames_using_callback(
        start_frame=start_frame,
        end_frame=end_frame,
        fetch_input_samples_callback=fetch_input_samples,
    )

    assert np.allclose(direct, via_callback)


def test_single_frame_matches_same_frame_from_batch() -> None:
    calc = STFTWindowCalculator(
        num_input_samples=24,
        sample_rate_Hz=1.0,
        NFFT=8,
        win_type=WindowType.HAMMING,
        win_length_samples=6,
        hop_samples=4,
    )

    signal = (
        np.arange(24, dtype=np.float32) + 1j * np.arange(200, 224, dtype=np.float32)
    ).astype(np.complex64)

    single_start = 2
    single_end = 3
    batch_start = 1
    batch_end = 5

    single_required = calc.calculate_input_sample_range_for_frame_range(single_start, single_end)
    assert single_required is not None
    single_frame = calc.calculate_stft_frames_given_required_input_data(
        input_data=signal[single_required.start_sample_idx : single_required.end_sample_idx],
        input_sample_base_idx=single_required.start_sample_idx,
        start_frame=single_start,
        end_frame=single_end,
    )

    batch_required = calc.calculate_input_sample_range_for_frame_range(batch_start, batch_end)
    assert batch_required is not None
    batch_frames = calc.calculate_stft_frames_given_required_input_data(
        input_data=signal[batch_required.start_sample_idx : batch_required.end_sample_idx],
        input_sample_base_idx=batch_required.start_sample_idx,
        start_frame=batch_start,
        end_frame=batch_end,
    )

    index_in_batch = single_start - batch_start
    assert np.allclose(single_frame[0], batch_frames[index_in_batch])
