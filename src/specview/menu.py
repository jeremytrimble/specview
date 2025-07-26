from PyQt5.QtWidgets import QMenu, QMenuBar, QFileDialog
from PyQt5.QtCore import QObject


def populate_menubar(menu_bar: QMenuBar, parent:QObject):
    """
    Example Populate the menubar with the necessary menus and actions.
    """
    # TODO: make the menu do the real things I want
    file_menu = QMenu("File", menu_bar)
    file_menu.addAction("Open", lambda: present_open_file_dialog(parent))
    file_menu.addAction("Exit", lambda: print("Exit action triggered"))
    
    view_menu = QMenu("View", menu_bar)
    view_menu.addAction("Toggle Fullscreen", lambda: print("Toggle Fullscreen action triggered"))
    
    help_menu = QMenu("Help", menu_bar)
    help_menu.addAction("About", lambda: print("About action triggered"))

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
        print(f"Selected file: {file_name}")
        return file_name
    else:
        print("No file selected")
        return None
