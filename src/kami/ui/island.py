"""The notch: a black pill at the top centre of the screen that grows into Kami's panel.

Collapsed it's a slim pill with Kami's face and four dots, and it doesn't take the
keyboard from your app. Expanded it's a wide bar: a status card (face, "Kami · Thinking",
the last two steps), a 2x2 grid of chips, and `body`, where the panel puts its input and
answer. The window itself never changes size: a mask that follows the drawn shape lets
clicks through everywhere else, so the empty part never blocks the apps below.

X11 first. Native Wayland doesn't let apps place windows, so there the desktop decides
where the notch goes. It still works, it just isn't pinned to the top.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QEvent,
    QPoint,
    QPointF,
    QRectF,
    QSize,
    Qt,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QGuiApplication,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRegion,
    QScreen,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from kami.ui.mascot import MOODS, Mascot, paint_face

log = logging.getLogger(__name__)

PILL_W, PILL_H = 220, 34
WIDE_W, WIDE_H = 600, 470
RADIUS = 22             # corner radius when open; the pill is fully round
SLACK_X, SLACK_Y = 12, 22   # spare window room for the expand overshoot
TOP_GAP = 8             # below the top of the screen (or the top bar)
PAD = 12
CARD_H = 100
FACE_SMALL = 30         # the face in the pill
FACE_BIG = 72           # the face in the status card
EXPAND_MS = 280
COLLAPSE_MS = 200

SHELL = QColor("#0B0A10")
RIM = QColor(255, 244, 220, 28)   # a faint edge, so the notch reads on a black wallpaper

MOOD_WORDS = {
    "idle": "Idle", "listening": "Listening", "thinking": "Thinking", "talking": "Writing",
    "happy": "Done", "worried": "Oops", "capture": "Capturing",
}
MOOD_COLORS = {
    "idle": "#8A85A0", "listening": "#FFF4DC", "thinking": "#FFC93C", "talking": "#FF6B9A",
    "happy": "#7BE0A0", "worried": "#FF7A59", "capture": "#FFC93C",
}

ISLAND_STYLE = """
QFrame#card { background: #1E1B2E; border-radius: 16px; }
QLabel#header { color: #FFF4DC; font-size: 14px; font-weight: 800; }
QLabel#step { color: #8A85A0; font-size: 12px; }
QLabel#stepNow { color: #FFC93C; font-size: 12px; font-weight: 700; }
QPushButton#chip { background: #2A2640; color: #FFF4DC; border: none; border-radius: 12px;
                   padding: 7px 10px; font-size: 12px; font-weight: 700; text-align: left; }
QPushButton#chip:hover { background: #4A4560; }
QPushButton#chip:checked { background: #FF6B9A; color: #1E1B2E; }
"""


class Island(QWidget):
    """The notch window. Subclasses fill `body`, add chips, and call expand/collapse."""

    pill_clicked = Signal()

    def __init__(self) -> None:
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(WIDE_W + 2 * SLACK_X, WIDE_H + SLACK_Y)
        self.setCursor(Qt.PointingHandCursor)
        self._progress = 0.0          # 0 = pill, 1 = open (a little over 1 while overshooting)
        self._expanded = False        # where we're heading, even mid-animation
        self._told_wayland = False
        self._steps: list[tuple[str, str]] = []   # (mark, text), oldest first, at most 2
        self._dot_colors: list[QColor] = []
        self._big_face: QRectF | None = None
        self._morph = QVariantAnimation(self)
        self._morph.valueChanged.connect(self._set_progress)
        self._morph.finished.connect(self._settle)
        self._build_shell()
        self.mascot = Mascot(self)
        self.mascot.raise_()          # above the cards, so it can travel between pill and card
        self.set_mood("idle")
        self._set_progress(0.0)
        self.setStyleSheet(ISLAND_STYLE)

    # ---------- layout ----------
    def _build_shell(self) -> None:
        # _clip cuts the content to the shape while it morphs; content fades inside it.
        # (A mask and an opacity effect on the same widget draw the mask in the wrong place.)
        self._clip = QWidget(self)
        self._clip.setGeometry(SLACK_X + PAD, PAD, WIDE_W - 2 * PAD, WIDE_H - 2 * PAD)
        self._clip.hide()
        self.content = QWidget(self._clip)
        self.content.setGeometry(self._clip.rect())
        self._fade = QGraphicsOpacityEffect(self.content)
        self._fade.setEnabled(False)   # only during the fade: an effect re-renders everything
        self.content.setGraphicsEffect(self._fade)

        status = QFrame()
        status.setObjectName("card")
        status.setFixedHeight(CARD_H)
        row = QHBoxLayout(status)
        row.setContentsMargins(12, 12, 12, 12)
        row.setSpacing(10)
        self._face_spot = QWidget()   # the mascot itself flies here from the pill
        self._face_spot.setFixedSize(FACE_BIG, FACE_BIG)
        row.addWidget(self._face_spot, 0, Qt.AlignVCenter)
        text = QVBoxLayout()
        text.setSpacing(4)
        head = QHBoxLayout()
        head.setSpacing(6)
        self._dot = _Dot()
        self._header = QLabel()
        self._header.setObjectName("header")
        self._header.setTextFormat(Qt.PlainText)
        head.addWidget(self._dot, 0, Qt.AlignVCenter)
        head.addWidget(self._header, 1)
        self._lines = (_Line(), _Line())
        text.addStretch(1)
        text.addLayout(head)
        for line in self._lines:
            text.addWidget(line)
        text.addStretch(1)
        row.addLayout(text, 1)

        chips = QFrame()
        chips.setObjectName("card")
        chips.setFixedHeight(CARD_H)
        self._chips = QGridLayout(chips)
        self._chips.setContentsMargins(8, 8, 8, 8)
        self._chips.setSpacing(6)

        cards = QHBoxLayout()
        cards.setSpacing(10)
        cards.addWidget(status, 1)
        cards.addWidget(chips)
        outer = QVBoxLayout(self.content)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)
        outer.addLayout(cards)
        self.body = QVBoxLayout()     # the panel's input, answer and buttons go here
        self.body.setSpacing(10)
        outer.addLayout(self.body, 1)

    def add_chip(self, text: str, color: str) -> QPushButton:
        """A chip in the 2x2 grid with a little coloured Kami icon. Clicks hop the mascot;
        connect the action yourself. The pill's dots use the same colours."""
        chip = QPushButton(text)
        chip.setObjectName("chip")
        chip.setIcon(_chip_icon(QColor(color)))
        chip.setIconSize(QSize(16, 16))
        chip.setCursor(Qt.PointingHandCursor)
        chip.clicked.connect(self.mascot.hop)
        n = self._chips.count()
        self._chips.addWidget(chip, n // 2, n % 2)
        self._dot_colors.append(QColor(color))
        return chip

    # ---------- status ----------
    @property
    def mood(self) -> str:
        return self.mascot.mood

    @property
    def is_expanded(self) -> bool:
        return self._expanded

    def set_status(self, text: str, mood: str) -> None:
        """A new step ("Thinking...") plus the mood that goes with it. The step before
        it stays above with a check mark."""
        mark = {"happy": "✓", "worried": "!"}.get(mood, "›")
        if self._steps and self._steps[-1][1] == text:
            self._steps[-1] = (mark, text)
        else:
            self._steps = [("✓" if m == "›" else m, t) for m, t in self._steps[-1:]]
            self._steps.append((mark, text))
        rows = self._steps + [("", "")] * (2 - len(self._steps))
        newest = len(self._steps) - 1
        for i, (line, (step_mark, step_text)) in enumerate(zip(self._lines, rows, strict=True)):
            line.set_line(f"{step_mark} {step_text}" if step_text else "", current=i == newest)
        self.set_mood(mood)

    def set_mood(self, mood: str) -> None:
        """The mascot's mood and the header ("Kami · Thinking"), without a new step."""
        if mood not in MOODS:
            log.warning("unknown mood %r ignored", mood)
            return
        self.mascot.set_mood(mood)
        self._header.setText(f"Kami · {MOOD_WORDS[mood]}")
        self._dot.set_color(MOOD_COLORS[mood])

    # ---------- placement ----------
    def place(self, screen: QScreen) -> None:
        """Top centre of `screen`. Native Wayland ignores move(), so there we say so once."""
        if QGuiApplication.platformName().startswith("wayland"):
            if not self._told_wayland:
                log.info("wayland: the desktop places windows, so the notch isn't pinned")
                self._told_wayland = True
            return
        area = screen.availableGeometry()
        self.move(area.x() + (area.width() - self.width()) // 2, area.top() + TOP_GAP)

    # ---------- expand / collapse ----------
    def expand(self) -> None:
        if self._expanded:
            return
        self._expanded = True
        self._clip.show()
        self._find_big_face()
        self.setCursor(Qt.ArrowCursor)
        curve = QEasingCurve(QEasingCurve.OutBack)
        curve.setOvershoot(1.1)   # about 4% past the end, then settle
        self._run_morph(1.0, EXPAND_MS, curve)

    def collapse(self) -> None:
        if not self._expanded:
            return
        self._expanded = False
        self._run_morph(0.0, COLLAPSE_MS, QEasingCurve(QEasingCurve.InOutCubic))

    def _find_big_face(self) -> None:
        """Where the face goes in the open panel: the empty spot in the status card."""
        self.content.layout().activate()
        spot = self._face_spot.mapTo(self, QPoint(0, 0))
        self._big_face = QRectF(spot.x(), spot.y(), FACE_BIG, FACE_BIG)

    def _run_morph(self, end: float, ms: int, curve: QEasingCurve) -> None:
        self._morph.stop()
        if not self.isVisible():   # nothing to watch: jump straight there
            self._set_progress(end)
            self._settle(hand_back=False)
            return
        self._morph.setStartValue(self._progress)
        self._morph.setEndValue(end)
        self._morph.setDuration(ms)
        self._morph.setEasingCurve(curve)
        self._sync_mascot()
        self._morph.start()

    def _shape(self, progress: float) -> QRectF:
        w = min(PILL_W + (WIDE_W - PILL_W) * progress, self.width())
        h = min(PILL_H + (WIDE_H - PILL_H) * progress, self.height())
        return QRectF((self.width() - w) / 2, 0, w, h)

    def _radius(self, shape: QRectF, progress: float) -> float:
        k = min(max(progress, 0.0), 1.0)
        return min(PILL_H / 2 + (RADIUS - PILL_H / 2) * k, shape.height() / 2)

    def _small_face(self) -> QRectF:
        # The body's centre sits ~58% down the mascot's box; line that up with the pill's.
        left = (self.width() - PILL_W) / 2 + 6
        return QRectF(left, PILL_H / 2 - FACE_SMALL * 0.58, FACE_SMALL, FACE_SMALL)

    def _set_progress(self, value) -> None:
        self._progress = progress = float(value)
        shape = self._shape(progress)
        self.setMask(_mask(shape, self._radius(shape, progress)))
        k = min(max(progress, 0.0), 1.0)
        small = self._small_face()
        big = self._big_face or small
        self.mascot.setGeometry(QRectF(
            small.x() + (big.x() - small.x()) * k, small.y() + (big.y() - small.y()) * k,
            small.width() + (big.width() - small.width()) * k,
            small.height() + (big.height() - small.height()) * k).toRect())
        opacity = min(max((progress - 0.55) / 0.4, 0.0), 1.0)   # fade in once it's open
        self._fade.setOpacity(opacity)
        self._fade.setEnabled(opacity < 0.999)
        # The window mask clips drawing on X11 only (on Wayland it's just the click area),
        # so the content gets its own mask while the shape is smaller than it.
        inner = shape.translated(-self._clip.x(), -self._clip.y())
        if inner.contains(QRectF(self._clip.rect())):
            self._clip.clearMask()
        else:
            self._clip.setMask(_mask(inner, self._radius(shape, progress)))
        self.update()

    def _settle(self, hand_back: bool = True) -> None:
        """The morph ended (or was skipped)."""
        if not self._expanded:
            self._clip.hide()
            self.setCursor(Qt.PointingHandCursor)
            if hand_back:
                self._hand_back_focus()
        self._sync_mascot()

    def _hand_back_focus(self) -> None:
        # X11: a collapsed pill shouldn't keep the keyboard. Re-showing it without
        # activation makes the window manager focus the app below again. On native
        # Wayland a re-show can move the window, so there the pill keeps focus until
        # you click somewhere else.
        if not self.isActiveWindow() or QGuiApplication.platformName().startswith("wayland"):
            return
        self.hide()
        self.show_quietly(True)
        self.show()

    def show_quietly(self, quiet: bool) -> None:
        """The next show() takes keyboard focus (False) or leaves it alone (True). Qt reads
        the window property at show time; the widget attribute alone isn't passed on."""
        self.setAttribute(Qt.WA_ShowWithoutActivating, quiet)
        if self.windowHandle() is not None:
            self.windowHandle().setProperty("_q_showWithoutActivating", quiet)

    def _sync_mascot(self) -> None:
        """Animate only while you can see it; bob only in the open panel you're using."""
        moving = self._morph.state() == QAbstractAnimation.Running
        bob = self._expanded and not moving and self.isActiveWindow()
        self.mascot.set_active(self.isVisible(), bob=bob)

    # ---------- events ----------
    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.ActivationChange:
            self._sync_mascot()   # you clicked into another app: stop bobbing

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._expanded:   # opened while hidden: the card's layout only exists now
            self._find_big_face()
            self._set_progress(self._progress)
        self._sync_mascot()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        if self._morph.state() == QAbstractAnimation.Running:
            self._morph.stop()
            self._set_progress(1.0 if self._expanded else 0.0)
            self._settle(hand_back=False)   # never re-show a window that is hiding
        self._sync_mascot()

    def mousePressEvent(self, event) -> None:
        if not self._expanded and self._shape(self._progress).contains(event.position()):
            self.mascot.hop()
            self.pill_clicked.emit()
            return
        super().mousePressEvent(event)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        shape = self._shape(self._progress)
        radius = self._radius(shape, self._progress)
        p.setPen(QPen(RIM, 1))
        p.setBrush(SHELL)
        p.drawRoundedRect(shape.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
        fade = 1 - min(max(self._progress * 4, 0.0), 1.0)   # the dots go first
        if fade > 0:
            right = shape.right() - 14
            p.setPen(Qt.NoPen)
            for i, color in enumerate(self._dot_colors[:4]):
                dot = QColor(color)
                dot.setAlphaF(fade)
                p.setBrush(dot)
                x = right - 4.5 - (1 - i % 2) * 9
                y = PILL_H / 2 - 4.5 + (i // 2) * 9
                p.drawEllipse(QPointF(x, y), 3, 3)


class _Dot(QWidget):
    """The coloured status dot before "Kami · ..."."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(10, 10)
        self._color = QColor(MOOD_COLORS["idle"])

    def set_color(self, color: str) -> None:
        self._color = QColor(color)
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(self._color)
        p.drawEllipse(QRectF(1, 1, 8, 8))


class _Line(QLabel):
    """One plain-text step line that ends in "…" instead of running off the card."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("step")
        self.setTextFormat(Qt.PlainText)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._full = ""

    def set_line(self, text: str, current: bool) -> None:
        name = "stepNow" if current else "step"
        if self.objectName() != name:
            self.setObjectName(name)
            self.style().unpolish(self)
            self.style().polish(self)
        self._full = text
        self._elide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        width = max(self.width() - 2, 0)
        self.setText(self.fontMetrics().elidedText(self._full, Qt.ElideRight, width))


def _chip_icon(color: QColor) -> QIcon:
    pixmap = QPixmap(32, 32)          # drawn at 2x, so it stays sharp on HiDPI
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    paint_face(p, QRectF(0, 0, 16, 16), color=color)
    p.end()
    return QIcon(pixmap)


def _mask(shape: QRectF, radius: float) -> QRegion:
    """The clickable, visible area: the shape plus a pixel so the soft edge isn't cut."""
    path = QPainterPath()
    path.addRoundedRect(shape.adjusted(-1, -1, 1, 1), radius + 1, radius + 1)
    return QRegion(path.toFillPolygon().toPolygon())
