import pyqtgraph as pg

class LabeledRectROI(pg.RectROI):
    """
    A RectROI that displays a small text label in the top-left corner of the ROI.
    """
    def __init__(self, *args, **kwargs):
        label_text = kwargs.pop('label_text', "")
        label_text_color = kwargs.pop('label_text_color', (255, 255, 80))
        label_fill_color = kwargs.pop('label_fill_color', (0, 0, 255))
        super().__init__(*args, **kwargs)
        self.label_text = label_text
        self.label_color = label_text_color
        self.text_item = pg.TextItem(self.label_text, anchor=(0, 0), 
            color=label_text_color, 
            fill=label_fill_color, 
        )
        self.text_item.setParentItem(self)
        self._update_label_position()
        self.sigRegionChanged.connect(self._update_label_position)

    def setLabel(self, text):
        self.label_text = text
        self.text_item.setText(text)
        self._update_label_position()

    def _update_label_position(self):
        # Always place label at the top-left of the ROI, in ROI coordinates
        self.text_item.setPos(0, 0)

    def setLabelVisible(self, visible:bool):
        self.text_item.setVisible(visible)