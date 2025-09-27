import pyqtgraph as pg

class LabeledLinearRegionItem(pg.LinearRegionItem):
    """
    A LinearRegionItem that displays a text label at the top of the region.
    """
    def __init__(self, *args, **kwargs):
        label_text = kwargs.pop('label_text', "")
        label_text_color = kwargs.pop('label_text_color', (255, 255, 80))
        label_fill_color = kwargs.pop('label_fill_color', (0, 0, 255))
        super().__init__(*args, **kwargs)
        self.label_text = label_text
        self.label_color = label_text_color
        self.text_item = pg.TextItem(self.label_text, 
            anchor=(0.5, 1),    # Note: change this to modify alignment of label
            color=label_text_color,
            fill=label_fill_color,
        )
        # Set the text item as a child of the region
        self.text_item.setParentItem(self.lines[0])
        self._update_label_position()
        self.sigRegionChanged.connect(self._update_label_position)

    def setLabel(self, text):
        """Set the label text and update its position."""
        self.label_text = text
        self.text_item.setText(text)
        self._update_label_position()

    def _update_label_position(self):
        """Update the label position to be centered at the top of the region."""
        region = self.getRegion()
        center = (region[0] + region[1]) / 2
        # Position the label at the center of the region
        self.text_item.setPos(center, 0)

    def setLabelVisible(self, visible: bool):
        """Show or hide the label."""
        self.text_item.setVisible(visible)
