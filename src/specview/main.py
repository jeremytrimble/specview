from PyQt5.QtCore import QSize, Qt, QThread, pyqtSignal, QObject, QTimer, QThreadPool
from PyQt5.QtWidgets import QApplication, QMainWindow, QGridLayout, QWidget, QSlider, QLabel, QHBoxLayout, QVBoxLayout, QPushButton, QComboBox  # tested with PyQt6==6.7.0
import pyqtgraph as pg # tested with pyqtgraph==0.13.7
import numpy as np
import signal # TODO: let control-C actually close the app


import sigmf
import logging

from pathlib import Path
import argparse

from specview.util import measure_runtime

from .time_view import TimeView
from .specan_view import SpecanView
from .waterfall_view import WaterfallView
from .app_state import AppState
from .monotonic_axis import MonotonicAxis
from .annotations_table import AnnotationsTable
from .captures_panel import CapturesPanel

log = logging.getLogger("specview")


from .menu import populate_menubar


# Subclass QMainWindow to customize your application's main window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("SpecView ALPHA 20251013") # TODO: set title with filename(s)
        #self.setFixedSize(QSize(1500, 1000)) # window size, starting size should fit on 1920 x 1080

        layout = QGridLayout() # overall layout

        self._menubar = self.menuBar()
        populate_menubar(self._menubar, self)

        self.time_view = TimeView(parent=self)
        self.specan_view = SpecanView(parent=self)
        self.waterfall_view = WaterfallView(parent=self)
        self.annotation_table = AnnotationsTable(parent=self)
        self.captures_panel = CapturesPanel(parent=self)

        layout.addWidget(self.time_view, 1, 0)
        layout.addWidget(self.specan_view, 2, 0)
        layout.addWidget(self.waterfall_view, 3, 0)
        layout.addWidget(self.annotation_table, 4, 0)
        layout.addWidget(self.captures_panel, 5, 0)

        central_widget = QWidget()
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

        self._statusbar = self.statusBar()
        self._statusbar.showMessage("Ready")  # Initial message in the status bar

        self._connect_app_signals()

        self.resize(QSize(2000,1500))

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
