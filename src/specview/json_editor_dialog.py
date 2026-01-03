from typing import Any, Optional, Union
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QPlainTextEdit,
    QDialogButtonBox,
    QLabel,
    QWidget,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCharFormat, QColor, QSyntaxHighlighter, QTextDocument
import json

class JSONSyntaxHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for JSON errors."""

    def __init__(self, parent: Optional[QTextDocument] = None) -> None:
        super().__init__(parent)
        self.error_pos: Optional[int] = None
        self.error_length: int = 0
        
        # Create error format
        self.error_format = QTextCharFormat()
        self.error_format.setUnderlineColor(QColor("red"))
        self.error_format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)

    def set_error(self, pos: int, length: int) -> None:
        """Set the position and length of the error to highlight."""
        self.error_pos = pos
        self.error_length = length
        self.rehighlight()

    def clear_error(self) -> None:
        """Clear any existing error highlighting."""
        self.error_pos = None
        self.error_length = 0
        self.rehighlight()

    def highlightBlock(self, text: Optional[str]) -> None:
        """Highlight the error in the text if it exists in this block."""
        if self.error_pos is None or text is None:
            return

        block_pos = self.currentBlock().position()
        block_length = len(text)
        error_start = self.error_pos - block_pos
        
        # Check if the error is in this block
        if 0 <= error_start < block_length:
            error_end = min(error_start + self.error_length, block_length)
            if error_start < error_end:
                self.setFormat(error_start, error_end - error_start, self.error_format)


class JSONEditorDialog(QDialog):
    """A dialog for displaying and optionally editing JSON content."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        json_data: Optional[Any] = None,
        read_only: bool = True,
        title: str = "JSON Editor"
    ) -> None:
        """Initialize the JSON editor dialog.

        Args:
            parent: Parent widget
            json_data: The JSON data to display/edit (can be dict, list, or any JSON-serializable object)
            read_only: If True, the content will be read-only but selectable/copyable
            title: The title for the dialog window
        """
        super().__init__(parent)
        self._validation_in_progress = False
        self.setWindowTitle(title)
        self.resize(600, 400)  # Set a reasonable default size

        # Create layout
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Create the text editor
        self.text_editor = QPlainTextEdit()
        if read_only:
            self.text_editor.setReadOnly(True)
        else:
            # Only set up error checking if the editor is editable
            self.text_editor.textChanged.connect(self.validate_json)
        layout.addWidget(self.text_editor)

        # Create syntax highlighter
        self.highlighter = JSONSyntaxHighlighter(self.text_editor.document())

        # Create error label (hidden by default)
        self.error_label = QLabel()
        self.error_label.setStyleSheet("QLabel { color: red; }")
        self.error_label.hide()
        layout.addWidget(self.error_label)

        # Add OK/Cancel buttons
        self.button_box = QDialogButtonBox()
        if read_only:
            self.button_box.setStandardButtons(QDialogButtonBox.StandardButton.Close)
        else:
            self.button_box.setStandardButtons(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)

        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        # Set the JSON content if provided
        if json_data is not None:
            self.set_json(json_data)



    def set_json(self, data: Any) -> None:
        """Set the JSON content in the editor with nice formatting.

        Args:
            data: The data to display (must be JSON-serializable)
        """
        try:
            formatted_json = json.dumps(data, indent=2, sort_keys=True)
            self.text_editor.setPlainText(formatted_json)
        except (TypeError, ValueError) as e:
            self.text_editor.setPlainText(f"Error formatting JSON: {str(e)}")

    def validate_json(self) -> None:
        """Validate the current JSON content and update error display."""

        if self._validation_in_progress:
            return  # Prevent re-entrancy   

        self._validation_in_progress = True

        text = self.text_editor.toPlainText()
        try:
            json.loads(text)
            # If successful, clear any error indicators
            self.error_label.hide()
            self.highlighter.clear_error()
            ok_button = self.button_box.button(QDialogButtonBox.Ok)
            if ok_button:
                ok_button.setEnabled(True)
        except json.JSONDecodeError as e:
            # Show error message and highlight the error position
            self.error_label.setText(f"JSON Error: {str(e)}")
            self.error_label.show()
            self.highlighter.set_error(e.pos, 1)  # Highlight the character at error position
            ok_button = self.button_box.button(QDialogButtonBox.Ok)
            if ok_button:
                ok_button.setEnabled(False)
        finally:
            self._validation_in_progress = False

    def get_json(self) -> Optional[Any]:
        """Get the current JSON content as a Python object.

        Returns:
            The parsed JSON data as a Python object, or None if parsing fails
        """
        try:
            text = self.text_editor.toPlainText()
            return json.loads(text)
        except json.JSONDecodeError:
            return None