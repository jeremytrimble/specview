from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QTableView

from pydantic import BaseModel, Field
import pandas as pd

class AnnotationTable(QTableView):
    pass
