from PyQt6.QtWidgets import QDialog, QVBoxLayout, QPushButton, QHBoxLayout
from PyQt6.QtCore import Qt
from pydantic import ValidationError
from pyqtschema import WidgetBuilder

from .app_state import AppState
from .chunkwise_compute import FrequencyDomainComputationSpec

import logging
log = logging.getLogger(__name__)

class FFTConfigDialog(QDialog):
    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self.app_state = app_state
        self.setWindowTitle("FFT Settings")
        
        # Create layout
        layout = QVBoxLayout()

        # Create form from FrequencyDomainComputationSpec model
        builder = WidgetBuilder(FrequencyDomainComputationSpec.model_json_schema())
        self.form = builder.create_form()
        layout.addWidget(self.form)
        
        # Set initial values from current config
        current_config = app_state.get_fft_config()
        self.form.state = current_config.model_dump()
        
        # Add OK/Cancel buttons
        button_layout = QHBoxLayout()
        
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self.accept)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)
        button_layout.setAlignment(Qt.AlignmentFlag.AlignRight)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
        
    def accept(self):
        """Update AppState with new config when OK is clicked."""
        try:
            # Get form data and create new config
            form_data = self.form.state
            new_config = FrequencyDomainComputationSpec.model_validate(form_data)
            
            # Update AppState (this will emit the change signal)
            self.app_state.set_fft_config(new_config)

            super().accept()
        except ValidationError as e:
            log.exception(f"Failed to update FFT config: {e}")