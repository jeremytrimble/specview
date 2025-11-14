"""Tests for annotations table sorting functionality."""
import pytest
from PyQt5.QtCore import Qt, QThreadPool, QModelIndex
from PyQt5.QtWidgets import QApplication
import numpy as np
from pathlib import Path
from sigmf import SigMFFile

from specview.annotations_table import AnnotationsModel, AnnotationsTable
from specview.loaded_file_mgmt import LoadedFilesCollection
from specview.app_state import AppState


@pytest.fixture
def qapp():
    """Create QApplication with AppState for testing."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    
    if not hasattr(app, 'app_state'):
        app.app_state = AppState(parent=app)
    if not hasattr(app, 'thread_pool'):
        app.thread_pool = QThreadPool()
        app.thread_pool.setMaxThreadCount(4)
    
    yield app


def generate_test_sigmffile_with_multiple_annotations(tmpdir) -> Path:
    """Generate a test SigMF file with multiple annotations for sorting tests."""
    TOTAL_NUM_SAMPLES = 3_000_000
    np.zeros(TOTAL_NUM_SAMPLES, dtype=np.complex64).tofile(tmpdir / "test.sigmf-data")
    
    smf = SigMFFile()
    smf.set_global_field(SigMFFile.DATATYPE_KEY, "cf32_le")
    smf.set_global_field(SigMFFile.SAMPLE_RATE_KEY, 1e6)  # 1 MHz sample rate
    smf.add_capture(start_index=0, metadata={SigMFFile.FREQUENCY_KEY: 2.4e9})
    
    smf.set_data_file(str(tmpdir / "test.sigmf-data"))
    
    # Add multiple annotations with different properties for testing sorting
    # Annotation 1: Label "Zebra", starts at 0.1s, duration 0.5s, center freq 2.4GHz
    smf.add_annotation(start_index=100_000, length=500_000, metadata={
        SigMFFile.LABEL_KEY: "Zebra",
        SigMFFile.FLO_KEY: 2.4e9 - 100e3,
        SigMFFile.FHI_KEY: 2.4e9 + 100e3,
    })
    
    # Annotation 2: Label "Apple", starts at 0.8s, duration 0.2s, center freq 2.5GHz
    smf.add_annotation(start_index=800_000, length=200_000, metadata={
        SigMFFile.LABEL_KEY: "Apple",
        SigMFFile.FLO_KEY: 2.5e9 - 50e3,
        SigMFFile.FHI_KEY: 2.5e9 + 50e3,
    })
    
    # Annotation 3: Label "Banana", starts at 0.3s, duration 0.4s, center freq 2.3GHz
    smf.add_annotation(start_index=300_000, length=400_000, metadata={
        SigMFFile.LABEL_KEY: "Banana",
        SigMFFile.FLO_KEY: 2.3e9 - 150e3,
        SigMFFile.FHI_KEY: 2.3e9 + 150e3,
    })
    
    # Annotation 4: No label, starts at 0.05s, duration 0.1s, no frequency info
    smf.add_annotation(start_index=50_000, length=100_000, metadata={})
    
    smf.tofile(tmpdir / "test.sigmf-meta")
    
    return Path(tmpdir / "test.sigmf-meta")


def test_model_user_role_returns_comparable_values(qapp, tmpdir):
    """Test that AnnotationsModel returns comparable values for Qt.UserRole."""
    sigmf_path = generate_test_sigmffile_with_multiple_annotations(tmpdir)
    lfc = LoadedFilesCollection()
    lf = lfc.load_file(sigmf_path)
    
    # Set up app state with the loaded file
    app_state = qapp.app_state
    app_state._loaded_files = lfc
    capture_id = list(lf._capture_id_to_capture.keys())[0]
    app_state.selected_capture_changed.emit(capture_id)
    
    model = AnnotationsModel()
    model._current_capture_id = capture_id
    
    # Test that UserRole returns numeric values for time columns
    index_start_time = model.createIndex(0, 2)  # Start Time column
    start_time_value = model.data(index_start_time, Qt.UserRole)
    assert isinstance(start_time_value, float), "Start time UserRole should return float"
    
    # Test that UserRole returns numeric values for frequency columns
    index_center_freq = model.createIndex(0, 6)  # Center Freq column
    center_freq_value = model.data(index_center_freq, Qt.UserRole)
    assert isinstance(center_freq_value, (float, int)), "Center freq UserRole should return numeric"
    
    # Test that UserRole returns string for label column
    index_label = model.createIndex(0, 1)  # Label column
    label_value = model.data(index_label, Qt.UserRole)
    assert isinstance(label_value, str), "Label UserRole should return string"
    
    # Test that missing numeric values return inf
    row_with_no_freq = None
    for row in range(model.rowCount(None)):
        idx = model.createIndex(row, 6)
        val = model.data(idx, Qt.UserRole)
        if val == float('inf'):
            row_with_no_freq = row
            break
    
    # Annotation 4 has no frequency info, so it should return inf
    assert row_with_no_freq is not None, "Should have at least one annotation with missing frequency"


def test_model_display_role_unchanged(qapp, tmpdir):
    """Test that DisplayRole still returns formatted strings."""
    sigmf_path = generate_test_sigmffile_with_multiple_annotations(tmpdir)
    lfc = LoadedFilesCollection()
    lf = lfc.load_file(sigmf_path)
    
    app_state = qapp.app_state
    app_state._loaded_files = lfc
    capture_id = list(lf._capture_id_to_capture.keys())[0]
    app_state.selected_capture_changed.emit(capture_id)
    
    model = AnnotationsModel()
    model._current_capture_id = capture_id
    
    # Test that DisplayRole returns formatted strings
    index_start_time = model.createIndex(0, 2)  # Start Time column
    display_value = model.data(index_start_time, Qt.DisplayRole)
    assert isinstance(display_value, str), "DisplayRole should return string"
    assert display_value != "--", "DisplayRole should have formatted time"
    
    # Test that missing values show "--"
    # Find row with missing frequency
    for row in range(model.rowCount(None)):
        idx = model.createIndex(row, 6)  # Center Freq column
        user_val = model.data(idx, Qt.UserRole)
        if user_val == float('inf'):
            display_val = model.data(idx, Qt.DisplayRole)
            assert display_val == "--", "Missing numeric values should display as '--'"
            break

def test_header_click_toggle(qapp, tmpdir):
    """Test that clicking the same header toggles sort order."""
    sigmf_path = generate_test_sigmffile_with_multiple_annotations(tmpdir)
    lfc = LoadedFilesCollection()
    lf = lfc.load_file(sigmf_path)
    
    app_state = qapp.app_state
    app_state._loaded_files = lfc
    capture_id = list(lf._capture_id_to_capture.keys())[0]
    app_state.selected_capture_changed.emit(capture_id)
    
    table = AnnotationsTable()
    table.model._current_capture_id = capture_id
    
    # Initial state
    assert table._current_sort_column == -1
    assert table._current_sort_order == Qt.AscendingOrder
    
    # Click column 1 (Label) - should sort ascending
    table._on_header_clicked(1)
    assert table._current_sort_column == 1
    assert table._current_sort_order == Qt.AscendingOrder
    
    # Click column 1 again - should toggle to descending
    table._on_header_clicked(1)
    assert table._current_sort_column == 1
    assert table._current_sort_order == Qt.DescendingOrder
    
    # Click column 1 again - should toggle back to ascending
    table._on_header_clicked(1)
    assert table._current_sort_column == 1
    assert table._current_sort_order == Qt.AscendingOrder
    
    # Click different column (1) - should reset to ascending
    table._on_header_clicked(2)
    assert table._current_sort_column == 2
    assert table._current_sort_order == Qt.AscendingOrder


def test_numeric_sorting_with_missing_values(qapp, tmpdir):
    """Test that numeric columns sort with missing values at the end."""
    sigmf_path = generate_test_sigmffile_with_multiple_annotations(tmpdir)
    lfc = LoadedFilesCollection()
    lf = lfc.load_file(sigmf_path)
    
    app_state = qapp.app_state
    app_state._loaded_files = lfc
    capture_id = list(lf._capture_id_to_capture.keys())[0]
    app_state.selected_capture_changed.emit(capture_id)
    
    table = AnnotationsTable()
    table.model._current_capture_id = capture_id
    
    # Sort by Start Time (column 2) ascending
    table.proxy_model.sort(2, Qt.AscendingOrder)
    
    # Get start times in sorted order
    start_times = []
    for row in range(table.proxy_model.rowCount()):
        index = table.proxy_model.index(row, 2)
        user_val = table.proxy_model.data(index, Qt.UserRole)
        start_times.append(user_val)
    
    # Check that times are sorted in ascending order
    for i in range(len(start_times) - 1):
        assert start_times[i] <= start_times[i + 1], "Start times should be in ascending order"
    