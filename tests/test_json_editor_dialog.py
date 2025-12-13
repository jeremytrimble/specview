import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from specview.json_editor_dialog import JSONEditorDialog

def main():
    """Interactive test for JSONEditorDialog."""
    # Sample JSON data
    test_data = {
        "string": "Hello, World!",
        "number": 42,
        "float": 3.14159,
        "boolean": True,
        "null": None,
        "array": [1, 2, 3, 4, 5],
        "nested_object": {
            "name": "Test Object",
            "properties": {
                "color": "blue",
                "size": "large"
            }
        }
    }

    app = QApplication(sys.argv)

    # First, show a read-only dialog
    read_only_dialog = JSONEditorDialog(
        json_data=test_data,
        read_only=True,
        title="Read-only JSON Viewer"
    )
    read_only_dialog.exec_()

    # Then show an editable dialog
    editable_dialog = JSONEditorDialog(
        json_data=test_data,
        read_only=False,
        title="Editable JSON Editor"
    )
    
    if editable_dialog.exec_() == JSONEditorDialog.Accepted:
        edited_data = editable_dialog.get_json()
        if edited_data is not None:
            print("Edited JSON data:")
            print(edited_data)
        else:
            print("Invalid JSON or dialog cancelled")

if __name__ == "__main__":
    main()