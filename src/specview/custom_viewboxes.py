from PyQt6.QtCore import Qt
import pyqtgraph as pg
from .roi_select_viewboxes import IntervalSelectViewBox, RectSelectViewBox

class TimeScrollViewBox(IntervalSelectViewBox):
    """ViewBox that uses mouse wheel for horizontal panning"""

    def wheelEvent(self, ev, axis=None):
        if axis is None and ev.modifiers() == Qt.KeyboardModifier.NoModifier:
            delta = ev.delta() * 0.02  # Adjust this multiplier to control scroll speed
            rect = self.viewRect()
            # Translate the view along the x-axis
            dx = -delta * rect.width()
            self.translateBy(x=dx, y=0)
            ev.accept()
        else:
            # Pass other modifier key combinations to parent for standard behavior
            super().wheelEvent(ev, axis=axis)

class SpecanXZoomViewBox(IntervalSelectViewBox):
    """ViewBox that uses mouse wheel for X-axis zoom only"""
    
    def wheelEvent(self, ev):
        if ev.modifiers() == Qt.KeyboardModifier.NoModifier:
            rect = self.viewRect()
            center = rect.center()
            scale = 1.1 ** (ev.delta() * 0.1)  # Adjust this multiplier to control zoom speed
            
            # Scale only in X direction
            self.scaleBy(x=scale, y=1.0, center=center)
            ev.accept()
        else:
            # Pass other modifier key combinations to parent for standard behavior
            super().wheelEvent(ev)

class WaterfallScrollViewBox(RectSelectViewBox):
    """ViewBox that uses mouse wheel for vertical scrolling"""
    
    def wheelEvent(self, ev, axis=None):
        if axis is None and ev.modifiers() == Qt.KeyboardModifier.NoModifier:
            delta = ev.delta() * 0.02  # Adjust this multiplier to control scroll speed
            rect = self.viewRect()
            # Translate the view along the y-axis
            dy = -delta * rect.height()
            self.translateBy(x=0, y=dy)
            ev.accept()
        else:
            # Pass other modifier key combinations to parent for standard behavior
            super().wheelEvent(ev, axis=axis)