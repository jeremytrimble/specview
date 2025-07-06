import pyqtgraph as pg
from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtWidgets import QGraphicsSceneMouseEvent


class IntervalSelectViewBox(pg.ViewBox):
    def __init__(self, parent=None, border=None, lockAspect=False, enableMouse=True, invertY=False, enableMenu=True, name=None, invertX=False, defaultPadding=0.02):
        super().__init__(parent, border, lockAspect, enableMouse, invertY, enableMenu, name, invertX, defaultPadding)
        self._sv = None
        self._left_bound = None

        self._plot : pg.PlotWidget|None = None
        self._interval_roi : pg.LinearRegionItem|None = None

    def set_plot_and_interval(self, plot, interval_roi):
        self._plot = plot
        self._interval_roi = interval_roi

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        pos :QPointF = event.scenePos()
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            if self._plot.sceneBoundingRect().contains(pos):
                mousePoint = self._plot.getViewBox().mapSceneToView(pos)

                self._left_bound = mousePoint.x()

                self._interval_roi.setRegion( ( self._left_bound, self._left_bound+1.0 ) )
                self._interval_roi.setVisible(True)   # TODO: emit signal
                return event.accept()

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        #print(f"drag: {event=}")
        if self._left_bound is not None:
            pos :QPointF = event.scenePos()
            if self._plot.sceneBoundingRect().contains(pos):
                mousePoint = self._plot.getViewBox().mapSceneToView(pos)

                self._interval_roi.setRegion( ( self._left_bound, mousePoint.x() ) )
            return event.accept()

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        #print(f"release: {event=}")

        accepted = False

        if self._left_bound is not None:
            pos :QPointF = event.scenePos()
            if self._plot.sceneBoundingRect().contains(pos):
                mousePoint = self._plot.getViewBox().mapSceneToView(pos)
                self._interval_roi.setRegion( ( self._left_bound, mousePoint.x() ) )
            else:
                self._interval_roi.setVisible(False)   # TODO: emit signal
            event.accept()
            accepted = True

        self._is_dragging = False
        self._left_bound = None

        if not accepted:
            super().mouseReleaseEvent(event)

    def mouseClickEvent(self, ev):
        self._interval_roi.setVisible(False)   # TODO: emit signal
        return super().mouseClickEvent(ev)