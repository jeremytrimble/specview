import pyqtgraph as pg
from PyQt6.QtCore import pyqtSignal

class LabeledLinearRegionItem(pg.LinearRegionItem):
    """
    A LinearRegionItem that displays a text label at the top of the region.
    """
    # Signal emitted when the label is clicked
    label_clicked = pyqtSignal()
    
    def __init__(self, *args, **kwargs):
        label_text = kwargs.pop('label_text', "")
        label_text_color = kwargs.pop('label_text_color', (255, 255, 80))
        label_fill_color = kwargs.pop('label_fill_color', (0, 0, 255))
        super().__init__(*args, **kwargs)
        self.label_text = label_text
        self.label_color = label_text_color
        self.text_item = pg.TextItem(self.label_text, 
            anchor=(0,0),    # Note: change this to modify alignment of label
            color=label_text_color,
            fill=label_fill_color,
        )
        # Set the text item as a child of the region
        self.text_item.setParentItem(self.lines[0])
        
        # Make the text item clickable
        self.text_item.setFlag(self.text_item.GraphicsItemFlag.ItemIsSelectable, True)
        
        # Override the text item's mouse press event
        original_mouse_press = self.text_item.mousePressEvent
        def text_mouse_press(event):
            self.label_clicked.emit()
            event.accept()
        self.text_item.mousePressEvent = text_mouse_press
        
        #self._update_label_position()
        #self.sigRegionChanged.connect(self._update_label_position)

    def setLabel(self, text):
        """Set the label text and update its position."""
        self.label_text = text
        self.text_item.setText(text)
        #self._update_label_position()

    def setColors(self, text_color, fill_color):
        """Set the label text color and fill color."""
        self.label_color = text_color
        self.text_item.setColor(text_color)
        self.text_item.fill = pg.mkBrush(fill_color)
        self.text_item.update() # trigger a redraw

    def setLabelVisible(self, visible: bool):
        """Show or hide the label."""
        self.text_item.setVisible(visible)
