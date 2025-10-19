from PyQt5.QtCore import QSize, Qt, QThread, pyqtSignal, QObject, QTimer, QThreadPool, QSettings
from PyQt5.QtWidgets import QApplication, QMainWindow, QGridLayout, QWidget, QSlider, QLabel, QHBoxLayout, QVBoxLayout, QPushButton, QComboBox, QDockWidget  # tested with PyQt6==6.7.0
import pyqtgraph as pg # tested with pyqtgraph==0.13.7
import numpy as np
import signal # TODO: let control-C actually close the app


import sigmf
import logging

from pathlib import Path
import argparse
import sys

from specview.version import get_version_info
from specview.util import measure_runtime

from .time_view import TimeView
from .specan_view import SpecanView
from .waterfall_view import WaterfallView
from .app_state import AppState
from .monotonic_axis import MonotonicAxis
from .annotations_table import AnnotationsTable
from .captures_panel import CapturesPanel
from .ui_constants import SETTINGS_ORGANIZATION, SETTINGS_APPLICATION

log = logging.getLogger("specview")


from .menu import populate_menubar

if 0:
    import warnings
    # Treat RuntimeWarnings as errors
    warnings.simplefilter('error', RuntimeWarning)



# Subclass QMainWindow to customize your application's main window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # Get version info and set window title
        version_info = get_version_info()
        self.setWindowTitle(f"Specview v{version_info.version}")

        layout = QGridLayout() # overall layout

        self.time_view = TimeView(parent=self)
        self.specan_view = SpecanView(parent=self)
        self.waterfall_view = WaterfallView(parent=self)
        self.annotation_table = AnnotationsTable(parent=self)
        self.captures_panel = CapturesPanel(parent=self)

        # Create dock widgets for each view
        self.time_dock = self._create_dock_widget("Time View", self.time_view)
        self.specan_dock = self._create_dock_widget("Spectrum Analyzer", self.specan_view)
        self.waterfall_dock = self._create_dock_widget("Waterfall", self.waterfall_view)
        self.annotation_dock = self._create_dock_widget("Annotations", self.annotation_table)
        self.captures_dock = self._create_dock_widget("Captures", self.captures_panel)

        self.time_dock.sizePolicy().setVerticalStretch(1)
        self.specan_dock.sizePolicy().setVerticalStretch(1)
        self.waterfall_dock.sizePolicy().setVerticalStretch(2)

        # Set up default dock layout
        self._setup_default_layout()

        # Create a dummy central widget (required by QMainWindow)
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        central_widget.hide()  # Hide it since we're using docks

        # Populate menu bar after dock widgets are created
        self._menubar = self.menuBar()
        populate_menubar(self._menubar, self)

        self._statusbar = self.statusBar()
        self._statusbar.showMessage("Ready")  # Initial message in the status bar

        self._connect_app_signals()

        # Load saved geometry and state, or use defaults
        self._load_window_state()

    def _create_dock_widget(self, title: str, widget: QWidget) -> QDockWidget:
        """Create a dock widget with the given title and widget."""
        dock = QDockWidget(title, self)
        dock.setObjectName(title.replace(" ", ""))  # Set object name for state saving
        dock.setWidget(widget)
        dock.setAllowedAreas(Qt.AllDockWidgetAreas)
        dock.setFeatures(QDockWidget.DockWidgetMovable | 
                        QDockWidget.DockWidgetFloatable | 
                        QDockWidget.DockWidgetClosable)
        return dock

    def _setup_default_layout(self):
        """Set up the default dock widget layout."""
        # Add docks to main window in default positions
        self.addDockWidget(Qt.TopDockWidgetArea, self.time_dock, Qt.Vertical)
        self.addDockWidget(Qt.TopDockWidgetArea, self.specan_dock, Qt.Vertical)
        self.addDockWidget(Qt.TopDockWidgetArea, self.waterfall_dock, Qt.Vertical)

        self.addDockWidget(Qt.TopDockWidgetArea, self.captures_dock, Qt.Vertical)
        self.addDockWidget(Qt.TopDockWidgetArea, self.annotation_dock, Qt.Vertical)
        self.tabifyDockWidget(self.captures_dock, self.annotation_dock)

        self.resizeDocks([self.time_dock, self.specan_dock, self.waterfall_dock, self.captures_dock, self.annotation_dock], [1, 1, 2, 1,1], Qt.Vertical)
        
    def _load_window_state(self):
        """Load window geometry and dock widget state from settings."""
        settings = QSettings(SETTINGS_ORGANIZATION, SETTINGS_APPLICATION)
        
        # Restore window geometry
        geometry = settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        else:
            self.resize(QSize(2000, 1500))
        
        # Restore dock widget state
        state = settings.value("windowState")
        if state is not None:
            self.restoreState(state)
    
    def _save_window_state(self):
        """Save window geometry and dock widget state to settings."""
        settings = QSettings(SETTINGS_ORGANIZATION, SETTINGS_APPLICATION)
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("windowState", self.saveState())
    
    def reset_layout(self):
        """Reset dock widgets to default layout."""
        # Clear settings
        settings = QSettings(SETTINGS_ORGANIZATION, SETTINGS_APPLICATION)
        settings.remove("geometry")
        settings.remove("windowState")
        
        # Remove all docks
        self.removeDockWidget(self.time_dock)
        self.removeDockWidget(self.specan_dock)
        self.removeDockWidget(self.waterfall_dock)
        self.removeDockWidget(self.annotation_dock)
        self.removeDockWidget(self.captures_dock)
        
        # Make all docks non-floating (must be after adding them)
        self.time_dock.setFloating(False)
        self.specan_dock.setFloating(False)
        self.waterfall_dock.setFloating(False)
        self.annotation_dock.setFloating(False)
        self.captures_dock.setFloating(False)
        
        # Show all docks
        self.time_dock.show()
        self.specan_dock.show()
        self.waterfall_dock.show()
        self.annotation_dock.show()
        self.captures_dock.show()

        # Re-add them in default configuration
        self._setup_default_layout()
        
        # Reset window size
        self.resize(QSize(2000, 1500))
    
    def closeEvent(self, event):
        """Save state before closing."""
        self._save_window_state()
        super().closeEvent(event)

    def _connect_app_signals(self):
        app_state = QApplication.instance().app_state
        app_state.cursor_frequency_changed.connect(self._update_status_bar)
        app_state.cursor_time_changed.connect(self._update_status_bar)
        app_state.frequency_interval_changed.connect(self._update_status_bar)
        app_state.time_interval_changed.connect(self._update_status_bar)

    def _update_status_bar(self):
        app_state = QApplication.instance().app_state

        msg = ""
        if app_state._frequency_interval is not None:
            msg += f"Freq: [ {app_state._frequency_interval[0]/1e6:.2f} : {app_state._frequency_interval[1]/1e6:.2f} MHz ]"
        elif app_state._cursor_frequency is not None:
            msg += f"Freq: {app_state._cursor_frequency/1e6:.2f} MHz"
        else:
            msg += f"Freq: --"

        msg += " | "

        if app_state._time_interval is not None:
            msg += f"Time: [ {app_state._time_interval[0]:.2f} : {app_state._time_interval[1]:.2f} ] sec"
        elif app_state._cursor_time is not None:
            msg += f"Time: {app_state._cursor_time:.2f} sec"
        else:
            msg += f"Time: --"

        self._statusbar.showMessage(msg)

def parse_args():
    parser = argparse.ArgumentParser(prog="specview", description="Display and annotate SigMF files")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                      default="WARNING", help="Set the logging level (default: INFO)")
    parser.add_argument("--version", action="version", version=str(get_version_info()))
    parser.add_argument("files", nargs="*", default=[], help="Path to SigMF file(s) to open.")

    return parser.parse_args()

def main():
    args = parse_args()

    # Set up logging with the specified level
    log_level = getattr(logging, args.log_level)
    logging.basicConfig(level=log_level)

    log.debug(f"Command line arguments: {args}")

    app = QApplication([])
    app_state = app.app_state = AppState(parent=app)
    app.thread_pool = QThreadPool()
    app.thread_pool.setMaxThreadCount(4) # TODO: make configurable?

    window = MainWindow()
    window.show() # Windows are hidden by default
    signal.signal(signal.SIGINT, signal.SIG_DFL) # this lets control-C actually close the app

    for filepath in args.files:
        filepath = Path(filepath)
        with measure_runtime(f"loading {filepath}"):
            app_state.load_sigmf_file(filepath)

    app.exec() # Start the event loop


if __name__ == "__main__":
    main()
