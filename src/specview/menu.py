from PyQt5.QtWidgets import QMenu, QMenuBar, QFileDialog
from PyQt5.QtCore import QObject
from PyQt5.QtWidgets import QApplication, QAction

from .about_dialog import AboutDialog
from .stfft_config_dialog import STFFTConfigDialog
from .app_state import AppState

import logging
import sigmf

log = logging.getLogger("menu")

def create_annotation_from_selection() -> None:
    """
    Create an annotation from the current time and frequency selections.
    """
    app_state: AppState = QApplication.instance().app_state  # type: ignore[union-attr]
    
    # Get the time interval (required)
    time_interval = app_state._time_interval
    if time_interval is None:
        log.warning("No time selection available. Cannot create annotation.")
        return
    
    # Get the frequency interval (optional)
    frequency_interval = app_state._frequency_interval
    
    # Get the selected capture
    selected_capture_id = app_state._selected_capture
    if selected_capture_id is None:
        log.warning("No capture selected. Cannot create annotation.")
        return
    
    # Get the capture dictionary
    capture = app_state.get_capture_by_id(selected_capture_id)
    if capture is None:
        log.warning(f"Capture {selected_capture_id} not found. Cannot create annotation.")
        return
    
    # Get the parent LoadedFile
    loaded_file = capture.parent_loadedfile
    
    # Get the sample rate from the SigMF file
    sample_rate = loaded_file.sigmf_file.get_global_field(sigmf.SigMFFile.SAMPLE_RATE_KEY)
    if sample_rate is None or sample_rate <= 0:
        log.error("Invalid or missing sample rate. Cannot create annotation.")
        return
    
    # Extract time bounds
    start_time_sec, end_time_sec = time_interval
    
    # Convert time to sample indices
    start_index = int(start_time_sec * sample_rate)
    end_index = int(end_time_sec * sample_rate)
    length = end_index - start_index
    
    if length <= 0:
        log.warning("Invalid time selection (end time must be greater than start time).")
        return
    
    # Generate a meaningful label
    
    # Create metadata dictionary
    metadata: dict[str, float | str] = {
        sigmf.SigMFFile.LABEL_KEY: "Changeme",
    }
    
    # Add frequency bounds if available
    if frequency_interval is not None:
        low_freq_Hz, high_freq_Hz = frequency_interval
        metadata[sigmf.SigMFFile.FLO_KEY] = low_freq_Hz
        metadata[sigmf.SigMFFile.FHI_KEY] = high_freq_Hz
    
    # Create the annotation
    try:
        annotation = loaded_file.add_annotation(
            start_index=start_index,
            length=length,
            metadata=metadata
        )
        log.info(f"Created annotation: {metadata[sigmf.SigMFFile.LABEL_KEY]}")
    except Exception as e:
        log.error(f"Failed to create annotation: {e}")

def populate_menubar(menu_bar: QMenuBar, parent:QObject):
    """
    Example Populate the menubar with the necessary menus and actions.
    """

    # TODO: move actions to central place?
    open_action = QAction(text="Open", parent=parent)
    open_action.setShortcut("Ctrl+O")
    open_action.triggered.connect(lambda: present_open_file_dialog(parent))

    def do_save():
        app_state: AppState = QApplication.instance().app_state
        app_state.save_current_file()

    #def do_save_as():
    #    app_state: AppState = QApplication.instance().app_state
    #    app_state.save_as(parent)

    save_action = QAction(text="Save", parent=parent)
    save_action.setShortcut("Ctrl+S")
    save_action.triggered.connect(do_save)

    #save_as_action = QAction(text="Save As...", parent=parent)
    #save_as_action.setShortcut("Ctrl+Shift+S")
    #save_as_action.triggered.connect(do_save_as)

    # TODO: make the menu do the real things I want
    file_menu = QMenu("&File", menu_bar)
    #file_menu.addAction("&Open", lambda: present_open_file_dialog(parent))
    file_menu.addAction(open_action)
    file_menu.addAction(save_action)
    #file_menu.addAction(save_as_action)
    #file_menu.addSeparator()
    #file_menu.addAction("E&xit", lambda: print("Exit action triggered"))

    annotation_from_selection = QAction(text="Annotation from Selection", parent=parent)
    annotation_from_selection.setShortcut("Ctrl+T")
    annotation_from_selection.triggered.connect(lambda: create_annotation_from_selection())

    annotations_menu = QMenu("&Annotations", menu_bar)
    annotations_menu.addAction(annotation_from_selection)
    
    # View menu for toggling plot visibility
    view_menu = QMenu("&View", menu_bar)
    
    # Get reference to main window to access dock widgets
    # Create toggle actions for each dock widget
    time_view_action = parent.time_dock.toggleViewAction()
    time_view_action.setText("&Time View")
    view_menu.addAction(time_view_action)
    
    specan_view_action = parent.specan_dock.toggleViewAction()
    specan_view_action.setText("&Spectrum Analyzer")
    view_menu.addAction(specan_view_action)
    
    waterfall_view_action = parent.waterfall_dock.toggleViewAction()
    waterfall_view_action.setText("&Waterfall")
    view_menu.addAction(waterfall_view_action)
    
    annotation_view_action = parent.annotation_dock.toggleViewAction()
    annotation_view_action.setText("&Annotations")
    view_menu.addAction(annotation_view_action)
    
    captures_view_action = parent.captures_dock.toggleViewAction()
    captures_view_action.setText("&Captures")
    view_menu.addAction(captures_view_action)
    
    view_menu.addSeparator()
    
    # Add STFFT settings action
    stfft_settings_action = QAction(text="STFFT Settings...", parent=parent)
    stfft_settings_action.triggered.connect(lambda: STFFTConfigDialog(QApplication.instance().app_state, parent).exec_())
    view_menu.addAction(stfft_settings_action)
    
    view_menu.addSeparator()
    
    # Add reset layout action
    reset_layout_action = QAction(text="Reset Layout", parent=parent)
    reset_layout_action.triggered.connect(parent.reset_layout)
    view_menu.addAction(reset_layout_action)
    
    help_menu = QMenu("&Help", menu_bar)
    help_menu.addAction("&About", lambda: AboutDialog(parent).exec_())

    menu_bar.addMenu(file_menu)
    menu_bar.addMenu(view_menu)
    menu_bar.addMenu(annotations_menu)
    menu_bar.addMenu(help_menu)

def present_open_file_dialog(parent):
    """
    Present an open file dialog to the user.
    """
    options = QFileDialog.Options()
    options |= QFileDialog.ReadOnly
    file_name, _ = QFileDialog.getOpenFileName(parent, "Open SigMF File", "", "SigMF Files (*.sigmf-meta);;All Files (*)", options=options)
    if file_name:
        log.info(f"Selected file: {file_name}")
        app_state: AppState = QApplication.instance().app_state
        app_state.load_sigmf_file(file_name)

    else:
        return None
