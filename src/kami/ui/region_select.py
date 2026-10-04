"""Full-screen layer where the user drags a box around what they want explained."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget


class RegionSelector(QWidget):
    selected = Signal(QRect)   # global screen coordinates
    cancelled = Signal()

    def __init__(self) -> None:
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)
        self._origin: QPoint | None = None
        self._current: QPoint | None = None

    def start(self) -> None:
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        self.setGeometry(screen.geometry())
        self.showFullScreen()
        self.activateWindow()

    def _rect(self) -> QRect:
        return QRect(self._origin, self._current).normalized()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(30, 27, 46, 90))
        if self._origin and self._current:
            r = self._rect()
            p.setCompositionMode(QPainter.CompositionMode_Clear)
            p.fillRect(r, Qt.transparent)
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)
            p.setPen(QPen(QColor("#FF6B9A"), 4, Qt.DashLine))
            p.drawRect(r)

    def mousePressEvent(self, e) -> None:
        self._origin = self._current = e.position().toPoint()
        self.update()

    def mouseMoveEvent(self, e) -> None:
        if self._origin:
            self._current = e.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, _e) -> None:
        r = self._rect() if self._origin else QRect()
        self.hide()
        self._origin = self._current = None
        if r.width() > 10 and r.height() > 10:
            self.selected.emit(r.translated(self.geometry().topLeft()))
        else:
            self.cancelled.emit()

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_Escape:
            self.hide()
            self.cancelled.emit()
