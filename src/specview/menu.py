from PyQt5.QtWidgets import QMenu, QMenuBar, QFileDialog
from PyQt5.QtCore import QObject
from PyQt5.QtWidgets import QApplication, QAction
from pathlib import Path

from .about_dialog import AboutDialog
from .fft_config_dialog import FFTConfigDialog
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

def _get_annotations_dict():
    """
    Get the annotations dictionary for the current capture.
    Returns None if no capture is selected or capture not found.
    """
    app_state: AppState = QApplication.instance().app_state  # type: ignore[union-attr]
    
    # Get the selected capture
    selected_capture_id = app_state._selected_capture
    if selected_capture_id is None:
        log.warning("No capture selected.")
        return None
    
    # Get the capture dictionary
    capture = app_state.get_capture_by_id(selected_capture_id)
    if capture is None:
        log.warning(f"Capture {selected_capture_id} not found.")
        return None
    
    # Get all annotations for this capture's parent file
    return capture.parent_loadedfile.get_annotations_dict()

def set_all_annotations_visible(visible: bool) -> None:
    """
    Set visibility for all annotations in the current capture.
    
    Args:
        visible: True to show all annotations, False to hide all annotations
    """
    annotations_dict = _get_annotations_dict()
    if annotations_dict is None:
        return
    
    # Set visibility for all annotations
    count = 0
    for annotation in annotations_dict.values():
        if annotation.visible != visible:
            annotation.visible = visible
            count += 1
    
    if count > 0:
        action = "Showed" if visible else "Hid"
        log.info(f"{action} {count} annotation(s)")
    else:
        status = "visible" if visible else "hidden"
        log.info(f"All annotations are already {status}")

def show_all_annotations() -> None:
    """
    Show all annotations in the current capture.
    """
    set_all_annotations_visible(True)

def hide_all_annotations() -> None:
    """
    Hide all annotations in the current capture.
    """
    set_all_annotations_visible(False)

def toggle_all_annotations() -> None:
    """
    Toggle visibility for all annotations in the current capture.
    If any annotation is hidden, show all. Otherwise, hide all.
    """
    annotations_dict = _get_annotations_dict()
    if annotations_dict is None:
        return
    
    if len(annotations_dict) == 0:
        log.info("No annotations to toggle")
        return
    
    # Determine if we should show all or hide all
    # If any annotation is hidden, show all. Otherwise, hide all.
    any_hidden = any(not ann.visible for ann in annotations_dict.values())
    
    if any_hidden:
        show_all_annotations()
    else:
        hide_all_annotations()

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


    # Create main file menu
    file_menu = QMenu("&File", menu_bar)
    file_menu.addAction(open_action)
    recent_files_menu = QMenu("Recent &Files", file_menu)
    file_menu.addMenu(recent_files_menu)
    file_menu.addSeparator()
    file_menu.addAction(save_action)

    
    # Add clear recent files action
    clear_recent_files_action = QAction("Clear Recent Files", parent)
    clear_recent_files_action.triggered.connect(
        lambda: QApplication.instance().app_state.clear_recent_files()
    )
    
    def update_recent_files_menu():
        recent_files_menu.clear()
        recent_files = QApplication.instance().app_state.get_recent_files()
        
        for file_path in recent_files:
            action = QAction(str(Path(file_path).name), parent)
            action.setData(file_path)
            action.setStatusTip(file_path)
            action.triggered.connect(
                lambda checked, path=file_path: 
                QApplication.instance().app_state.load_sigmf_file(path)
            )
            recent_files_menu.addAction(action)
            
        if recent_files:
            recent_files_menu.addSeparator()
        recent_files_menu.addAction(clear_recent_files_action)
    
    # Connect the signal to update the menu
    QApplication.instance().app_state.recent_files_changed.connect(update_recent_files_menu)
    
    # Initial population of recent files menu
    update_recent_files_menu()
    
    file_menu.addSeparator()
    #file_menu.addAction(save_as_action)
    #file_menu.addSeparator()
    #file_menu.addAction("E&xit", lambda: print("Exit action triggered"))

    annotation_from_selection = QAction(text="Annotation from Selection", parent=parent)
    annotation_from_selection.setShortcut("Ctrl+T")
    annotation_from_selection.triggered.connect(lambda: create_annotation_from_selection())

    show_all_action = QAction(text="Show All Annotations", parent=parent)
    #show_all_action.setShortcut("Ctrl+E")
    show_all_action.triggered.connect(show_all_annotations)
    
    hide_all_action = QAction(text="Hide All Annotations", parent=parent)
    #hide_all_action.setShortcut("Ctrl+Shift+E")
    hide_all_action.triggered.connect(hide_all_annotations)
    
    toggle_all_action = QAction(text="Toggle All Annotations", parent=parent)
    toggle_all_action.setShortcut("Ctrl+R")
    toggle_all_action.triggered.connect(toggle_all_annotations)

    annotations_menu = QMenu("&Annotations", menu_bar)
    annotations_menu.addAction(annotation_from_selection)
    annotations_menu.addSeparator()
    annotations_menu.addAction(show_all_action)
    annotations_menu.addAction(hide_all_action)
    annotations_menu.addAction(toggle_all_action)
    
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
    
    # Add reset layout action
    reset_layout_action = QAction(text="Reset Layout", parent=parent)
    reset_layout_action.triggered.connect(parent.reset_layout)
    view_menu.addAction(reset_layout_action)

    analysis_menu = QMenu("A&nalysis", menu_bar)

    # Add FFT settings action
    fft_settings_action = QAction(text="FFT Settings...", parent=parent)
    fft_settings_action.setShortcut("Ctrl+F")
    fft_settings_action.triggered.connect(lambda: FFTConfigDialog(QApplication.instance().app_state, parent).exec_())
    analysis_menu.addAction(fft_settings_action)

    analysis_menu.addSeparator()

    # Add FFT size adjustment actions
    increase_fft_action = QAction(text="More FFT Bins", parent=parent)
    increase_fft_action.setShortcut("Ctrl++")
    increase_fft_action.triggered.connect(lambda: QApplication.instance().app_state.increase_fft_size())
    analysis_menu.addAction(increase_fft_action)

    decrease_fft_action = QAction(text="Less FFT Bins", parent=parent)
    decrease_fft_action.setShortcut("Ctrl+-")
    decrease_fft_action.triggered.connect(lambda: QApplication.instance().app_state.decrease_fft_size())
    analysis_menu.addAction(decrease_fft_action)

    help_menu = QMenu("&Help", menu_bar)
    help_menu.addAction("&About", lambda: AboutDialog(parent).exec_())

    menu_bar.addMenu(file_menu)
    menu_bar.addMenu(view_menu)
    menu_bar.addMenu(analysis_menu)
    menu_bar.addMenu(annotations_menu)
    menu_bar.addMenu(help_menu)

def get_open_dir_dialog_initial_dir() -> str:
    """
    Get the initial directory for the open file dialog.
    """

    app_state: AppState = QApplication.instance().app_state
    capture = app_state._loaded_files.get_capture_from_id( app_state._selected_capture )
    if capture is not None:
        file_path = capture.parent_loadedfile.file_path
        if file_path is not None and file_path.parent.exists():
            return str(file_path.parent)

    recent_files = app_state.get_recent_files()
    if len(recent_files) > 0:
        recent_path = Path(recent_files[0])
        if recent_path.parent.exists():
            return str(recent_path.parent)

    return str(Path.cwd())

def present_open_file_dialog(parent):
    """
    Present an open file dialog to the user.
    Supports selecting multiple files at once.
    """
    options = QFileDialog.Options()
    options |= QFileDialog.ReadOnly
    file_names, _ = QFileDialog.getOpenFileNames(parent, "Open SigMF File(s)", get_open_dir_dialog_initial_dir(), "SigMF Files (*.sigmf-meta);;All Files (*)", options=options)
    if file_names:
        log.info(f"Selected files: {file_names}")
        app_state: AppState = QApplication.instance().app_state
        for file_name in file_names:
            app_state.load_sigmf_file(file_name)
    else:
        return None
