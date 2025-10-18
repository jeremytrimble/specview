"""About dialog for displaying version information."""

from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel
from PyQt5.QtCore import Qt

from .version import get_version_info

class AboutDialog(QDialog):
    """Dialog showing application version and build information."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About Specview")
        self.setFixedSize(300, 150)
        
        layout = QVBoxLayout()
        
        # Create version info label
        version_label = QLabel(str(get_version_info()))
        version_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(version_label)
        
        self.setLayout(layout)