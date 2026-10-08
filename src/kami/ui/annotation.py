"""Click-through layer that doodles on the screen: circles, arrows and notes."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from kami.geometry import Rect, layer_rect, place_label, to_point
from kami.modes.learning import Annotation

INK = QColor("#FF6B9A")
NOTE_BG = QColor(30, 27, 46, 220)
NOTE_FG = QColor("#FFC93C")
PAD = 60  # room for labels just outside the region
LABEL_MAX_PX = 220
EDGE = 4  # labels keep this far from the layer's edge


class AnnotationLayer(QWidget):
    def __init__(self, hide_after_ms: int = 25_000) -> None:
        super().__init__(
            None,
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
            | Qt.WindowTransparentForInput,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self._items: list[Annotation] = []
        self._region = QRectF()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(hide_after_ms)
        self._timer.timeout.connect(self.clear)

    def show_annotations(self, region: QRect, items: list[Annotation], screen: QRect) -> None:
        """`region` and `screen` are global logical coordinates (Qt's, so HiDPI-scaled)."""
        layer, inner = layer_rect(_rect(region), _rect(screen), PAD)
        self.setGeometry(QRect(int(layer.x), int(layer.y), int(layer.w), int(layer.h)))
        self._region = QRectF(inner.x, inner.y, inner.w, inner.h)
        self._items = items
        self.show()
        self.update()
        self._timer.start()

    def clear(self) -> None:
        self._items = []
        self.hide()

    def _pt(self, x: float, y: float) -> QPointF:
        r = self._region
        return QPointF(*to_point(Rect(r.x(), r.y(), r.width(), r.height()), x, y))

    def _note(self, p: QPainter, anchor: QPointF, text: str, taken: list[Rect]) -> None:
        if not text:
            return
        metrics = p.fontMetrics()
        text = metrics.elidedText(text, Qt.ElideRight, LABEL_MAX_PX)
        size = (metrics.horizontalAdvance(text) + 20, metrics.height() + 10)
        bounds = Rect(EDGE, EDGE, self.width() - 2 * EDGE, self.height() - 2 * EDGE)
        spot = place_label((anchor.x(), anchor.y()), size, bounds, taken)
        taken.append(spot)
        box = QRectF(spot.x, spot.y, spot.w, spot.h)
        p.setPen(Qt.NoPen)
        p.setBrush(NOTE_BG)
        p.drawRoundedRect(box, 8, 8)
        p.setPen(NOTE_FG)
        p.drawText(box, Qt.AlignCenter, text)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setFont(QFont("Sans", 13, QFont.Bold))
        pen = QPen(INK, 5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        side = min(self._region.width(), self._region.height())
        taken: list[Rect] = []

        for a in self._items:
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            if a.type == "circle":
                c, rad = self._pt(a.x, a.y), a.r * side
                p.drawEllipse(c, rad * 1.15, rad)          # a bit wobbly, like a marker
                self._note(p, c + QPointF(rad, -rad) * 0.75, a.label, taken)
            elif a.type == "arrow":
                start, end = self._pt(a.x, a.y), self._pt(a.x2, a.y2)
                mid = (start + end) / 2 + QPointF(0, -25)
                path = QPainterPath(start)
                path.quadTo(mid, end)
                p.drawPath(path)
                angle = math.atan2(end.y() - mid.y(), end.x() - mid.x())
                for wing in (angle + 2.6, angle - 2.6):
                    p.drawLine(end, end + QPointF(math.cos(wing), math.sin(wing)) * 22)
                self._note(p, start, a.label, taken)
            elif a.type == "text":
                self._note(p, self._pt(a.x, a.y), a.label, taken)


def _rect(r: QRect) -> Rect:
    return Rect(r.x(), r.y(), r.width(), r.height())
