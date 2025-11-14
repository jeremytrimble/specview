from PyQt5.QtWidgets import (
    QTreeView, QTreeWidgetItem, QVBoxLayout, QSplitter, QWidget, 
    QTreeWidget, QApplication, QAbstractItemView, QLabel, QFormLayout,
    QPushButton, QMenu
)
from PyQt5.QtCore import Qt

from .loaded_file_mgmt import LoadedFile
from .util import duration_format, freq_format
from .json_editor_dialog import JSONEditorDialog

from .app_state import AppState 

import sigmf
import logging

log = logging.getLogger("captures")

class CapturesPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        
        # Left side: Tree widget for captures
        self.captures_widget = QWidget(self)
        self.captures_layout = QVBoxLayout(self.captures_widget)
        
        self.tree_widget = QTreeWidget(self)
        self.tree_widget.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tree_widget.setColumnCount(4)
        self.tree_widget.setHeaderLabels(["Capture ID", "Center Freq", "Duration", "Date/Time"])
        self.tree_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree_widget.customContextMenuRequested.connect(self._on_tree_context_menu)
        self.captures_layout.addWidget(self.tree_widget)
        
        self.splitter.addWidget(self.captures_widget)
        
        # Right side: Metadata panel
        self.metadata_widget = QWidget(self)
        self.metadata_layout = QFormLayout(self.metadata_widget)

        self.file_path_label = QLabel("File Path:", self)
        self.file_path_value = QLabel("", self)
        self.metadata_layout.addRow(self.file_path_label, self.file_path_value)

        self.sample_rate_label = QLabel("Sample Rate:", self)
        self.sample_rate_value = QLabel("", self)
        self.metadata_layout.addRow(self.sample_rate_label, self.sample_rate_value)

        self.duration_label = QLabel("Total Duration:", self)
        self.duration_value = QLabel("", self)
        self.metadata_layout.addRow(self.duration_label, self.duration_value)

        self.num_channels_label = QLabel("Channels:", self)
        self.num_channels_value = QLabel("", self)
        self.metadata_layout.addRow(self.num_channels_label, self.num_channels_value)
        
        self.datatype_label = QLabel("Data Type:", self)
        self.datatype_value = QLabel("", self)
        self.metadata_layout.addRow(self.datatype_label, self.datatype_value)
        
        self.description_label = QLabel("Description:", self)
        self.description_value = QLabel("", self)
        self.metadata_layout.addRow(self.description_label, self.description_value)
        
        self.author_label = QLabel("Author:", self)
        self.author_value = QLabel("", self)
        self.metadata_layout.addRow(self.author_label, self.author_value)

        # Add button to view full JSON metadata
        self.view_json_button = QPushButton("View JSON Globals", self)
        self.view_json_button.clicked.connect(self._on_view_json_clicked)
        self.view_json_button.setEnabled(False)  # Disabled until a capture is selected
        self.metadata_layout.addRow("", self.view_json_button)

        for label in [self.file_path_value, self.sample_rate_value, self.duration_value,
                      self.num_channels_value, self.datatype_value,
                      self.description_value, self.author_value]:
            label.setTextInteractionFlags(label.textInteractionFlags() | Qt.TextSelectableByMouse)
        
        self.splitter.addWidget(self.metadata_widget)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 1)

        layout = QVBoxLayout(self)
        layout.addWidget(self.splitter)
        self.setLayout(layout)

        # Connect signals
        self._connect_app_signals()
        self.tree_widget.currentItemChanged.connect(self._on_current_item_changed)

    def _get_app_state(self) -> AppState:
        return QApplication.instance().app_state

    def _connect_app_signals(self):
        app_state = self._get_app_state()
        app_state.loaded_files_changed.connect(self.populate_tree)
        app_state.selected_capture_changed.connect(self.on_capture_changed)

    def _on_current_item_changed(self, selected: QTreeWidgetItem|None, deselected:QTreeWidgetItem|None):
        #log.debug(f"current item changed: {args=}, {kwargs=}")
        if selected is None:
            return

        if not hasattr(selected, "capture_id"):
            return

        app_state = self._get_app_state()
        app_state.set_selected_capture(capture_id=selected.capture_id)

    def on_capture_changed(self, capture_id: str|None):
        # Clear metadata display
        self.sample_rate_value.setText("")
        self.num_channels_value.setText("")
        self.datatype_value.setText("")
        self.description_value.setText("")
        self.author_value.setText("")

        if capture_id is not None:
            self.view_json_button.setEnabled(True)  # Enable button when a capture is selected
        else:
            self.view_json_button.setEnabled(False)  # Disable button when no capture is selected
            return

        app_state = self._get_app_state()
        loaded_file = app_state._loaded_files.get_capture_from_id(capture_id).parent_loadedfile

        sigmf_meta = loaded_file.sigmf_file.get_global_info()
        self.file_path_value.setText(str(loaded_file.file_path))
        self.sample_rate_value.setText(freq_format(loaded_file.sample_rate_Hz))
        self.duration_value.setText(duration_format(loaded_file.sigmf_file.sample_count / loaded_file.sample_rate_Hz))
        self.num_channels_value.setText(str(loaded_file.num_channels))
        self.datatype_value.setText(str(sigmf_meta.get(sigmf.SigMFFile.DATATYPE_KEY, "N/A")))
        self.description_value.setText(str(sigmf_meta.get(sigmf.SigMFFile.DESCRIPTION_KEY, "N/A")))
        self.author_value.setText(str(sigmf_meta.get(sigmf.SigMFFile.AUTHOR_KEY, "N/A")))
        
    def _on_view_json_clicked(self):
        """Open a dialog to view the full global metadata as JSON."""

        app_state = self._get_app_state()
        if app_state._selected_capture is None:
            return
        capture = app_state.get_capture_by_id(app_state._selected_capture)
        if capture is None:
            return
        loaded_file = capture.parent_loadedfile

        global_metadata = loaded_file.sigmf_file.get_global_info()
        
        dialog = JSONEditorDialog(
            parent=self,
            json_data=global_metadata,
            read_only=True,
            title=f"Global SigMF Metadata - {loaded_file.file_path.name}"
        )
        dialog.exec_()

    def _on_tree_context_menu(self, position):
        """Show context menu for tree items."""
        item = self.tree_widget.itemAt(position)
        if item is None:
            return
        
        # Only show menu for capture items (not file items)
        if not hasattr(item, "capture_id"):
            return
        
        menu = QMenu(self)
        view_json_action = menu.addAction("View Capture JSON")
        
        action = menu.exec_(self.tree_widget.viewport().mapToGlobal(position))
        
        if action == view_json_action:
            self._view_capture_json(item.capture_id)
    
    def _view_capture_json(self, capture_id: str):
        """Open a dialog to view the capture's raw JSON metadata."""
        app_state = self._get_app_state()
        capture = app_state.get_capture_by_id(capture_id)
        
        if capture is None:
            return
        
        # Get the capture annotation data (which contains all the capture metadata)
        capture_data = dict(capture)  # Convert the capture object to a dict
        
        dialog = JSONEditorDialog(
            parent=self,
            json_data=capture_data,
            read_only=True,
            title=f"Capture Metadata - {capture.parent_loadedfile.file_path.name} - Capture {capture.capture_idx_in_file:02d}"
        )
        dialog.exec_()

    def populate_tree(self):
        app_state = self._get_app_state()

        self.tree_widget.setHeaderHidden(False)
        self.tree_widget.setRootIsDecorated(True)
        self.tree_widget.clear()

        file_items = []
        for loaded_file in app_state._loaded_files.loaded_file_dict.values():
            log.debug(f" populating for {loaded_file}")
            loaded_file: LoadedFile
            file_item = QTreeWidgetItem([loaded_file.file_path.name])

            for capture in loaded_file._capture_id_to_capture.values():
                #log.debug(f" populating for {capture}")

                # TODO: present friendly units
                freq_Hz = capture[sigmf.SigMFFile.FREQUENCY_KEY] 

                datetime_str = capture.get(sigmf.SigMFFile.DATETIME_KEY, "N/A")

                capture_item = QTreeWidgetItem([f"Capture {capture.capture_idx_in_file:02d}", freq_format(freq_Hz), duration_format(capture.duration_sec), datetime_str])
                capture_item.capture_id = capture.capture_id
                file_item.addChild(capture_item)
            file_items.append(file_item)

        self.tree_widget.addTopLevelItems(file_items)
        self.tree_widget.expandAll()
        self.tree_widget.resizeColumnToContents(0)
        self.tree_widget.resizeColumnToContents(1)
        self.tree_widget.resizeColumnToContents(2)