from PyQt5.QtCore import QSize, Qt, QThread, pyqtSignal, QObject, QTimer
from PyQt5.QtWidgets import QApplication, QMainWindow, QGridLayout, QWidget, QSlider, QLabel, QHBoxLayout, QVBoxLayout, QPushButton, QComboBox  # tested with PyQt6==6.7.0

class AppState(QObject):
    # Items of state:
    # - set of opened sigmf files

    # - selected sigmf file
    # - selected capture
    # - selected annotation
    # - selected channel

    # - plot range selections/focus times

    pass
