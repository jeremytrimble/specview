from PyQt5.QtCore import QPointF, QRectF
from PyQt5.QtWidgets import QApplication, QMainWindow, QGridLayout, QWidget, QSlider, QLabel, QHBoxLayout, QVBoxLayout, QPushButton, QComboBox  # tested with PyQt6==6.7.0
import pyqtgraph as pg

from .spec_types import Spectrogram
from .app_state import AppState

class WaterfallView(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._sgram : Spectrogram|None = None

        # Layout container for waterfall related stuff
        waterfall_layout = QHBoxLayout()

        # Waterfall plot
        self._waterfall = pg.PlotWidget(labels={'left': 'Time [s]', 'bottom': 'Frequency [MHz]'})
        self._waterfall.plotItem.getViewBox().invertY(True)
        self._imageitem = pg.ImageItem(axisOrder='col-major') # this arg is purely for performance
        self._waterfall.addItem(self._imageitem)
        self._waterfall.setMouseEnabled(x=True, y=True)
        waterfall_layout.addWidget(self._waterfall)

        # Colorbar for waterfall
        self._colorbar = pg.HistogramLUTWidget()
        self._colorbar.setImageItem(self._imageitem) # connects the bar to the waterfall imageitem
        self._colorbar.item.gradient.loadPreset('viridis') # set the color map, also sets the imageitem
        self._imageitem.setLevels((-30, 20)) # needs to come after colorbar is created for some reason
        waterfall_layout.addWidget(self._colorbar)

        self._roiPen = pg.mkPen("red", width=3)
        roi = pg.RectROI(pos=(0,0), size=(200,400), sideScalers=True, rotatable=False)
        roi.setPen(self._roiPen)
        roi.sigRegionChanged.connect(lambda x:print(f"Region changed: {x.getArraySlice(returnSlice=False)}"))

        self._waterfall.addItem(roi)

        self.setLayout(waterfall_layout)

    def _redisplay(self):

        if self._sgram is None:
            return

        # TODO pull channel, time segment, etc
        chan = 0

        f_Hz = self._sgram.freq_Hz
        f_lo_Hz = f_Hz[0]
        f_hi_Hz = f_Hz[-1]

        wfall_data = self._sgram.data[chan,:,:]

        time_sec = self._sgram.time_sec
        time_lo_sec = time_sec[0]
        time_hi_sec = time_sec[-1]

        wf_rect = QRectF(
            f_lo_Hz,
            time_lo_sec, 
            f_hi_Hz - f_lo_Hz,
            time_hi_sec-time_lo_sec,
        )

        print(f"{wf_rect=}")

        #self._imageitem.setImage(wfall_data, rect=wf_rect)
        self._imageitem.setImage(wfall_data)
        self._imageitem.setRect(wf_rect)

        self._waterfall.setYRange( time_lo_sec, time_hi_sec )
        self._waterfall.setXRange( f_lo_Hz, f_hi_Hz )

    def setDisplayedSpectrogramData(self, sgram:Spectrogram):
        self._sgram = sgram
        self._redisplay()
