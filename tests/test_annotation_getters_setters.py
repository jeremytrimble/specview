from sigmf import SigMFFile
import numpy as np
from pathlib import Path
import pytest

from specview.loaded_file_mgmt import LoadedFilesCollection, CacheManager


def generate_test_sigmffile(tmpdir) -> Path:
    """Generate a test SigMF file with two captures and one annotation."""
    TOTAL_NUM_SAMPLES = 2_000_000
    np.zeros(TOTAL_NUM_SAMPLES, dtype=np.complex64).tofile(tmpdir / "test.sigmf-data")
    
    smf = SigMFFile()
    smf.set_global_field(SigMFFile.DATATYPE_KEY, "cf32_le")
    smf.set_global_field(SigMFFile.SAMPLE_RATE_KEY, 1e6)  # 1 MHz sample rate
    smf.add_capture(start_index=0, metadata={SigMFFile.FREQUENCY_KEY: 2.4e9})
    smf.add_capture(start_index=1_000_000, metadata={SigMFFile.FREQUENCY_KEY: 2.5e9})
    
    smf.set_data_file(str(tmpdir / "test.sigmf-data"))
    
    # Add annotation in first capture: starts at 100k samples, length 500k samples
    # At 1MHz sample rate: starts at 0.1s, ends at 0.6s, duration 0.5s
    smf.add_annotation(start_index=100_000, length=500_000, metadata={
        SigMFFile.FLO_KEY: 2.4e9 - 100e3,  # 2.4 GHz - 100 kHz
        SigMFFile.FHI_KEY: 2.4e9 + 100e3,  # 2.4 GHz + 100 kHz
    })
    
    smf.tofile(tmpdir / "test.sigmf-meta")
    
    return Path(tmpdir / "test.sigmf-meta")


def test_get_start_time_sec(tmpdir):
    """Test getting start time in seconds."""
    sigmf_path = generate_test_sigmffile(tmpdir)
    cache_manager = CacheManager(base_path=Path(tmpdir/"cache"))
    lfc = LoadedFilesCollection(cache_manager=cache_manager)
    lf = lfc.load_file(sigmf_path)
    
    annotations = lf.get_annotations_dict()
    ann = list(annotations.values())[0]
    
    # Get the capture IDs
    capture_ids = list(lf._capture_id_to_capture.keys())
    first_capture_id = capture_ids[0]
    second_capture_id = capture_ids[1]
    
    # Test getting start time for first capture
    start_time = ann.get_start_time_sec(first_capture_id)
    assert start_time == 0.1  # 100,000 samples / 1e6 samples/sec = 0.1 sec
    
    # Annotation is not in second capture
    start_time = ann.get_start_time_sec(second_capture_id)
    assert start_time is None


def test_set_start_time_sec(tmpdir):
    """Test setting start time in seconds."""
    sigmf_path = generate_test_sigmffile(tmpdir)
    cache_manager = CacheManager(base_path=Path(tmpdir/"cache"))
    lfc = LoadedFilesCollection(cache_manager=cache_manager)
    lf = lfc.load_file(sigmf_path)
    
    annotations = lf.get_annotations_dict()
    ann = list(annotations.values())[0]
    
    capture_ids = list(lf._capture_id_to_capture.keys())
    first_capture_id = capture_ids[0]
    
    # Set start time to 0.2 seconds
    ann.set_start_time_sec(first_capture_id, 0.2)
    
    # Verify the change
    assert ann[SigMFFile.START_INDEX_KEY] == 200_000  # 0.2 sec * 1e6 samples/sec = 200,000 samples
    assert ann.get_start_time_sec(first_capture_id) == 0.2


def test_get_end_time_sec(tmpdir):
    """Test getting end time in seconds."""
    sigmf_path = generate_test_sigmffile(tmpdir)
    cache_manager = CacheManager(base_path=Path(tmpdir/"cache"))
    lfc = LoadedFilesCollection(cache_manager=cache_manager)
    lf = lfc.load_file(sigmf_path)
    
    annotations = lf.get_annotations_dict()
    ann = list(annotations.values())[0]
    
    capture_ids = list(lf._capture_id_to_capture.keys())
    first_capture_id = capture_ids[0]
    second_capture_id = capture_ids[1]
    
    # Test getting end time for first capture
    end_time = ann.get_end_time_sec(first_capture_id)
    assert end_time == 0.6  # (100,000 + 500,000) samples / 1e6 samples/sec = 0.6 sec
    
    # Annotation is not in second capture
    end_time = ann.get_end_time_sec(second_capture_id)
    assert end_time is None


def test_set_end_time_sec(tmpdir):
    """Test setting end time in seconds."""
    sigmf_path = generate_test_sigmffile(tmpdir)
    cache_manager = CacheManager(base_path=Path(tmpdir/"cache"))
    lfc = LoadedFilesCollection(cache_manager=cache_manager)
    lf = lfc.load_file(sigmf_path)
    
    annotations = lf.get_annotations_dict()
    ann = list(annotations.values())[0]
    
    capture_ids = list(lf._capture_id_to_capture.keys())
    first_capture_id = capture_ids[0]
    
    # Set end time to 0.8 seconds
    ann.set_end_time_sec(first_capture_id, 0.8)
    
    # Verify the change
    # Start is at 100k, end at 0.8s = 800k samples, so length = 700k
    assert ann[SigMFFile.LENGTH_INDEX_KEY] == 700_000
    assert ann.get_end_time_sec(first_capture_id) == 0.8


def test_set_end_time_sec_before_start_raises_error(tmpdir):
    """Test that setting end time before start time raises an error."""
    sigmf_path = generate_test_sigmffile(tmpdir)
    cache_manager = CacheManager(base_path=Path(tmpdir/"cache"))
    lfc = LoadedFilesCollection(cache_manager=cache_manager)
    lf = lfc.load_file(sigmf_path)
    
    annotations = lf.get_annotations_dict()
    ann = list(annotations.values())[0]
    
    capture_ids = list(lf._capture_id_to_capture.keys())
    first_capture_id = capture_ids[0]
    
    # Try to set end time before start time (start is at 0.1s)
    with pytest.raises(ValueError, match="End time must be greater than start time"):
        ann.set_end_time_sec(first_capture_id, 0.05)


def test_duration_sec_getter(tmpdir):
    """Test getting duration in seconds."""
    sigmf_path = generate_test_sigmffile(tmpdir)
    cache_manager = CacheManager(base_path=Path(tmpdir/"cache"))
    lfc = LoadedFilesCollection(cache_manager=cache_manager)
    lf = lfc.load_file(sigmf_path)
    
    annotations = lf.get_annotations_dict()
    ann = list(annotations.values())[0]
    
    # Duration should be 500,000 samples / 1e6 samples/sec = 0.5 sec
    assert ann.duration_sec == 0.5


def test_duration_sec_setter(tmpdir):
    """Test setting duration in seconds."""
    sigmf_path = generate_test_sigmffile(tmpdir)
    cache_manager = CacheManager(base_path=Path(tmpdir/"cache"))
    lfc = LoadedFilesCollection(cache_manager=cache_manager)
    lf = lfc.load_file(sigmf_path)
    
    annotations = lf.get_annotations_dict()
    ann = list(annotations.values())[0]
    
    # Set duration to 0.3 seconds
    ann.duration_sec = 0.3
    
    # Verify the change
    assert ann[SigMFFile.LENGTH_INDEX_KEY] == 300_000  # 0.3 sec * 1e6 samples/sec
    assert ann.duration_sec == 0.3


def test_duration_sec_setter_invalid_value(tmpdir):
    """Test that setting invalid duration raises an error."""
    sigmf_path = generate_test_sigmffile(tmpdir)
    cache_manager = CacheManager(base_path=Path(tmpdir/"cache"))
    lfc = LoadedFilesCollection(cache_manager=cache_manager)
    lf = lfc.load_file(sigmf_path)
    
    annotations = lf.get_annotations_dict()
    ann = list(annotations.values())[0]
    
    # Try to set negative duration
    with pytest.raises(ValueError, match="Duration must be positive"):
        ann.duration_sec = -0.1


def test_center_frequency_Hz_getter(tmpdir):
    """Test getting center frequency in Hz."""
    sigmf_path = generate_test_sigmffile(tmpdir)
    cache_manager = CacheManager(base_path=Path(tmpdir/"cache"))
    lfc = LoadedFilesCollection(cache_manager=cache_manager)
    lf = lfc.load_file(sigmf_path)
    
    annotations = lf.get_annotations_dict()
    ann = list(annotations.values())[0]
    
    # Center frequency should be (2.4e9 - 100e3 + 2.4e9 + 100e3) / 2 = 2.4e9
    assert ann.center_frequency_Hz == 2.4e9


def test_center_frequency_Hz_setter(tmpdir):
    """Test setting center frequency in Hz."""
    sigmf_path = generate_test_sigmffile(tmpdir)
    cache_manager = CacheManager(base_path=Path(tmpdir/"cache"))
    lfc = LoadedFilesCollection(cache_manager=cache_manager)
    lf = lfc.load_file(sigmf_path)
    
    annotations = lf.get_annotations_dict()
    ann = list(annotations.values())[0]
    
    # Set center frequency to 2.5 GHz (keeping bandwidth the same)
    ann.center_frequency_Hz = 2.5e9
    
    # Verify the change (bandwidth should remain 200 kHz)
    assert ann[SigMFFile.FLO_KEY] == 2.5e9 - 100e3
    assert ann[SigMFFile.FHI_KEY] == 2.5e9 + 100e3
    assert ann.center_frequency_Hz == 2.5e9
    assert ann.bandwidth_Hz == 200e3


def test_bandwidth_Hz_getter(tmpdir):
    """Test getting bandwidth in Hz."""
    sigmf_path = generate_test_sigmffile(tmpdir)
    cache_manager = CacheManager(base_path=Path(tmpdir/"cache"))
    lfc = LoadedFilesCollection(cache_manager=cache_manager)
    lf = lfc.load_file(sigmf_path)
    
    annotations = lf.get_annotations_dict()
    ann = list(annotations.values())[0]
    
    # Bandwidth should be (2.4e9 + 100e3) - (2.4e9 - 100e3) = 200e3
    assert ann.bandwidth_Hz == 200e3


def test_bandwidth_Hz_setter(tmpdir):
    """Test setting bandwidth in Hz."""
    sigmf_path = generate_test_sigmffile(tmpdir)
    cache_manager = CacheManager(base_path=Path(tmpdir/"cache"))
    lfc = LoadedFilesCollection(cache_manager=cache_manager)
    lf = lfc.load_file(sigmf_path)
    
    annotations = lf.get_annotations_dict()
    ann = list(annotations.values())[0]
    
    # Set bandwidth to 500 kHz (keeping center frequency the same)
    ann.bandwidth_Hz = 500e3
    
    # Verify the change (center should remain 2.4 GHz)
    assert ann[SigMFFile.FLO_KEY] == 2.4e9 - 250e3
    assert ann[SigMFFile.FHI_KEY] == 2.4e9 + 250e3
    assert ann.center_frequency_Hz == 2.4e9
    assert ann.bandwidth_Hz == 500e3


def test_bandwidth_Hz_setter_invalid_value(tmpdir):
    """Test that setting negative bandwidth raises an error."""
    sigmf_path = generate_test_sigmffile(tmpdir)
    cache_manager = CacheManager(base_path=Path(tmpdir/"cache"))
    lfc = LoadedFilesCollection(cache_manager=cache_manager)
    lf = lfc.load_file(sigmf_path)
    
    annotations = lf.get_annotations_dict()
    ann = list(annotations.values())[0]
    
    # Try to set negative bandwidth
    with pytest.raises(ValueError, match="Bandwidth must be non-negative"):
        ann.bandwidth_Hz = -100e3


def test_bandwidth_Hz_setter_without_center_frequency(tmpdir):
    """Test that setting bandwidth without center frequency raises an error."""
    sigmf_path = generate_test_sigmffile(tmpdir)
    cache_manager = CacheManager(base_path=Path(tmpdir/"cache"))
    lfc = LoadedFilesCollection(cache_manager=cache_manager)
    lf = lfc.load_file(sigmf_path)
    
    annotations = lf.get_annotations_dict()
    ann = list(annotations.values())[0]
    
    # Remove frequency keys
    del ann[SigMFFile.FLO_KEY]
    del ann[SigMFFile.FHI_KEY]
    
    # Try to set bandwidth without center frequency
    with pytest.raises(ValueError, match="Cannot set bandwidth without a center frequency"):
        ann.bandwidth_Hz = 100e3


def test_center_frequency_Hz_setter_without_bandwidth(tmpdir):
    """Test setting center frequency when bandwidth is not set."""
    sigmf_path = generate_test_sigmffile(tmpdir)
    cache_manager = CacheManager(base_path=Path(tmpdir/"cache"))
    lfc = LoadedFilesCollection(cache_manager=cache_manager)
    lf = lfc.load_file(sigmf_path)
    
    annotations = lf.get_annotations_dict()
    ann = list(annotations.values())[0]
    
    # Remove frequency keys
    del ann[SigMFFile.FLO_KEY]
    del ann[SigMFFile.FHI_KEY]
    
    # Set center frequency (should default to 0 bandwidth)
    ann.center_frequency_Hz = 2.5e9
    
    # Verify the change (bandwidth should be 0)
    assert ann[SigMFFile.FLO_KEY] == 2.5e9
    assert ann[SigMFFile.FHI_KEY] == 2.5e9
    assert ann.center_frequency_Hz == 2.5e9
    assert ann.bandwidth_Hz == 0.0


def test_getters_return_none_when_keys_missing(tmpdir):
    """Test that getters return None when required keys are missing."""
    sigmf_path = generate_test_sigmffile(tmpdir)
    cache_manager = CacheManager(base_path=Path(tmpdir/"cache"))
    lfc = LoadedFilesCollection(cache_manager=cache_manager)
    lf = lfc.load_file(sigmf_path)
    
    annotations = lf.get_annotations_dict()
    ann = list(annotations.values())[0]
    
    # Remove LENGTH_INDEX_KEY
    del ann[SigMFFile.LENGTH_INDEX_KEY]
    assert ann.duration_sec is None
    
    # Remove frequency keys
    del ann[SigMFFile.FLO_KEY]
    del ann[SigMFFile.FHI_KEY]
    assert ann.center_frequency_Hz is None
    assert ann.bandwidth_Hz is None


def test_notification_triggered_on_setters(tmpdir):
    """Test that setters trigger the change notification system."""
    sigmf_path = generate_test_sigmffile(tmpdir)
    
    callbacks = []
    def callback(annotation_id, action):
        callbacks.append((annotation_id, action))
    
    cache_manager = CacheManager(base_path=Path(tmpdir/"cache"))
    lfc = LoadedFilesCollection(cache_manager=cache_manager)
    lfc.set_annotation_changed_callback(callback)
    lf = lfc.load_file(sigmf_path)
    
    annotations = lf.get_annotations_dict()
    ann = list(annotations.values())[0]
    
    capture_ids = list(lf._capture_id_to_capture.keys())
    first_capture_id = capture_ids[0]
    
    # Clear callbacks from loading
    callbacks.clear()
    
    # Test that each setter triggers a notification
    ann.duration_sec = 0.3
    assert len(callbacks) > 0
    
    callbacks.clear()
    ann.center_frequency_Hz = 2.5e9
    assert len(callbacks) > 0
    
    callbacks.clear()
    ann.bandwidth_Hz = 500e3
    assert len(callbacks) > 0
    
    callbacks.clear()
    ann.set_start_time_sec(first_capture_id, 0.15)
    assert len(callbacks) > 0
    
    callbacks.clear()
    ann.set_end_time_sec(first_capture_id, 0.75)
    assert len(callbacks) > 0
