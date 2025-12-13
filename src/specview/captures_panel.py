from PyQt6.QtWidgets import (
    QTreeView, QTreeWidgetItem, QVBoxLayout, QSplitter, QWidget, 
    QTreeWidget, QApplication, QAbstractItemView, QLabel, QFormLayout,
    QPushButton, QMenu, QHBoxLayout
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QPainter, QColor

from .loaded_file_mgmt import LoadedFile, FileID
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
        self.tree_widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tree_widget.setColumnCount(4)
        self.tree_widget.setHeaderLabels(["Capture ID", "Center Freq", "Duration", "Date/Time"])
        self.tree_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_widget.customContextMenuRequested.connect(self._on_tree_context_menu)
        self.captures_layout.addWidget(self.tree_widget)
        
        self.splitter.addWidget(self.captures_widget)
        
        # Right side: Metadata panel
        self.metadata_widget = QWidget(self)
        self.metadata_layout = QFormLayout(self.metadata_widget)

        self.file_path_label = QLabel("File Path:", self)
        self.file_path_value = QLabel("", self)

        # Save status icon (green = saved, red = unsaved). We'll place it to the
        # right of the file path value inside a small horizontal container.
        self.save_status_icon = QLabel(self)
        self.save_status_icon.setFixedSize(16, 16)

        # Create pixmaps for saved/unsaved states
        def _make_circle_pixmap(color: QColor, size: int = 14) -> QPixmap:
            pix = QPixmap(size, size)
            pix.fill(Qt.GlobalColor.transparent)
            p = QPainter(pix)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setBrush(color)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(0, 0, size - 1, size - 1)
            p.end()
            return pix

        self._saved_pixmap = _make_circle_pixmap(QColor(0, 200, 0), size=12)
        self._unsaved_pixmap = _make_circle_pixmap(QColor(200, 0, 0), size=12)

        # Container for file path value + status icon
        fp_container = QWidget(self)
        fp_layout = QHBoxLayout(fp_container)
        fp_layout.setContentsMargins(0, 0, 0, 0)
        fp_layout.addWidget(self.file_path_value)
        fp_layout.addStretch(1)
        fp_layout.addWidget(self.save_status_icon)
        self.metadata_layout.addRow(self.file_path_label, fp_container)

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
            label.setTextInteractionFlags(label.textInteractionFlags() | Qt.TextInteractionFlag.TextSelectableByMouse)
        
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
        app_state.file_save_status_changed.connect(self._on_file_save_status_changed)

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
        self.file_path_value.setText(str(loaded_file.sigmf_data_file_path))
        self.sample_rate_value.setText(freq_format(loaded_file.sample_rate_Hz))
        self.duration_value.setText(duration_format(loaded_file.sigmf_file.sample_count / loaded_file.sample_rate_Hz))
        self.num_channels_value.setText(str(loaded_file.num_channels))
        self.datatype_value.setText(str(sigmf_meta.get(sigmf.SigMFFile.DATATYPE_KEY, "N/A")))
        self.description_value.setText(str(sigmf_meta.get(sigmf.SigMFFile.DESCRIPTION_KEY, "N/A")))
        self.author_value.setText(str(sigmf_meta.get(sigmf.SigMFFile.AUTHOR_KEY, "N/A")))
        # Update the save-status icon for the selected file
        self._update_save_status_icon_in_panel(loaded_file)
        
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
            title=f"Global SigMF Metadata - {loaded_file.sigmf_data_file_path.name}"
        )
        dialog.exec_()

    def _update_save_status_icon_in_panel(self, loaded_file: LoadedFile | None):
        """Set the save/unsaved icon for the provided loaded file.
        If loaded_file is None, hide the icon.
        """
        if loaded_file is None:
            self.save_status_icon.hide()
            return

        if loaded_file.has_unsaved_changes:
            self.save_status_icon.setPixmap(self._unsaved_pixmap)
            self.save_status_icon.setToolTip("File has unsaved changes")
            self.save_status_icon.show()
        else:
            self.save_status_icon.setPixmap(self._saved_pixmap)
            self.save_status_icon.setToolTip("File is saved")
            self.save_status_icon.show()

    def _refresh_save_icon_for_selected(self):
        """Helper invoked when files list changes; refresh icon for selected file."""
        app_state = self._get_app_state()
        if app_state._selected_capture is None:
            self._update_save_status_icon_in_panel(None)
            return
        capture = app_state.get_capture_by_id(app_state._selected_capture)
        if capture is None:
            self._update_save_status_icon_in_panel(None)
            return
        self._update_save_status_icon_in_panel(capture.parent_loadedfile)

    def _on_tree_context_menu(self, position):
        """Show context menu for tree items."""
        item = self.tree_widget.itemAt(position)
        if item is None:
            return
        
        menu = QMenu(self)
        
        # Check if it's a capture item or a file item
        if hasattr(item, "capture_id"):
            # Capture item - show capture-specific menu
            view_json_action = menu.addAction("View Capture JSON")
            menu.addSeparator()
            
            # Get the parent file for this capture
            app_state = self._get_app_state()
            capture = app_state.get_capture_by_id(item.capture_id)
            if capture is not None:
                loaded_file = capture.parent_loadedfile
                
                # Add save action
                save_file_action = menu.addAction("Save File")
                if not loaded_file.has_unsaved_changes:
                    save_file_action.setEnabled(False)
                
                # Add close file action
                close_file_action = menu.addAction("Close File")
        else:
            # File item - show file-specific menu
            # Get the loaded file from this item
            app_state = self._get_app_state()
            loaded_file = None
            
            # Find the loaded file by file_id if available, otherwise by filename
            if hasattr(item, 'file_id'):
                loaded_file = app_state._loaded_files.get_loaded_file_from_id(item.file_id)
            else:
                # Fallback: match by filename (strip asterisk if present)
                item_text = item.text(0).lstrip('* ')
                for lf in app_state._loaded_files.loaded_file_dict.values():
                    if lf.sigmf_data_file_path.name == item_text:
                        loaded_file = lf
                        break
            
            if loaded_file is not None:
                # Add save action
                save_file_action = menu.addAction("Save File")
                if not loaded_file.has_unsaved_changes:
                    save_file_action.setEnabled(False)
                
                # Add close file action
                close_file_action = menu.addAction("Close File")
        
        action = menu.exec_(self.tree_widget.viewport().mapToGlobal(position))
        
        if action is None:
            return
        
        if hasattr(item, "capture_id") and action.text() == "View Capture JSON":
            self._view_capture_json(item.capture_id)
        elif action.text() == "Save File":
            # Get the loaded file
            if hasattr(item, "capture_id"):
                app_state = self._get_app_state()
                capture = app_state.get_capture_by_id(item.capture_id)
                if capture is not None:
                    loaded_file = capture.parent_loadedfile
                    loaded_file.save()
                    log.info(f"Saved file: {loaded_file.sigmf_data_file_path.name}")
                    self._update_file_item_in_tree_view(loaded_file)
            else:
                # File item
                if loaded_file is not None:
                    loaded_file.save()
                    log.info(f"Saved file: {loaded_file.sigmf_data_file_path.name}")
                    self._update_file_item_in_tree_view(loaded_file)
        elif action.text() == "Close File":
            # Get the loaded file and close it
            if hasattr(item, "capture_id"):
                app_state = self._get_app_state()
                capture = app_state.get_capture_by_id(item.capture_id)
                if capture is not None:
                    file_id = capture.parent_loadedfile.file_id
                    app_state.close_file(file_id, prompt_save=True)
            else:
                # File item
                if loaded_file is not None:
                    app_state = self._get_app_state()
                    app_state.close_file(loaded_file.file_id, prompt_save=True)
    
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
            title=f"Capture Metadata - {capture.parent_loadedfile.sigmf_data_file_path.name} - Capture {capture.capture_idx_in_file:02d}"
        )
        dialog.exec_()

    def _on_file_save_status_changed(self, file_id:FileID, is_saved:bool) -> None:
        """Update file display when annotations change (to show unsaved indicator)."""
        # Find which file this annotation belongs to and update its display
        app_state = self._get_app_state()
        loaded_file = app_state._loaded_files.get_loaded_file_from_id(file_id)

        if loaded_file is not None:
            self._update_file_item_in_tree_view(loaded_file)
            if app_state._selected_capture is not None:
                selected_capture = app_state.get_capture_by_id(app_state._selected_capture)
                if selected_capture is not None and selected_capture.parent_loadedfile == loaded_file:
                    # Update save status icon if the selected capture's file changed
                    self._update_save_status_icon_in_panel(loaded_file)
    
    def _update_file_item_in_tree_view(self, loaded_file: LoadedFile):
        """Update the display of a file item to show unsaved changes indicator."""
        # Find the tree item for this file
        for i in range(self.tree_widget.topLevelItemCount()):
            item = self.tree_widget.topLevelItem(i)
            if hasattr(item, 'file_id') and item.file_id == loaded_file.file_id:
                # Update the text to show/hide the unsaved indicator
                file_name = loaded_file.sigmf_data_file_path.name
                if loaded_file.has_unsaved_changes:
                    item.setText(0, f"* {file_name}")
                else:
                    item.setText(0, file_name)
                break

    def populate_tree(self):
        app_state = self._get_app_state()

        self.tree_widget.setHeaderHidden(False)
        self.tree_widget.setRootIsDecorated(True)
        self.tree_widget.clear()

        file_items = []
        for loaded_file in app_state._loaded_files.loaded_file_dict.values():
            log.debug(f" populating for {loaded_file}")
            loaded_file: LoadedFile
            # Add asterisk prefix if file has unsaved changes
            file_name = loaded_file.sigmf_data_file_path.name
            if loaded_file.has_unsaved_changes:
                file_name = f"* {file_name}"
            file_item = QTreeWidgetItem([file_name])
            # Store file_id for later lookup
            file_item.file_id = loaded_file.file_id

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