from PyQt5.QtWidgets import QTreeView, QTreeWidgetItem, QVBoxLayout, QWidget, QTreeWidget

class CapturesPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Captures")

        self.layout = QVBoxLayout(self)

        self.tree_widget = QTreeWidget(self)
        self.layout.addWidget(self.tree_widget)

        # Example items, replace with actual capture data
        self.populate_tree()

    def populate_tree(self):
        root_item = QTreeWidgetItem(["Captures"])
        self.tree_widget.setHeaderHidden(True)
        self.tree_widget.setRootIsDecorated(False)
        
        # Add example captures
        for i in range(5):
            item = QTreeWidgetItem([f"Capture {i+1}"])
            root_item.addChild(item)

        self.tree_widget.addTopLevelItem(root_item)
        self.tree_widget.expandAll()  # Expand all items for visibility   