from PyQt5.QtWidgets import QMenu, QMenuBar, QFileDialog
from PyQt5.QtCore import QObject
from PyQt5.QtWidgets import QApplication, QAction

from .app_state import AppState

import logging
log = logging.getLogger("menu")

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

    save_action = QAction(text="Save", parent=parent)
    save_action.setShortcut("Ctrl+S")
    save_action.triggered.connect(do_save)

    # TODO: make the menu do the real things I want
    file_menu = QMenu("&File", menu_bar)
    #file_menu.addAction("&Open", lambda: present_open_file_dialog(parent))
    file_menu.addAction(open_action)
    file_menu.addAction(save_action)
    file_menu.addSeparator()
    file_menu.addAction("E&xit", lambda: print("Exit action triggered"))
    
    view_menu = QMenu("&View", menu_bar)
    view_menu.addAction("Toggle &Fullscreen", lambda: print("Toggle Fullscreen action triggered"))
    
    help_menu = QMenu("&Help", menu_bar)
    help_menu.addAction("&About", lambda: print("About action triggered"))

    menu_bar.addMenu(file_menu)
    menu_bar.addMenu(view_menu)
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
