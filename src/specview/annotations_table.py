from PyQt5.QtCore import QAbstractTableModel, Qt
from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QTableView, QWidget, QApplication, QHBoxLayout

from .loaded_file_mgmt import LoadedDictAction, AnnotationID, CaptureID

from .app_state import AppState
import sigmf
from .util import duration_format, freq_format, parse_time_str, parse_freq_str

# Note: difference between QTableWidget and QTableView is that QTableWidget has
# its own built-in model, whereas QTableView requires a separate model to be developed

class AnnotationsModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_capture_id: CaptureID|None = None
        self._connect_app_signals()

        self._column_names = (
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
            0,  # Label
            1,  # Start Time
            2,  # End Time
            3,  # Duration
            4,  # Low Freq
            5,  # Center Freq
            6,  # High Freq
            7,  # Bandwidth
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
            return base_flags | Qt.ItemIsEditable
        return base_flags

    def data(self, index, role=None):
        annotations_dict = self._get_current_capture_annotations()
        if annotations_dict is None:
            return
        if role == Qt.DisplayRole:
            keys = list(annotations_dict.keys())
            row = index.row()
            col = index.column()
            if row < 0 or row >= len(keys) or col < 0 or col >= self._NUM_COLUMNS:
                return None
            annotation = annotations_dict[keys[row]]
            if col == 0:
                return annotation.get(sigmf.SigMFFile.LABEL_KEY, "--")
            elif col == 1:
                v = annotation.get_start_time_sec(self._current_capture_id)
                if v is None:
                    return "--"
                else:
                    return duration_format(v)
            elif col == 2:
                v = annotation.get_end_time_sec(self._current_capture_id)
                if v is None:
                    return "--"
                else:
                    return duration_format(v)
            elif col == 3:
                v = annotation.duration_sec
                if v is None:
                    return "--"
                else:
                    return duration_format(v)
            elif col == 4:
                v = annotation.low_frequency_Hz
                if v is None:
                    return "--"
                else:
                    return freq_format(v)
            elif col == 5:
                v = annotation.center_frequency_Hz
                if v is None:
                    return "--"
                else:
                    return freq_format(v)
            elif col == 6:
                v = annotation.high_frequency_Hz
                if v is None:
                    return "--"
                else:
                    return freq_format(v)
            elif col == 7:
                v = annotation.bandwidth_Hz
                if v is None:
                    return "--"
                else:
                    return freq_format(v)
            elif col == 8:
                return "TODO"   # put more here

    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.EditRole:
            return False

        annotations_dict = self._get_current_capture_annotations()
        if annotations_dict is None:
            return False

        keys = list(annotations_dict.keys())
        row = index.row()
        col = index.column()

        if row < 0 or row >= len(keys):
            return False

        annotation = annotations_dict[keys[row]]
        try:
            if col == 0:  # Label
                annotation[sigmf.SigMFFile.LABEL_KEY] = str(value)
            elif col == 1:  # Start Time
                try:
                    time_sec = parse_time_str(str(value))
                    annotation.set_start_time_sec(self._current_capture_id, time_sec)
                except ValueError:
                    return False
            elif col == 2:  # End Time
                try:
                    time_sec = parse_time_str(str(value))
                    annotation.set_end_time_sec(self._current_capture_id, time_sec)
                except ValueError:
                    return False
            elif col == 4:  # Low Freq
                try:
                    freq = parse_freq_str(str(value))
                    annotation.low_frequency_Hz = freq
                except ValueError:
                    return False
            elif col == 5:  # Center Freq
                try:
                    freq = parse_freq_str(str(value))
                    annotation.center_frequency_Hz = freq
                except ValueError:
                    return False
            elif col == 6:  # High Freq
                try:
                    freq = parse_freq_str(str(value))
                    annotation.high_frequency_Hz = freq
                except ValueError:
                    return False
            elif col == 3:  # Duration
                try:
                    duration_sec = parse_time_str(str(value))
                    annotation.duration_sec = duration_sec  # This will update end time keeping start time fixed
                except ValueError:
                    return False
            elif col == 5:  # Center Freq
                try:
                    freq = parse_freq_str(str(value))
                    annotation.center_frequency_Hz = freq  # This will update high/low keeping bandwidth fixed
                except ValueError:
                    return False
            elif col == 7:  # Bandwidth
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
            print(f"Error updating annotation: {e}")
            return False

class AnnotationsTable(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.table = QTableView(self)
        self.model = AnnotationsModel(self)

        self.table.setModel(self.model)

        self.layout = QHBoxLayout()
        self.layout.addWidget(self.table)
        self.setLayout(self.layout)

        self.model.layoutChanged.connect(self.table.resizeColumnsToContents)


    def get_application(self):
        return self.parent().application

