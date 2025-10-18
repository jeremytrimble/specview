"""About dialog for displaying version information."""

from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton
from PyQt5.QtCore import Qt

from .version import get_version_info

class AboutDialog(QDialog):
    """Dialog showing application version and build information."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About Specview")
        # Remove the context help button
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        
        layout = QVBoxLayout()

        msg = f"This is Specview\nA SigMF visualization and annotation tool.\n\nCopyright 2025 Jeremy Trimble\n\n{str(get_version_info())}"
        
        # Create version info label with wider minimum width
        version_label = QLabel(msg)
        version_label.setAlignment(Qt.AlignCenter)
        version_label.setMinimumWidth(400)  # Set minimum width
        layout.addWidget(version_label)
        
        # Add a close button
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button, alignment=Qt.AlignCenter)
        
        # Add some padding around content
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)  # Space between widgets
        
        self.setLayout(layout)
        
        # Let the dialog size to its contents
        self.adjustSize()