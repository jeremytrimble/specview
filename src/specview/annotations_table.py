from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QTableView

# Note: difference between QTableWidget and QTableView is that QTableWidget has
# its own built-in model, whereas QTableView requires a separate model to be developed

class AnnotationsTable(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(3)
        self.setHorizontalHeaderLabels(["Annotation", "Start Time", "End Time"])
        self.setSortingEnabled(True)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setEditTriggers(QTableWidget.NoEditTriggers)

        # Example data, replace with actual annotations
        self.add_annotation("Example Annotation 1", "00:00:01", "00:00:05")
        self.add_annotation("Example Annotation 2", "00:00:10", "00:00:15")

    def add_annotation(self, annotation, start_time, end_time):
        row_position = self.rowCount()
        self.setRowCount(row_position+1)
        self.insertRow(row_position)
        self.setItem(row_position, 0, QTableWidgetItem(annotation))
        self.setItem(row_position, 1, QTableWidgetItem(start_time))
        self.setItem(row_position, 2, QTableWidgetItem(end_time))
