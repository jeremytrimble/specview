from PyQt5.QtWidgets import QTreeView, QTreeWidgetItem, QVBoxLayout, QWidget, QTreeWidget, QApplication, QAbstractItemView

from .app_state import AppState, LoadedFile 

import sigmf
import logging

log = logging.getLogger("captures")

class CapturesPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.layout = QVBoxLayout(self)

        self.tree_widget = QTreeWidget(self)
        self.tree_widget.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tree_widget.setColumnCount(3)
        self.tree_widget.setHeaderLabels(["Capture ID", "Center Freq (MHz)", "Duration (s)"])
        self.layout.addWidget(self.tree_widget)

        # Example items, replace with actual capture data
        self._connect_app_signals()

        self.tree_widget.currentItemChanged.connect(self._on_current_item_changed)

    def _get_app_state(self) -> AppState:
        return QApplication.instance().app_state

    def _connect_app_signals(self):
        app_state = self._get_app_state()
        app_state.loaded_files_changed.connect(self.populate_tree)

    def _on_current_item_changed(self, selected: QTreeWidgetItem|None, deselected:QTreeWidgetItem|None):
        #log.debug(f"current item changed: {args=}, {kwargs=}")
        if selected is None:
            return

        #parent = selected.parent()
        #if parent is None:
        #    return
        #idx = parent.indexOfChild(selected)

        app_state = self._get_app_state()
        app_state.set_selected_capture(capture_id=selected.capture_id)

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
            #file_item.open_file_id = loaded_file.file_id
            captures = loaded_file._captures
            for cap_idx, capture in enumerate(captures):
                #log.debug(f" populating for {capture}")

                # TODO: present friendly units
                freq_Hz = capture[sigmf.SigMFFile.FREQUENCY_KEY] 
                freq_MHz = freq_Hz/1e6

                # TODO: compute length here
                #duration_sec = capture[sigmf.SigMFFile.LENGTH_INDEX_KEY]

                capture_item = QTreeWidgetItem([f"Capture {cap_idx:2d}", f"{freq_MHz:.2f} MHz"])
                #capture_item.setText(0, f"Capture {cap_idx:02d}")
                capture_item.capture_id = capture.capture_id
                file_item.addChild(capture_item)
            file_items.append(file_item)

        self.tree_widget.addTopLevelItems(file_items)
        self.tree_widget.expandAll()
        self.tree_widget.resizeColumnToContents(0)
        self.tree_widget.resizeColumnToContents(1)
        self.tree_widget.resizeColumnToContents(2)