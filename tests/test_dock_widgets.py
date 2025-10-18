"""Tests for dock widget functionality."""
import pytest
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QSettings, QThreadPool
from specview.main import MainWindow
from specview.app_state import AppState


@pytest.fixture
def app_with_window(qtbot):
    """Create QApplication with MainWindow for testing."""
    # Initialize app_state
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    
    if not hasattr(app, 'app_state'):
        app.app_state = AppState(parent=app)
    if not hasattr(app, 'thread_pool'):
        app.thread_pool = QThreadPool()
        app.thread_pool.setMaxThreadCount(4)
    
    # Clear settings before test
    settings = QSettings("SpecView", "SpecView")
    settings.clear()
    
    # Create window
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()  # Show the window so docks are visible
    
    yield window
    
    # Cleanup
    window.close()
    settings.clear()


def test_dock_widgets_exist(app_with_window):
    """Test that all dock widgets are created."""
    window = app_with_window
    
    assert window.time_dock is not None
    assert window.specan_dock is not None
    assert window.waterfall_dock is not None
    assert window.annotation_dock is not None
    assert window.captures_dock is not None


def test_dock_widgets_visible_by_default(app_with_window):
    """Test that all dock widgets are visible by default."""
    window = app_with_window
    
    assert window.time_dock.isVisible()
    assert window.specan_dock.isVisible()
    assert window.waterfall_dock.isVisible()
    assert window.annotation_dock.isVisible()
    assert window.captures_dock.isVisible()


def test_dock_widgets_not_floating_by_default(app_with_window):
    """Test that dock widgets are not floating by default."""
    window = app_with_window
    
    assert not window.time_dock.isFloating()
    assert not window.specan_dock.isFloating()
    assert not window.waterfall_dock.isFloating()
    assert not window.annotation_dock.isFloating()
    assert not window.captures_dock.isFloating()


def test_dock_widget_can_be_hidden(app_with_window):
    """Test that dock widgets can be hidden."""
    window = app_with_window
    
    window.time_dock.hide()
    assert not window.time_dock.isVisible()


def test_dock_widget_can_be_floated(app_with_window):
    """Test that dock widgets can be floated."""
    window = app_with_window
    
    window.waterfall_dock.setFloating(True)
    assert window.waterfall_dock.isFloating()


def test_reset_layout_restores_visibility(app_with_window):
    """Test that reset_layout makes all docks visible."""
    window = app_with_window
    
    # Hide a dock
    window.time_dock.hide()
    assert not window.time_dock.isVisible()
    
    # Reset layout
    window.reset_layout()
    
    # Check all docks are visible
    assert window.time_dock.isVisible()
    assert window.specan_dock.isVisible()
    assert window.waterfall_dock.isVisible()
    assert window.annotation_dock.isVisible()
    assert window.captures_dock.isVisible()


def test_reset_layout_restores_docked_state(app_with_window):
    """Test that reset_layout makes all docks non-floating."""
    window = app_with_window
    
    # Float a dock
    window.waterfall_dock.setFloating(True)
    assert window.waterfall_dock.isFloating()
    
    # Reset layout
    window.reset_layout()
    
    # Check all docks are not floating
    assert not window.time_dock.isFloating()
    assert not window.specan_dock.isFloating()
    assert not window.waterfall_dock.isFloating()
    assert not window.annotation_dock.isFloating()
    assert not window.captures_dock.isFloating()


def test_dock_widgets_have_object_names(app_with_window):
    """Test that dock widgets have object names set for state persistence."""
    window = app_with_window
    
    assert window.time_dock.objectName() == "TimeView"
    assert window.specan_dock.objectName() == "SpectrumAnalyzer"
    assert window.waterfall_dock.objectName() == "Waterfall"
    assert window.annotation_dock.objectName() == "Annotations"
    assert window.captures_dock.objectName() == "Captures"
