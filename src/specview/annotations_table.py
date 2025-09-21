from PyQt5.QtCore import QAbstractTableModel, Qt
from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QTableView, QWidget, QApplication, QHBoxLayout

from .loaded_file_mgmt import LoadedDictAction, AnnotationID, CaptureID

from .app_state import AppState
import sigmf
from .util import duration_format, freq_format

# Note: difference between QTableWidget and QTableView is that QTableWidget has
# its own built-in model, whereas QTableView requires a separate model to be developed

class AnnotationsModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_capture_fileid: str|None = None
        self._connect_app_signals()

        self._NUM_COLUMNS = 6
        self._column_names = (
            "Label",
            "Start Time",
            "End Time",
            "Low Freq",
            "High Freq",
            "More Info",
        )

    def _get_app_state(self) -> AppState:
        return QApplication.instance().app_state

    def _connect_app_signals(self):
        app_state = self._get_app_state()
        app_state.selected_capture_changed.connect(self._on_selected_capture_changed)
        app_state.annotation_changed.connect(self._on_annotation_changed)

    def _on_selected_capture_changed(self, capture_id: CaptureID):

        app_state = self._get_app_state()
        loaded_capture_dict = app_state.get_capture_by_id(capture_id)
        fileid = loaded_capture_dict.parent_loadedfile.file_id

        self._current_capture_fileid = fileid

        # layoutChanged indicates that the SHAPE of the model has changed,
        # dataChanged is for when just some elements of the data have changed
        # but the shape remains the same
        self.layoutChanged.emit() 

    def _on_annotation_changed(self, annotation_id:AnnotationID, action: LoadedDictAction):
        if action == LoadedDictAction.ADDED or action == LoadedDictAction.DELETED:
            self.layoutChanged.emit()
        elif action == LoadedDictAction.MODIFIED:
            self.dataChanged.emit()

    def _get_current_capture_annotations(self):
        if self._current_capture_fileid is None:
            return None
        app_state = self._get_app_state()
        annotations_dict = app_state._loaded_files._fileid_to_loadedfile[self._current_capture_fileid].get_annotations_dict()
        return annotations_dict

    def rowCount(self, index):
        # TODO: what is index for?
        annotations_dict = self._get_current_capture_annotations()
        if annotations_dict is None:
            return 0
        return len(annotations_dict)

    def columnCount(self, index):
        # TODO: what is index for?
        return self._NUM_COLUMNS  # Assuming two columns: 'Annotation' and 'Value'

    def headerData(self, section, orientation, role):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return self._column_names[section]

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
            #print(f"{type(annotation)=}, {annotation=}, {row=}, {col=}")
            if col == 0:
                return annotation.get(sigmf.SigMFFile.LABEL_KEY, "--")
            elif col == 1:
                v = annotation.get(sigmf.SigMFFile.START_INDEX_KEY)
                # TODO: turn into duration format!
                if v is None:
                    return "--"
                else:
                    #return duration_format(v)
                    return "TODO"
            elif col == 2:
                v = annotation.get(sigmf.SigMFFile.LENGTH_INDEX_KEY)
                # TODO: turn into duration format!
                if v is None:
                    return "--"
                else:
                    #return duration_format(v)
                    return "TODO"
            elif col == 3:
                v = annotation.get(sigmf.SigMFFile.FLO_KEY)
                if v is None:
                    return "--"
                else:
                    return freq_format(v)
            elif col == 4:
                v = annotation.get(sigmf.SigMFFile.FHI_KEY)
                if v is None:
                    return "--"
                else:
                    return freq_format(v)
            elif col == 5:
                return "TODO"   # put a button here to edit the annotation

    #def set_data(self, data):
    #    self.beginResetModel()
    #    self._data = data
    #    self.endResetModel()

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

