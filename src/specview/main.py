
from collections import deque
import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui
import sigmf

import scipy.signal
import scipy.signal.windows

import logging

from pathlib import Path
import argparse


log = logging.getLogger("specview")


def parse_args():
    parser = argparse.ArgumentParser(prog="specview", description="Display and annotate SigMF files")
    parser.add_argument("file", default=None, type=Path, help="Path to a SigMF file to open.")

    return parser.parse_args()


def load_file(path:Path):
    smf = sigmf.sigmffile.fromfile(path)
    return smf


def main():
    logging.basicConfig(level=logging.INFO)
    args = parse_args()

    #win = pg.GraphicsView()
    #win.resize(1000, 600)
    #win.setWindowTitle('specview')


    smf = load_file(args.file)

    captures = smf.get_captures()
    cap = captures[0]

    sample_rate_Hz = cap.get(sigmf.SigMFFile.SAMPLE_RATE_KEY) or smf.get_global_field(sigmf.SigMFFile.SAMPLE_RATE_KEY)


    NFFT = 1024
    win = scipy.signal.windows.hamming(NFFT)
    f = scipy.signal.ShortTimeFFT(
        win=win,
        hop=len(win)-len(win)//4,
        fs=sample_rate_Hz,
        fft_mode="centered",
    )

    data = smf.read_samples_in_capture(0)
    
    print(f"{data.shape=}")

    t = np.arange( len(data) )

    #t = t[:50000]
    #data = data[:50000]

    print(f"{sample_rate_Hz=}")
    print(f"{f.extent(len(data))=}")
    print(f"{f.p_num(len(t))=}")

    #wid = pg.PlotWidget()

    pw = pg.plot(t, data.real, pen='r')
    pw.plot(t, data.imag, pen='g')

    pw.setYRange(-1.1, +1.1)
    pw.setXRange(0, 1000)

    pg.exec()


if __name__ == "__main__":
    main()

    #import sys

    #if (sys.flags.interactive != 1) or not hasattr(QtCore, 'PYQT_VERSION'):
    #    QtGui.QApplication.instance().exec_()

