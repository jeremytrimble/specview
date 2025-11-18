from PyQt5.QtCore import QAbstractTableModel, Qt, QSortFilterProxyModel, QModelIndex
from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QTableView, QWidget, QApplication, QHBoxLayout, QMenu, QMessageBox

from .loaded_file_mgmt import LoadedAnnotationDict, LoadedDictAction, AnnotationID, CaptureID
from .json_editor_dialog import JSONEditorDialog

from .app_state import AppState
import sigmf
import logging
from .util import duration_format, freq_format, parse_time_str, parse_freq_str

log = logging.getLogger(__name__)

# Note: difference between QTableWidget and QTableView is that QTableWidget has
# its own built-in model, whereas QTableView requires a separate model to be developed

class AnnotationsModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_capture_id: CaptureID|None = None
        self._connect_app_signals()

        self._column_names = (
            "Visible",
            "Label",
            "Start Time",
            "End Time",
            "Duration (sec)",
            "Low Freq",
            "Center Freq",
            "High Freq",
            "Bandwidth",
            "More Info",
        )
        # Define which columns are editable
        self._editable_columns = {
            0,  # Visible
            1,  # Label
            2,  # Start Time
            3,  # End Time
            4,  # Duration
            5,  # Low Freq
            6,  # Center Freq
            7,  # High Freq
            8,  # Bandwidth
        }
        self._NUM_COLUMNS = len(self._column_names)

        # An ordered list of the current annotations referenced by this model.
        # (Note, this is not used to directly set the row order, as the
        # proxymodel does that.)
        self._annotation_id_list: list[AnnotationID] = []

    def _get_app_state(self) -> AppState:
        return QApplication.instance().app_state

    def _connect_app_signals(self):
        app_state = self._get_app_state()
        app_state.selected_capture_changed.connect(self._on_selected_capture_changed)
        app_state.annotation_changed.connect(self._on_annotation_changed)

    def _on_selected_capture_changed(self, capture_id: CaptureID):
        self._current_capture_id = capture_id

        app_state = self._get_app_state()
        if capture := app_state._loaded_files.get_capture_from_id(capture_id):
            parent_file = capture.parent_loadedfile
            new_annotations_dict = parent_file.get_annotations_dict()

            self.modelAboutToBeReset.emit()
            self._annotation_id_list = list(new_annotations_dict.keys())
            self.resetInternalData()
            self.modelReset.emit()
        else:
            log.info(f"Setting annotations model to empty for capture_id={capture_id}")
            self._annotation_id_list = []

    def _on_annotation_changed(self, annotation_id:AnnotationID, action: LoadedDictAction):
        if action == LoadedDictAction.MODIFIED:
            top_left = self.createIndex(0, 0)
            bottom_right = self.createIndex(self.rowCount(None) - 1, self.columnCount(None) - 1)
            self.dataChanged.emit(top_left, bottom_right)
        elif action in (LoadedDictAction.LOADED, LoadedDictAction.ADDED, LoadedDictAction.DELETED, LoadedDictAction.CLOSED):
            if action == LoadedDictAction.DELETED:

                try:
                    row_idx_to_remove = self._annotation_id_list.index(annotation_id)
                except ValueError:
                    log.warning(f"Attempted to delete annotation ID {annotation_id} not in model")
                    return

                log.debug(f"Annotation deleted: {annotation_id}")
                self.beginRemoveRows(QModelIndex(), row_idx_to_remove, row_idx_to_remove)
                self._annotation_id_list.pop(row_idx_to_remove)
                self.endRemoveRows()
                log.debug(f"did the removerows dance for {annotation_id}")
            else: # adding creating or loading

                # check to see if this annotation is part of the current capture
                if self._current_capture_id is None:
                    log.debug(f"Skipping annotation {annotation_id=}, because no capture is selected")
                    return
                app_state = self._get_app_state()
                current_capture = app_state._loaded_files.get_capture_from_id(self._current_capture_id)
                parent_loadedfile = current_capture.parent_loadedfile
                if annotation_id not in parent_loadedfile.get_annotations_dict():
                    log.debug(f"Skipping annotation {annotation_id=}, because it is not part of the current file")
                else:
                    log.debug(f"Annotation added: {annotation_id}")
                    self.beginInsertRows(QModelIndex(), len(self._annotation_id_list), len(self._annotation_id_list))
                    self._annotation_id_list.append(annotation_id)
                    self.endInsertRows()
                    log.debug(f"did the insertrows dance for {annotation_id}")


    def rowCount(self, index):
        # TODO: what is index for?
        return len(self._annotation_id_list)

    def columnCount(self, index):
        # TODO: what is index for?
        return self._NUM_COLUMNS

    def headerData(self, section, orientation, role):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return self._column_names[section]

    def flags(self, index):
        base_flags = super().flags(index)
        if index.column() in self._editable_columns:
            flags = base_flags | Qt.ItemIsEditable
            # Make the visible column checkable
            if index.column() == 0:
                flags |= Qt.ItemIsUserCheckable
            return flags
        return base_flags

    def _get_annotation_id_and_dict_for_row_idx(self, index:int):
        if index < 0 or index >= len(self._annotation_id_list):
            return None, None

        annotation_id = self._annotation_id_list[index]
        app_state = self._get_app_state()
        annotation_dict = app_state._loaded_files._annotation_id_to_annotations.get(annotation_id)    

        if annotation_dict is None:
            return None, None
        else:
            return annotation_id, annotation_dict

    def data(self, index, role=None):
        row = index.row()

        _, annotation = self._get_annotation_id_and_dict_for_row_idx(row)
        if annotation is None:
            return None

        col = index.column()
        if row < 0 or row >= len(self._annotation_id_list) or col < 0 or col >= self._NUM_COLUMNS:
            return None
        
        if role == Qt.DisplayRole:
            if col == 0:
                # Visible column - don't show text, just checkbox
                return ""
            elif col == 1:
                return annotation.get(sigmf.SigMFFile.LABEL_KEY, "--")
            elif col == 2:
                v = annotation.get_start_time_sec(self._current_capture_id)
                if v is None:
                    return "--"
                else:
                    return duration_format(v)
            elif col == 3:
                v = annotation.get_end_time_sec(self._current_capture_id)
                if v is None:
                    return "--"
                else:
                    return duration_format(v)
            elif col == 4:
                v = annotation.duration_sec
                if v is None:
                    return "--"
                else:
                    return duration_format(v)
            elif col == 5:
                v = annotation.low_frequency_Hz
                if v is None:
                    return "--"
                else:
                    return freq_format(v)
            elif col == 6:
                v = annotation.center_frequency_Hz
                if v is None:
                    return "--"
                else:
                    return freq_format(v)
            elif col == 7:
                v = annotation.high_frequency_Hz
                if v is None:
                    return "--"
                else:
                    return freq_format(v)
            elif col == 8:
                v = annotation.bandwidth_Hz
                if v is None:
                    return "--"
                else:
                    return freq_format(v)
            elif col == 9:
                return "TODO"   # put more here
        
        elif role == Qt.CheckStateRole:
            # Only handle checkbox for the visible column
            if col == 0:
                return Qt.Checked if annotation.visible else Qt.Unchecked
        
        elif role == Qt.UserRole:
            # Return raw comparable values for sorting
            if col == 0:
                # Visible - return boolean for sorting
                return annotation.visible
            elif col == 1:
                # Label - return string for lexicographic sorting
                return annotation.get(sigmf.SigMFFile.LABEL_KEY, "")
            elif col == 2:
                # Start Time - return numeric value or inf for None
                v = annotation.get_start_time_sec(self._current_capture_id)
                return v if v is not None else float('inf')
            elif col == 3:
                # End Time - return numeric value or inf for None
                v = annotation.get_end_time_sec(self._current_capture_id)
                return v if v is not None else float('inf')
            elif col == 4:
                # Duration - return numeric value or inf for None
                v = annotation.duration_sec
                return v if v is not None else float('inf')
            elif col == 5:
                # Low Freq - return numeric value or inf for None
                v = annotation.low_frequency_Hz
                return v if v is not None else float('inf')
            elif col == 6:
                # Center Freq - return numeric value or inf for None
                v = annotation.center_frequency_Hz
                return v if v is not None else float('inf')
            elif col == 7:
                # High Freq - return numeric value or inf for None
                v = annotation.high_frequency_Hz
                return v if v is not None else float('inf')
            elif col == 8:
                # Bandwidth - return numeric value or inf for None
                v = annotation.bandwidth_Hz
                return v if v is not None else float('inf')
            elif col == 9:
                # More Info - return string
                return "TODO"

    def setData(self, index, value, role=Qt.EditRole):
        # Handle checkbox state changes
        
        row = index.row()

        _, annotation_dict = self._get_annotation_id_and_dict_for_row_idx(row)
        if annotation_dict is None:
            return False

        if role == Qt.CheckStateRole:
            if index.column() == 0:  # Visible column

                # Set visibility based on checkbox state
                annotation_dict.visible = (value == Qt.Checked)
                
                # Emit dataChanged signal to update the view
                self.dataChanged.emit(index, index)
                return True
            return False
        
        if role != Qt.EditRole:
            return False

        col = index.column()

        try:
            if col == 0:  # Visible (handled above via CheckStateRole)
                return False
            elif col == 1:  # Label
                annotation_dict[sigmf.SigMFFile.LABEL_KEY] = str(value)
            elif col == 2:  # Start Time
                try:
                    time_sec = parse_time_str(str(value))
                    annotation_dict.set_start_time_sec(self._current_capture_id, time_sec)
                except ValueError:
                    return False
            elif col == 3:  # End Time
                try:
                    time_sec = parse_time_str(str(value))
                    annotation_dict.set_end_time_sec(self._current_capture_id, time_sec)
                except ValueError:
                    return False
            elif col == 4:  # Duration
                try:
                    duration_sec = parse_time_str(str(value))
                    annotation_dict.duration_sec = duration_sec  # This will update end time keeping start time fixed
                except ValueError:
                    return False
            elif col == 5:  # Low Freq
                try:
                    freq = parse_freq_str(str(value))
                    annotation_dict.low_frequency_Hz = freq
                except ValueError:
                    return False
            elif col == 6:  # Center Freq
                try:
                    freq = parse_freq_str(str(value))
                    annotation_dict.center_frequency_Hz = freq
                except ValueError:
                    return False
            elif col == 7:  # High Freq
                try:
                    freq = parse_freq_str(str(value))
                    annotation_dict.high_frequency_Hz = freq
                except ValueError:
                    return False
            elif col == 8:  # Bandwidth
                try:
                    freq = parse_freq_str(str(value))
                    annotation_dict.bandwidth_Hz = freq  # This will update high/low keeping center fixed
                except ValueError:
                    return False
            else:
                return False

            # Emit dataChanged signal to update the view
            self.dataChanged.emit(index, index)
            return True
        except Exception as e:
            log.error(f"Error updating annotation: {e}")
            return False

class AnnotationsSortFilterProxyModel(QSortFilterProxyModel):
    """Custom proxy model that prevents sorting on the Visible column."""

    def parent(self, item: QModelIndex):
        # return an empty QModelIndex since we have no parent model item
        # Note: without this, the app crashes when deleting annotations
        return QModelIndex()
    
    def lessThan(self, left, right):
        """Override to prevent sorting on column 0 (Visible)."""
        # If trying to sort by the Visible column, don't actually sort
        if left.column() == 0:
            return False
        
        # For other columns, use the default sorting behavior
        return super().lessThan(left, right)

class AnnotationsTable(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.table = QTableView(self)
        self.model = AnnotationsModel(self)
        
        # Create and configure custom proxy model for sorting
        self.proxy_model = AnnotationsSortFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.model)
        self.proxy_model.setSortRole(Qt.UserRole)
        self.proxy_model.setDynamicSortFilter(True)

        self.table.setModel(self.proxy_model)
        
        # Enable sorting on the table view
        self.table.setSortingEnabled(True)
        
        # Enable context menu
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        
        self.layout = QHBoxLayout()
        self.layout.addWidget(self.table)
        self.setLayout(self.layout)
        
        # Track current sort column and order for toggling
        self._current_sort_column = -1
        self._current_sort_order = Qt.AscendingOrder
        
        # Connect header click to custom handler
        header = self.table.horizontalHeader()
        header.sectionClicked.connect(self._on_header_clicked)
        
        self.model.layoutChanged.connect(self.table.resizeColumnsToContents)

        self.table.selectionModel().selectionChanged.connect(self._on_selection_changed)

    def _get_app_state(self) -> AppState:
        return QApplication.instance().app_state

    def _on_selection_changed(self, selected, deselected):
        """Handle selection changes in the table."""
        app_state = self._get_app_state()
        indexes = self.table.selectionModel().selectedIndexes()
        if not indexes:
            app_state.set_selected_annotation(None)
            return
        
        # Get the first selected index
        first_index = indexes[0]
        
        # Map proxy index to source model index
        source_index = self.proxy_model.mapToSource(first_index)
        
        annotation_id, _ = self.model._get_annotation_id_and_dict_for_row_idx(source_index.row()) 
        app_state.set_selected_annotation(annotation_id)

    def _on_header_clicked(self, logical_index):
        """Handle header clicks to toggle sort order or visibility."""
        # Special handling for the Visible column (column 0)
        if logical_index == 0:
            self._toggle_all_annotations_visibility()
            return
        
        # Normal sorting behavior for other columns
        if logical_index == self._current_sort_column:
            # Toggle sort order for the same column
            if self._current_sort_order == Qt.AscendingOrder:
                self._current_sort_order = Qt.DescendingOrder
            else:
                self._current_sort_order = Qt.AscendingOrder
        else:
            # New column clicked, default to ascending
            self._current_sort_column = logical_index
            self._current_sort_order = Qt.AscendingOrder
        
        # Apply the sort
        self.proxy_model.sort(self._current_sort_column, self._current_sort_order)
        
        # Update header sort indicator
        self.table.horizontalHeader().setSortIndicator(self._current_sort_column, self._current_sort_order)

    def _toggle_all_annotations_visibility(self):
        """Toggle visibility for all annotations in the current capture."""
        # Note: This code is somewhat duplicative of the annotation toggling
        # code in the menu and could be consolidated in the future.

        app_state = self._get_app_state()
        annotations_dict : dict[str, LoadedAnnotationDict ]= {}
        for annotation_id in self.model._annotation_id_list:
            if annotation := app_state._loaded_files._annotation_id_to_annotations.get(annotation_id):
                annotations_dict[annotation_id] = annotation

        if not annotations_dict:
            return
        
        # Determine if we should show all or hide all
        # If any annotation is hidden, show all. Otherwise, hide all.
        any_hidden = any(not ann.visible for ann in annotations_dict.values())
        
        # Toggle all annotations
        for annotation in annotations_dict.values():
            annotation.visible = any_hidden
        
        # The visibility changes will trigger annotation_changed signals,
        # which will update the views automatically

    def _on_context_menu(self, position):
        """Show context menu for table rows."""
        index = self.table.indexAt(position)
        if not index.isValid():
            return
        
        # Map proxy index to source model index
        source_index = self.proxy_model.mapToSource(index)
        
        menu = QMenu(self)
        view_json_action = menu.addAction("View/Edit Annotation JSON")
        delete_action = menu.addAction("Delete Annotation")
        
        action = menu.exec_(self.table.viewport().mapToGlobal(position))
        
        if action == view_json_action:
            self._view_edit_annotation_json(source_index.row())
        elif action == delete_action:
            self._delete_annotation(source_index.row())
    
    def _view_edit_annotation_json(self, row):
        """Open a dialog to view and edit the annotation's raw JSON."""


        _, annotation = self.model._get_annotation_id_and_dict_for_row_idx(row)
        if annotation is None:
            return

        # Convert annotation to dict for editing
        annotation_data = dict(annotation)
        
        # Get label for dialog title
        label = annotation.get(sigmf.SigMFFile.LABEL_KEY, f"Annotation {row}")
        
        dialog = JSONEditorDialog(
            parent=self,
            json_data=annotation_data,
            read_only=False,  # Allow editing
            title=f"Annotation JSON - {label}"
        )
        
        if dialog.exec_():
            # User clicked OK, update the annotation with the edited data
            edited_data = dialog.get_json()
            if edited_data is not None:
                try:
                    # Update the annotation with the edited data
                    annotation.clear()
                    annotation.update(edited_data)
                except Exception as e:
                    log.error(f"Error updating annotation from JSON: {e}")
    
    def _delete_annotation(self, row):
        """Delete the annotation at the specified row."""
        annotation_id, annotation = self.model._get_annotation_id_and_dict_for_row_idx(row)
        if annotation is not None:
            annotation.delete_annotation()
        else:
            log.warning(f'Attempted to delete non-existent annotation ID {annotation_id}')

    def get_application(self):
        return self.parent().application
