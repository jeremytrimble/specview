from PyQt5.QtCore import QSize, Qt, QThread, pyqtSignal, QObject, QTimer
from PyQt5.QtWidgets import QApplication, QMainWindow, QGridLayout, QWidget, QSlider, QLabel, QHBoxLayout, QVBoxLayout, QPushButton, QComboBox  # tested with PyQt6==6.7.0
import pyqtgraph as pg # tested with pyqtgraph==0.13.7
import numpy as np
import signal # TODO: let control-C actually close the app

import scipy.signal, scipy.signal.windows

import sigmf
import logging

from pathlib import Path
import argparse

from platformdirs import user_cache_dir
import diskcache


from specview.smf import smf_get_field_cap_or_global
from specview.spec_types import Spectrogram, TimeSeries
from specview.util import measure_runtime

from .time_view import TimeView
from .specan_view import SpecanView

dcache = diskcache.Cache( directory=user_cache_dir("specview", "jeremytrimble") )

log = logging.getLogger("specview")

def parse_args():
    parser = argparse.ArgumentParser(prog="specview", description="Display and annotate SigMF files")
    parser.add_argument("file", default=None, type=Path, help="Path to a SigMF file to open.")

    return parser.parse_args()

@dcache.memoize()
# note: Path not hashable repeatably
def load_capture(path:str, cap_idx:int):
    with measure_runtime("entirety of load_capture"):
        path = Path(path)
        smf = sigmf.sigmffile.fromfile(path)

        #sample_rate_Hz = cap.get(sigmf.SigMFFile.SAMPLE_RATE_KEY) or smf.get_global_field(sigmf.SigMFFile.SAMPLE_RATE_KEY)
        sample_rate_Hz = smf_get_field_cap_or_global(smf, cap_idx, sigmf.SigMFFile.SAMPLE_RATE_KEY)
        center_freq_Hz = smf_get_field_cap_or_global(smf, cap_idx, sigmf.SigMFFile.FREQUENCY_KEY, None)

        # TODO: capture as SpectrogramConfig pa.rameter
        NFFT = 512 
        win = scipy.signal.windows.hamming(NFFT)
        f = scipy.signal.ShortTimeFFT(
            win=win,
            hop=len(win)-len(win)//4,
            fs=sample_rate_Hz,
            fft_mode="centered",
        )

        with measure_runtime("timeseries loading"):
            timedomain_data = smf.read_samples_in_capture(0)
            #timedomain_data = timedomain_data[:1000000]    # TODO:remove!
        t = np.arange( len(timedomain_data) )/sample_rate_Hz

        with measure_runtime("FFT"):
            S = f.stft(timedomain_data)
        Smag_dB = 20*np.log10(np.abs(S))

        tdat = TimeSeries(
            time_sec=t,
            channels=["ch0"], #TODO
            data=timedomain_data.reshape([1,len(timedomain_data)]),
        )

        spec_freq_Hz = f.f
        spec_time_sec = f.t(len(timedomain_data))

        spec = Spectrogram(
            channels=["ch0"],    #TODO
            time_sec = spec_time_sec,
            freq_Hz=spec_freq_Hz,
            center_freq_Hz=center_freq_Hz,
            data = Smag_dB.reshape([1,len(spec_time_sec),len(spec_freq_Hz)]),
        )

        return tdat, spec




# Subclass QMainWindow to customize your application's main window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("The PySDR Spectrum Analyzer")
        #self.setFixedSize(QSize(1500, 1000)) # window size, starting size should fit on 1920 x 1080

        layout = QGridLayout() # overall layout

        self.time_view = TimeView(parent=self)
        self.specan_view = SpecanView(parent=self)

        # Time plot
        layout.addWidget(self.time_view, 1, 0)

        # Freq plot
        layout.addWidget(self.specan_view, 2, 0)

        # Layout container for waterfall related stuff
        waterfall_layout = QHBoxLayout()
        layout.addLayout(waterfall_layout, 3, 0)

        # Waterfall plot
        waterfall = pg.PlotWidget(labels={'left': 'Time [s]', 'bottom': 'Frequency [MHz]'})
        imageitem = pg.ImageItem(axisOrder='col-major') # this arg is purely for performance
        waterfall.addItem(imageitem)
        waterfall.setMouseEnabled(x=False, y=False)
        waterfall_layout.addWidget(waterfall)

        # Colorbar for waterfall
        colorbar = pg.HistogramLUTWidget()
        colorbar.setImageItem(imageitem) # connects the bar to the waterfall imageitem
        colorbar.item.gradient.loadPreset('viridis') # set the color map, also sets the imageitem
        imageitem.setLevels((-30, 20)) # needs to come after colorbar is created for some reason
        waterfall_layout.addWidget(colorbar)

        roiPen = pg.mkPen("red", width=3)
        roi = pg.RectROI(pos=(0,0), size=(200,400), sideScalers=True, rotatable=False)
        roi.setPen(roiPen)
        roi.sigRegionChanged.connect(lambda x:print(f"Region changed: {x.getArraySlice(returnSlice=False)}"))

        waterfall.addItem(roi)

        central_widget = QWidget()
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

        self.resize(QSize(2000,1500))

        self.imageitem = imageitem

def parse_args():
    parser = argparse.ArgumentParser(prog="specview", description="Display and annotate SigMF files")
    parser.add_argument("-C", "--clear-cache", default=False, action="store_true", help="Clear cache", dest="clear_cache")
    parser.add_argument("file", default=None, type=Path, help="Path to a SigMF file to open.")


    return parser.parse_args()

def main():

    logging.basicConfig(level=logging.INFO)

    args = parse_args()

    if args.clear_cache:
        dcache.clear()
    dcache.reset('size_limit', 10 *2**30)
    dcache.cull()


    log.info(f"cache size before: {dcache.volume()}")
    with measure_runtime(f"loading {args.file}"):
        tser, sgram = load_capture(str(args.file), 0)
    log.info(f"cache size after: {dcache.volume()}")

    app = QApplication([])
    window = MainWindow()
    window.show() # Windows are hidden by default
    signal.signal(signal.SIGINT, signal.SIG_DFL) # this lets control-C actually close the app

    LIMIT = 4096
    tser.data = tser.data[:,:LIMIT]

    window.time_view.setDisplayedTimeSeries(tser)

    window.specan_view.setDisplayedSpectrogramData(sgram)

    #window.time_plot_curve_i.setData(tser.data[0,:LIMIT].real)
    #window.time_plot_curve_q.setData(tser.data[0,:LIMIT].imag)
    window.imageitem.setImage(sgram.data[0,:LIMIT,:])


    app.exec() # Start the event loop

if __name__ == "__main__":
    main()
