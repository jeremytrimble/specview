from PyQt5.QtCore import QPointF, QRectF
from PyQt5.QtWidgets import QApplication, QMainWindow, QGridLayout, QWidget, QSlider, QLabel, QHBoxLayout, QVBoxLayout, QPushButton, QComboBox  # tested with PyQt6==6.7.0
import pyqtgraph as pg

from .spec_types import Spectrogram
from .app_state import AppState

from .ui_constants import INTERVAL_ROI_COLOR
from .roi_select_viewboxes import RectSelectViewBox

class WaterfallView(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._sgram : Spectrogram|None = None

        myvb = RectSelectViewBox()

        # Layout container for waterfall related stuff
        waterfall_layout = QHBoxLayout()

        # Waterfall plot
        self._waterfall = pg.PlotWidget(labels={'left': 'Time [s]', 'bottom': 'Frequency [MHz]'}, viewBox=myvb)
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

        self._roiPen = pg.mkPen(INTERVAL_ROI_COLOR, width=3)
        roi = pg.RectROI(pos=(0,0), size=(200,400), sideScalers=True, rotatable=False)
        roi.setPen(self._roiPen)
        roi.setVisible(False) # Initially hidden

        self._roi = roi

        # make sure the rect ROI is updated when the user drags it (in addition to during initial creation with shift-drag)
        self._roi.sigRegionChanged.connect( lambda: self._waterfall_roi_set( self._region_from_rectroi(self._roi)) )

        myvb.set_plot_and_rect(self._waterfall, self._roi)
        myvb.set_roi_change_callback(self._waterfall_roi_set)

        self._waterfall.addItem(roi)

        self._waterfall.scene().sigMouseMoved.connect(self._on_scene_mouse_moved)

        self.setLayout(waterfall_layout)

        self._connect_app_signals()

    def _get_app_state(self) -> AppState:
        return QApplication.instance().app_state

    @classmethod
    def _region_from_rectroi(cls, roi: pg.RectROI) -> tuple[float, float]:
        pos = roi.pos()
        size = roi.size()  # This returns a Point, not a tuple
        # To get the rectangle as (left, top, right, bottom):
        left = pos.x()
        top = pos.y()
        right = left + size.x()
        bottom = top + size.y()
        return (left, top, right, bottom)

    def _waterfall_roi_set(self, region: tuple[float, float] | None):
        print(f"{region=}")
        if region is None:
            self._get_app_state().set_frequency_interval(None)
            self._get_app_state().set_time_interval(None)
        else:
            freq_lo_Hz, time_lo_sec, freq_hi_Hz, time_hi_sec = region
            self._get_app_state().set_frequency_interval((freq_lo_Hz, freq_hi_Hz))
            self._get_app_state().set_time_interval((time_lo_sec, time_hi_sec))

    def _connect_app_signals(self):
        app_state = self._get_app_state()
        app_state.cursor_frequency_changed.connect(self._on_cursor_frequency_changed)
        app_state.cursor_time_changed.connect(self._on_cursor_time_changed)

        # TODO: uncommenting either of the below works, but not both
        app_state.time_interval_changed.connect(self._on_interval_changed)
        app_state.frequency_interval_changed.connect(self._on_interval_changed)

    def _on_interval_changed(self):
        app_state = self._get_app_state()

        time_interval = app_state._time_interval
        freq_interval = app_state._frequency_interval

        if None in (time_interval, freq_interval):
            self._roi.setVisible(False)
        else:
            # both intervals are set, so show the ROI
            self._roi.setVisible(True)
            time_lo_sec, time_hi_sec = time_interval
            f_lo_Hz, f_hi_Hz = freq_interval
            rect_roi = self._roi
            # Update the position and size of the ROI
            rect_roi.setPos((f_lo_Hz, time_lo_sec))
            rect_roi.setSize((f_hi_Hz - f_lo_Hz, time_hi_sec - time_lo_sec))

    def _on_cursor_time_changed(self, t_sec: float):
        self._time_crosshair_y.setPos(t_sec)

    def _on_cursor_frequency_changed(self, f_Hz: float):
        self._freq_crosshair_x.setPos(f_Hz)

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
            self._get_app_state().set_cursor_frequency(freq_Hz)
            self._get_app_state().set_cursor_time(time_sec)


    def setDisplayedSpectrogramData(self, sgram:Spectrogram):
        self._sgram = sgram
        self._redisplay()

    
