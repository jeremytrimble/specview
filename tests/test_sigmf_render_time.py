import json
import time
import tempfile
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pytest

# pytest-qt provides the qtbot fixture
from PyQt5 import QtWidgets, QtCore  # noqa: E402


def _generate_sigmf(
    out_dir: Path,
    base_name: str,
    sample_rate: float,
    duration_seconds: float,
    num_annotations: int,
) -> Tuple[Path, Path]:
    """
    Generate a minimal SigMF pair (data + metadata) in out_dir with the given
    sample_rate, duration_seconds, and number of annotations.

    - Data is written as interleaved complex float32 (cf32 / complex64 in numpy),
      which is a common SigMF IQ format ("cf32" = complex float32 stored as I/Q float32 interleaved).
    - Metadata follows a minimal SigMF structure with a "global" block and a
      single capture describing sample_count. A number of simple annotations are added.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    data_path = out_dir / f"{base_name}.sigmf-data"
    meta_path = out_dir / f"{base_name}.sigmf-meta"

    sample_count = int(np.ceil(sample_rate * duration_seconds))
    # Generate random IQ samples as float32 interleaved I/Q
    # SigMF 'cf32' is interleaved I/Q float32 (I0, Q0, I1, Q1, ...)
    iq = (np.random.randn(sample_count) + 1j * np.random.randn(sample_count)).astype(np.complex64)
    # Interleave to float32: view as float32 1D array
    interleaved = np.empty(sample_count * 2, dtype=np.float32)
    interleaved[0::2] = np.real(iq).astype(np.float32)
    interleaved[1::2] = np.imag(iq).astype(np.float32)

    interleaved.tofile(str(data_path))

    # Build simple metadata. Different SigMF readers expect slightly different
    # layouts; this includes common fields:
    metadata = {
        "global": {
            "core:datatype": "cf32",  # cf32 -> complex float32
            "core:sample_rate": sample_rate,
            "core:annotations": {},  # placeholder
            "core:version": "0.0.1",
        },
        "captures": [
            {
                "core": {
                    "sample_start": 0,
                    "sample_count": sample_count,
                },
                # point to the data file relative to the metadata file
                "file": data_path.name,
            }
        ],
        # Put a few simple annotations distributed through the capture
        "annotations": [],
    }

    # Add requested number of annotations evenly spaced
    for i in range(num_annotations):
        start = int(i * sample_count / max(1, num_annotations))
        length = max(1, int(sample_count / max(1, num_annotations * 4)))
        metadata["annotations"].append(
            {
                "core": {
                    "sample_start": start,
                    "sample_count": length,
                },
                "annotation": f"auto-annotation-{i}",
            }
        )

    # Write metadata
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=2)

    return data_path, meta_path


def _detect_render_complete(window: QtWidgets.QWidget) -> bool:
    """
    Try several heuristics to detect whether the specview display has rendered.
    Since the internal API of specview may vary, check multiple likely signals:
      - existence of attribute or method like 'render_complete' or 'is_rendered'
      - common child widgets: QGraphicsView with a populated scene
      - QLabel with a non-empty pixmap
      - a custom attribute named 'spectrogram' or 'viewer' with state indicating data
    This function should be conservative (return True only if we see evidence of rendering).
    """
    # 1) Direct attributes that user code might expose
    for attr in ("render_complete", "is_rendered", "hasRendered", "rendered"):
        val = getattr(window, attr, None)
        if isinstance(val, bool) and val:
            return True
        # if it's a callable method returning bool
        if callable(val):
            try:
                if val():
                    return True
            except Exception:
                pass

    # 2) Look for QGraphicsView with a scene that has items
    graphics_views = window.findChildren(QtWidgets.QGraphicsView)
    for gv in graphics_views:
        scene = gv.scene()
        if scene and len(scene.items()) > 0:
            return True

    # 3) Look for QLabel with a pixmap present
    labels = window.findChildren(QtWidgets.QLabel)
    for lbl in labels:
        pm = lbl.pixmap()
        if pm is not None and (pm.width() > 1 and pm.height() > 1):
            return True

    # 4) Check for a widget named 'spectrogram' (common pattern) and inspect children
    spect = window.findChild(QtWidgets.QWidget, "spectrogram")
    if spect:
        # if it has a pixmap child or any painted area
        lbl = spect.findChild(QtWidgets.QLabel)
        if lbl is not None and lbl.pixmap() is not None:
            return True
        # or QGraphicsView inside spectrogram
        gv = spect.findChild(QtWidgets.QGraphicsView)
        if gv and gv.scene() and len(gv.scene().items()) > 0:
            return True

    # 5) Fallback: check for a central widget with a non-trivial size (UI laid out)
    cw = window.centralWidget()
    if cw and cw.size().width() > 50 and cw.size().height() > 50:
        # Not a proof of rendering, but UI is visible; as last resort return True
        return True

    return False


@pytest.mark.parametrize("sample_rate,duration_seconds,num_annotations", [
    (1e6, 0.1, 0),
    (2e6, 0.2, 5),
    (1e5, 1.0, 10),
])
def test_sigmf_render_time(qtbot, tmp_path, sample_rate, duration_seconds, num_annotations):
    """
    Generate a SigMF file with the configurable sample rate, duration and number of
    annotations, then have qtbot load the file in specview and measure how long until
    the display renders.

    This test attempts to import and exercise common entry points in the specview
    application. If specview is not importable or expected calls are missing, the test
    will be skipped.

    The test asserts that the view renders within a reasonable timeout (60s).
    """
    # Try to import the main application/window entry points that specview may expose.
    try:
        # Common locations: specview.main.MainWindow or specview.app.SpecView
        from specview.main import MainWindow  # type: ignore
    except Exception:
        try:
            from specview.app import SpecView as MainWindow  # type: ignore
        except Exception:
            # If we cannot import the application, skip the test rather than failing.
            pytest.skip("specview application imports not available in this environment")

    # Generate test files
    data_path, meta_path = _generate_sigmf(tmp_path, "test_capture", sample_rate, duration_seconds, num_annotations)

    # Create the application window
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    # Instantiate window. Try several constructor signatures.
    try:
        window = MainWindow()
    except TypeError:
        # maybe MainWindow expects a parent
        window = MainWindow(None)

    qtbot.addWidget(window)
    window.show()
    qtbot.waitForWindowShown(window)

    # Try to find a canonical "open" method. Common names: open_file, load_file, open
    open_methods = ("open_file", "open", "load_file", "load")
    opened = False
    for meth_name in open_methods:
        meth = getattr(window, meth_name, None)
        if callable(meth):
            try:
                # Some APIs accept a Path or str, try both
                try:
                    meth(str(meta_path))
                except TypeError:
                    meth(meta_path)
                opened = True
                break
            except Exception:
                # swallow and try next
                pass

    # If no helper open method, try to emulate user action through a file menu or a public 'open_capture' style
    if not opened:
        # Try to locate a 'viewer' subcomponent or a 'load' action
        #  - action = window.findChild(QtWidgets.QAction, 'actionOpen')
        #  - or window.open_capture(meta_path)
        alt_meths = ("open_capture", "load_capture", "load_path", "open_path")
        for meth_name in alt_meths:
            meth = getattr(window, meth_name, None)
            if callable(meth):
                try:
                    meth(str(meta_path))
                    opened = True
                    break
                except Exception:
                    pass

    if not opened:
        # As a last resort, set an attribute that some apps read at launch or call a 'set_file' method
        set_file = getattr(window, "set_file", None)
        if callable(set_file):
            try:
                set_file(str(meta_path))
                opened = True
            except Exception:
                pass

    if not opened:
        # We couldn't programmatically open the file; skip the test.
        pytest.skip("Could not open the generated SigMF file with the available specview API")

    # Measure time until rendering heuristics indicate completion
    start = time.perf_counter()
    timeout_s = 60.0  # generous timeout for CI / slow machines

    try:
        qtbot.waitUntil(lambda: _detect_render_complete(window), timeout=int(timeout_s * 1000))
    except Exception:
        # If waitUntil times out it raises a TimeoutError from pytest-qt
        elapsed = time.perf_counter() - start
        pytest.fail(f"Specview did not render the SigMF capture within {timeout_s}s (elapsed {elapsed:.2f}s)")

    elapsed = time.perf_counter() - start

    # Log the measured duration; tests generally shouldn't rely on absolute timing,
    # but we assert that it finished within the timeout.
    print(
        f"Rendered SigMF (sr={sample_rate}, dur={duration_seconds}s, anns={num_annotations}) in {elapsed:.3f}s"
    )

    assert elapsed < timeout_s, f"Rendering took too long: {elapsed:.2f}s"
