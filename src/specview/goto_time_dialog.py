"""Dialog for seeking to a specific time in all plots."""
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel
from PyQt6.QtCore import Qt
from specview.util import parse_time_str


class GotoTimeDialog(QDialog):
    """Dialog to prompt user for a specific time to seek to in all plots."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Go to Time")
        self.time_value = None
        
        layout = QVBoxLayout()
        
        # Add instruction label
        instruction_label = QLabel("Enter time in seconds:")
        layout.addWidget(instruction_label)
        
        # Add time input field
        self.time_input = QLineEdit()
        self.time_input.setPlaceholderText("e.g., 1.5")
        self.time_input.returnPressed.connect(self.accept)  # Accept on Enter key
        layout.addWidget(self.time_input)
        
        # Add buttons
        button_layout = QHBoxLayout()
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self.accept)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
        
        # Set focus to the input field
        self.time_input.setFocus()
    
    def accept(self):
        """Validate and store the time value before accepting."""
        try:
            self.time_value = parse_time_str(self.time_input.text())
            super().accept()
        except ValueError:
            # Invalid input - show error by highlighting the field
            self.time_input.setStyleSheet("border: 2px solid red;")
            self.time_input.selectAll()
    
    def get_time(self):
        """Return the time value entered by the user."""
        return self.time_value
