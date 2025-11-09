from PyQt5.QtCore import QAbstractTableModel, Qt, QSortFilterProxyModel
from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QTableView, QWidget, QApplication, QHBoxLayout, QMenu

from .loaded_file_mgmt import LoadedDictAction, AnnotationID, CaptureID
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

    def _get_app_state(self) -> AppState:
        return QApplication.instance().app_state

    def _connect_app_signals(self):
        app_state = self._get_app_state()
        app_state.selected_capture_changed.connect(self._on_selected_capture_changed)
        app_state.annotation_changed.connect(self._on_annotation_changed)

    def _on_selected_capture_changed(self, capture_id: CaptureID):
        self._current_capture_id = capture_id
        # layoutChanged indicates that the SHAPE of the model has changed,
        # dataChanged is for when just some elements of the data have changed
        # but the shape remains the same
        self.layoutChanged.emit() 

    def _on_annotation_changed(self, annotation_id:AnnotationID, action: LoadedDictAction):
        if action == LoadedDictAction.MODIFIED:
            top_left = self.createIndex(0, 0)
            bottom_right = self.createIndex(self.rowCount(None) - 1, self.columnCount(None) - 1)
            self.dataChanged.emit(top_left, bottom_right)
        elif action in (LoadedDictAction.LOADED, LoadedDictAction.ADDED, LoadedDictAction.DELETED, LoadedDictAction.CLOSED):
            self.layoutChanged.emit()

    def _get_current_capture_annotations(self):
        if self._current_capture_id is None:
            return None
        app_state = self._get_app_state()
        annotations_dict = app_state._loaded_files.get_capture_from_id(self._current_capture_id).parent_loadedfile.get_annotations_dict()
        return annotations_dict

    def rowCount(self, index):
        # TODO: what is index for?
        annotations_dict = self._get_current_capture_annotations()
        if annotations_dict is None:
            return 0
        return len(annotations_dict)

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

    def data(self, index, role=None):
        annotations_dict = self._get_current_capture_annotations()
        if annotations_dict is None:
            return
        
        keys = list(annotations_dict.keys())
        row = index.row()
        col = index.column()
        if row < 0 or row >= len(keys) or col < 0 or col >= self._NUM_COLUMNS:
            return None
        annotation = annotations_dict[keys[row]]
        
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
        if role == Qt.CheckStateRole:
            if index.column() == 0:  # Visible column
                annotations_dict = self._get_current_capture_annotations()
                if annotations_dict is None:
                    return False
                
                keys = list(annotations_dict.keys())
                row = index.row()
                
                if row < 0 or row >= len(keys):
                    return False
                
                annotation = annotations_dict[keys[row]]
                # Set visibility based on checkbox state
                annotation.visible = (value == Qt.Checked)
                
                # Emit dataChanged signal to update the view
                self.dataChanged.emit(index, index)
                return True
            return False
        
        if role != Qt.EditRole:
            return False

        annotations_dict = self._get_current_capture_annotations()
        if annotations_dict is None:
            return False

        # FIXME: this seesms to assume that the order of the annotations dict is
        # the same as the order of our rows, which may not always be true
        keys = list(annotations_dict.keys())
        row = index.row()
        col = index.column()

        if row < 0 or row >= len(keys):
            return False

        annotation = annotations_dict[keys[row]]
        try:
            if col == 0:  # Visible (handled above via CheckStateRole)
                return False
            elif col == 1:  # Label
                annotation[sigmf.SigMFFile.LABEL_KEY] = str(value)
            elif col == 2:  # Start Time
                try:
                    time_sec = parse_time_str(str(value))
                    annotation.set_start_time_sec(self._current_capture_id, time_sec)
                except ValueError:
                    return False
            elif col == 3:  # End Time
                try:
                    time_sec = parse_time_str(str(value))
                    annotation.set_end_time_sec(self._current_capture_id, time_sec)
                except ValueError:
                    return False
            elif col == 5:  # Low Freq
                try:
                    freq = parse_freq_str(str(value))
                    annotation.low_frequency_Hz = freq
                except ValueError:
                    return False
            elif col == 6:  # Center Freq
                try:
                    freq = parse_freq_str(str(value))
                    annotation.center_frequency_Hz = freq
                except ValueError:
                    return False
            elif col == 7:  # High Freq
                try:
                    freq = parse_freq_str(str(value))
                    annotation.high_frequency_Hz = freq
                except ValueError:
                    return False
            elif col == 4:  # Duration
                try:
                    duration_sec = parse_time_str(str(value))
                    annotation.duration_sec = duration_sec  # This will update end time keeping start time fixed
                except ValueError:
                    return False
            elif col == 6:  # Center Freq
                try:
                    freq = parse_freq_str(str(value))
                    annotation.center_frequency_Hz = freq  # This will update high/low keeping bandwidth fixed
                except ValueError:
                    return False
            elif col == 8:  # Bandwidth
                try:
                    freq = parse_freq_str(str(value))
                    annotation.bandwidth_Hz = freq  # This will update high/low keeping center fixed
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

class AnnotationsTable(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.table = QTableView(self)
        self.model = AnnotationsModel(self)
        
        # Create and configure proxy model for sorting
        self.proxy_model = QSortFilterProxyModel(self)
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

    def _on_header_clicked(self, logical_index):
        """Handle header clicks to toggle sort order."""
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

    def _on_context_menu(self, position):
        """Show context menu for table rows."""
        index = self.table.indexAt(position)
        if not index.isValid():
            return
        
        # Map proxy index to source model index
        source_index = self.proxy_model.mapToSource(index)
        
        menu = QMenu(self)
        view_json_action = menu.addAction("View/Edit Annotation JSON")
        
        action = menu.exec_(self.table.viewport().mapToGlobal(position))
        
        if action == view_json_action:
            self._view_edit_annotation_json(source_index.row())
    
    def _view_edit_annotation_json(self, row):
        """Open a dialog to view and edit the annotation's raw JSON."""
        annotations_dict: dict[str, LoadedDictAction] = self.model._get_current_capture_annotations()
        if annotations_dict is None:
            return
        
        # FIXME: this seesms to assume that the order of the annotations dict is
        # the same as the order of our rows, which may not always be true
        keys = list(annotations_dict.keys())
        if row < 0 or row >= len(keys):
            return
        
        annotation_id = keys[row]
        annotation = annotations_dict[annotation_id]
        
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
                    # Emit signal to update the view
                    app_state = QApplication.instance().app_state
                    app_state.annotation_changed.emit(annotation_id, LoadedDictAction.MODIFIED)
                except Exception as e:
                    log.error(f"Error updating annotation from JSON: {e}")

    def get_application(self):
        return self.parent().application
