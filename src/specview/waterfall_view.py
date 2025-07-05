from PyQt5.QtCore import QPointF, QRectF
from PyQt5.QtWidgets import QApplication, QMainWindow, QGridLayout, QWidget, QSlider, QLabel, QHBoxLayout, QVBoxLayout, QPushButton, QComboBox  # tested with PyQt6==6.7.0
import pyqtgraph as pg

from .spec_types import Spectrogram
from .app_state import AppState

from .util import signals_blocked

class WaterfallView(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._sgram : Spectrogram|None = None

        # Layout container for waterfall related stuff
        waterfall_layout = QHBoxLayout()

        # Waterfall plot
        self._waterfall = pg.PlotWidget(labels={'left': 'Time [s]', 'bottom': 'Frequency [MHz]'})
        self._waterfall.plotItem.getViewBox().invertY(True)
        self._imageitem = pg.ImageItem(axisOrder='row-major')
        self._waterfall.addItem(self._imageitem)
        self._waterfall.setMouseEnabled(x=True, y=True)
        waterfall_layout.addWidget(self._waterfall)

        # Colorbar for waterfall
        self._colorbar = pg.HistogramLUTWidget()
        self._colorbar.setImageItem(self._imageitem) # connects the bar to the waterfall imageitem
        self._colorbar.item.gradient.loadPreset('viridis') # set the color map, also sets the imageitem
        self._imageitem.setLevels((-30, 20)) # needs to come after colorbar is created for some reason
        waterfall_layout.addWidget(self._colorbar)

        # Freq crosshair
        self._freq_crosshair_x = pg.InfiniteLine(angle=90, movable=False)
        self._waterfall.addItem(self._freq_crosshair_x, ignoreBounds=True)

        self._time_crosshair_y = pg.InfiniteLine(angle=0, movable=False)
        self._waterfall.addItem(self._time_crosshair_y, ignoreBounds=True)

        self._roiPen = pg.mkPen("red", width=3)
        roi = pg.RectROI(pos=(0,0), size=(200,400), sideScalers=True, rotatable=False)
        roi.setPen(self._roiPen)
        roi.sigRegionChanged.connect(lambda x:print(f"Region changed: {x.getArraySlice(returnSlice=False)}"))

        self._waterfall.addItem(roi)

        self._waterfall.scene().sigMouseMoved.connect(self._on_scene_mouse_moved)

        self.setLayout(waterfall_layout)

        self._connect_app_signals()

    def _get_app_state(self) -> AppState:
        return QApplication.instance().app_state

    def _connect_app_signals(self):
        app_state = self._get_app_state()
        app_state.selected_frequencies_changed.connect(self._on_frequencies_changed)

    def _on_frequencies_changed(self, freq_lo_Hz: float, freq_hi_Hz: float):
        # TODO: handle ranges later
        if freq_hi_Hz != freq_lo_Hz:
            print("waterfall_view: freq intervals not supported yet")
        self._freq_crosshair_x.setPos(freq_lo_Hz)

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

        self._imageitem.setImage(wfall_data)
        self._imageitem.setRect(wf_rect)

        self._waterfall.setYRange( time_lo_sec, time_hi_sec )
        self._waterfall.setXRange( f_lo_Hz, f_hi_Hz )

    def _on_scene_mouse_moved(self, pos: QPointF):
        #print(f"on_scene_mouse_moved: {args=}, {kwargs=}")
        if self._waterfall.sceneBoundingRect().contains(pos):
            mousePoint = self._waterfall.getViewBox().mapSceneToView(pos)
            freq_Hz = mousePoint.x()
            time_sec = mousePoint.y()
            self._freq_crosshair_x.setPos( freq_Hz )
            self._time_crosshair_y.setPos( time_sec )

            # TODO: handle frequency interval selection later:
            with signals_blocked(self):
                self._get_app_state().set_selected_frequencies(freq_Hz,freq_Hz)
                self._get_app_state().set_selected_times(time_sec, time_sec)


    def setDisplayedSpectrogramData(self, sgram:Spectrogram):
        self._sgram = sgram
        self._redisplay()

    
