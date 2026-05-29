from sigmf import SigMFFile
import numpy as np
from pathlib import Path
from unittest.mock import Mock
import pytest

from specview.loaded_file_mgmt import LoadedFilesCollection, CacheManager
from specview.app_state import AppState
from specview.menu import create_annotation_from_selection


def generate_test_sigmffile(tmpdir) -> Path:
    """Generate a test SigMF file for testing."""
    TOTAL_NUM_SAMPLES = 2_000_000
    np.zeros(TOTAL_NUM_SAMPLES, dtype=np.complex64).tofile(tmpdir / "test.sigmf-data")
    
    smf = SigMFFile()
    smf.set_global_field(SigMFFile.DATATYPE_KEY, "cf32_le")
    smf.set_global_field(SigMFFile.SAMPLE_RATE_KEY, 1e6)  # 1 MHz sample rate
    smf.add_capture(start_index=0, metadata={SigMFFile.FREQUENCY_KEY: 2.4e9})
    
    smf.set_data_file(str(tmpdir / "test.sigmf-data"))
    smf.tofile(tmpdir / "test.sigmf-meta")
    
    return Path(tmpdir / "test.sigmf-meta")


def test_create_annotation_with_time_only(tmpdir, monkeypatch):
    """Test creating an annotation with only time selection."""
    sigmf_path = generate_test_sigmffile(tmpdir)
    cache_manager = CacheManager(base_path=Path(tmpdir/"cache"))
    lfc = LoadedFilesCollection(cache_manager=cache_manager)
    lf = lfc.load_file(sigmf_path)
    
    # Get the first capture ID
    capture_ids = list(lf._capture_id_to_capture.keys())
    first_capture_id = capture_ids[0]
    
    # Mock AppState
    mock_app = Mock()
    mock_app.app_state = Mock(spec=AppState)
    mock_app.app_state._time_interval = (0.1, 0.6)  # 0.1s to 0.6s
    mock_app.app_state._frequency_interval = None
    mock_app.app_state._selected_capture = first_capture_id
    mock_app.app_state.get_capture_by_id.return_value = lf._capture_id_to_capture[first_capture_id]
    
    # Patch QApplication.instance()
    monkeypatch.setattr('specview.menu.QApplication.instance', lambda: mock_app)
    
    # Create annotation
    create_annotation_from_selection()
    
    # Verify annotation was created
    annotations = lf.get_annotations_dict()
    assert len(annotations) == 1
    
    ann = list(annotations.values())[0]
    assert ann[SigMFFile.START_INDEX_KEY] == 100_000  # 0.1s * 1e6 samples/sec
    assert ann[SigMFFile.LENGTH_INDEX_KEY] == 500_000  # (0.6 - 0.1) * 1e6 samples/sec
    assert SigMFFile.LABEL_KEY in ann
    assert "Changeme" in ann[SigMFFile.LABEL_KEY]
    assert SigMFFile.FLO_KEY not in ann
    assert SigMFFile.FHI_KEY not in ann


def test_create_annotation_with_time_and_frequency(tmpdir, monkeypatch):
    """Test creating an annotation with both time and frequency selections."""
    sigmf_path = generate_test_sigmffile(tmpdir)
    cache_manager = CacheManager(base_path=Path(tmpdir/"cache"))
    lfc = LoadedFilesCollection(cache_manager=cache_manager)
    lf = lfc.load_file(sigmf_path)
    
    # Get the first capture ID
    capture_ids = list(lf._capture_id_to_capture.keys())
    first_capture_id = capture_ids[0]
    
    # Mock AppState
    mock_app = Mock()
    mock_app.app_state = Mock(spec=AppState)
    mock_app.app_state._time_interval = (0.1, 0.6)  # 0.1s to 0.6s
    mock_app.app_state._frequency_interval = (2.4e9 - 100e3, 2.4e9 + 100e3)  # ±100kHz
    mock_app.app_state._selected_capture = first_capture_id
    mock_app.app_state.get_capture_by_id.return_value = lf._capture_id_to_capture[first_capture_id]
    
    # Patch QApplication.instance()
    monkeypatch.setattr('specview.menu.QApplication.instance', lambda: mock_app)
    
    # Create annotation
    create_annotation_from_selection()
    
    # Verify annotation was created
    annotations = lf.get_annotations_dict()
    assert len(annotations) == 1
    
    ann = list(annotations.values())[0]
    assert ann[SigMFFile.START_INDEX_KEY] == 100_000  # 0.1s * 1e6 samples/sec
    assert ann[SigMFFile.LENGTH_INDEX_KEY] == 500_000  # (0.6 - 0.1) * 1e6 samples/sec
    assert ann[SigMFFile.FLO_KEY] == 2.4e9 - 100e3
    assert ann[SigMFFile.FHI_KEY] == 2.4e9 + 100e3
    assert SigMFFile.LABEL_KEY in ann
    assert "Changeme" in ann[SigMFFile.LABEL_KEY]


def test_create_annotation_no_time_selection(tmpdir, monkeypatch):
    """Test that creating an annotation without time selection does nothing."""
    sigmf_path = generate_test_sigmffile(tmpdir)
    cache_manager = CacheManager(base_path=Path(tmpdir/"cache"))
    lfc = LoadedFilesCollection(cache_manager=cache_manager)
    lf = lfc.load_file(sigmf_path)
    
    # Get the first capture ID
    capture_ids = list(lf._capture_id_to_capture.keys())
    first_capture_id = capture_ids[0]
    
    # Mock AppState with no time selection
    mock_app = Mock()
    mock_app.app_state = Mock(spec=AppState)
    mock_app.app_state._time_interval = None  # No time selection
    mock_app.app_state._frequency_interval = (2.4e9 - 100e3, 2.4e9 + 100e3)
    mock_app.app_state._selected_capture = first_capture_id
    mock_app.app_state.get_capture_by_id.return_value = lf._capture_id_to_capture[first_capture_id]
    
    # Patch QApplication.instance()
    monkeypatch.setattr('specview.menu.QApplication.instance', lambda: mock_app)
    
    # Create annotation
    create_annotation_from_selection()
    
    # Verify no annotation was created
    annotations = lf.get_annotations_dict()
    assert len(annotations) == 0


def test_create_annotation_no_capture_selected(tmpdir, monkeypatch):
    """Test that creating an annotation without a capture selected does nothing."""
    sigmf_path = generate_test_sigmffile(tmpdir)
    cache_manager = CacheManager(base_path=Path(tmpdir/"cache"))
    lfc = LoadedFilesCollection(cache_manager=cache_manager)
    lf = lfc.load_file(sigmf_path)
    
    # Mock AppState with no capture selected
    mock_app = Mock()
    mock_app.app_state = Mock(spec=AppState)
    mock_app.app_state._time_interval = (0.1, 0.6)
    mock_app.app_state._frequency_interval = None
    mock_app.app_state._selected_capture = None  # No capture selected
    
    # Patch QApplication.instance()
    monkeypatch.setattr('specview.menu.QApplication.instance', lambda: mock_app)
    
    # Create annotation
    create_annotation_from_selection()
    
    # Verify no annotation was created
    annotations = lf.get_annotations_dict()
    assert len(annotations) == 0
