"""The notch: a black pill at the top centre of the screen that grows into Kami's panel.

Collapsed it's a slim pill with Kami's face and four dots, and it doesn't take the
keyboard from your app. While Kami thinks it can fold into a smaller "chewing" pill:
just the monster, chewing. Expanded it's a compact bar: a status card (face, "Kami ·
Thinking", the last two steps), a 2x2 grid of chips, and `body`, where the panel puts
its input and answer. The open panel is as tall as its content: fit() measures the
layout and animates the height there, up to 60% of the screen (then the answer
scrolls). The window itself is a fixed size: a mask that follows the drawn shape lets
clicks through everywhere else, so the empty part never blocks the apps below.

X11 first. Native Wayland doesn't let apps place windows, so there the desktop decides
where the notch goes. It still works, it just isn't pinned to the top. There the window
mask is only the click area, so the content is clipped by its own mask instead.
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
CHEW_W = 56             # the chewing pill: just the monster
WIDE_W = 560
RADIUS = 22             # corner radius when open; the pill is fully round
SLACK_X, SLACK_Y = 12, 28   # spare window room for the expand overshoot
TOP_GAP = 8             # below the top of the screen (or the top bar)
PAD = 12
CARD_H = 80
FACE_SMALL = 32         # the face's box in the pill
FACE_BIG = 60           # the face's box in the status card
FACE_X = 12             # the face's inset from the pill's left end
MAX_SHARE = 0.6         # the open panel is at most this share of the screen's height
MIN_CAP = 240
EXPAND_MS = 280
COLLAPSE_MS = 200
GROW_MS = 180
PILL_MS = 160

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
                   padding: 5px 9px; font-size: 12px; font-weight: 700; text-align: left; }
QPushButton#chip:hover { background: #4A4560; }
QPushButton#chip:checked { background: #FF6B9A; color: #1E1B2E; }
"""


def _native_wayland() -> bool:
    """Qt runs on Wayland itself (not XWayland): no window placement, masks don't clip."""
    return QGuiApplication.platformName().startswith("wayland")


class _Tween(QVariantAnimation):
    """A number that animates to a target. A new target mid-way carries on from wherever
    the number is now, so nothing jumps."""

    def __init__(self, parent: QWidget, value: float, apply, close: float = 0.5) -> None:
        super().__init__(parent)
        self.value = float(value)
        self._apply = apply
        self._close = close   # nearer than this to the target counts as there
        self.valueChanged.connect(self._step)

    @property
    def running(self) -> bool:
        return self.state() == QAbstractAnimation.Running

    def _step(self, value) -> None:
        self.value = float(value)
        self._apply()

    def go(self, target: float, ms: int, curve: QEasingCurve) -> None:
        self.stop()
        if abs(target - self.value) < self._close:
            self.jump(target)
            return
        self.setStartValue(self.value)
        self.setEndValue(float(target))
        self.setDuration(ms)
        self.setEasingCurve(curve)
        self.start()

    def jump(self, value: float) -> None:
        self.stop()
        self.value = float(value)
        self._apply()


class Island(QWidget):
    """The notch window. Subclasses fill `body`, add chips, and call expand/collapse/fit."""

    pill_clicked = Signal()

    def __init__(self) -> None:
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.PointingHandCursor)
        self._expanded = False        # where we're heading, even mid-animation
        self._chewing = False         # the folded shape is the small chewing pill
        self._hand_back = True        # give the keyboard back when the fold ends
        self._told_wayland = False
        self._steps: list[tuple[str, str]] = []   # (mark, text), oldest first, at most 2
        self._dot_colors: list[QColor] = []
        self._big_face: QRectF | None = None
        self._cap = MIN_CAP           # the tallest the open panel may get on this screen
        self._open_target = 0.0       # how tall the open panel wants to be
        self._content_min = 0         # the content's layout never gets squeezed below this
        self._last_mask: tuple | None = None
        self._ready = False
        # 0 = folded, 1 = open (a little over 1 while overshooting)
        self._morph = _Tween(self, 0.0, self._apply, close=0.001)
        self._morph.finished.connect(self._settle)
        self._open_h = _Tween(self, CARD_H + 2 * PAD, self._apply)   # the open height
        self._pill = _Tween(self, PILL_W, self._apply)             # the folded width
        self._build_shell()
        self.mascot = Mascot(self)
        self.mascot.raise_()          # above the cards, so it can travel between pill and card
        self.set_mood("idle")
        self.setStyleSheet(ISLAND_STYLE)
        self._ready = True
        self._use_screen(QGuiApplication.primaryScreen())
        self.fit()

    # ---------- layout ----------
    def _build_shell(self) -> None:
        # _clip cuts the content to the shape while it morphs; content fades inside it.
        # (A mask and an opacity effect on the same widget draw the mask in the wrong place.)
        self._clip = QWidget(self)
        self._clip.hide()
        self.content = QWidget(self._clip)
        self._fade = QGraphicsOpacityEffect(self.content)
        self._fade.setEnabled(False)   # only during the fade: an effect re-renders everything
        self.content.setGraphicsEffect(self._fade)

        status = QFrame()
        status.setObjectName("card")
        status.setFixedHeight(CARD_H)
        row = QHBoxLayout(status)
        edge = (CARD_H - FACE_BIG) // 2
        row.setContentsMargins(edge, edge, 12, edge)
        row.setSpacing(10)
        self._face_spot = QWidget()   # the mascot itself flies here from the pill
        self._face_spot.setFixedSize(FACE_BIG, FACE_BIG)
        row.addWidget(self._face_spot, 0, Qt.AlignVCenter)
        text = QVBoxLayout()
        text.setSpacing(3)
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
        cards.setSpacing(8)
        cards.addWidget(status, 1)
        cards.addWidget(chips)
        outer = QVBoxLayout(self.content)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        outer.addLayout(cards)
        self.body = QVBoxLayout()     # the panel's input, answer and buttons go here
        self.body.setSpacing(8)
        outer.addLayout(self.body, 1)   # only the answer area in it stretches

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

    @property
    def is_chewing(self) -> bool:
        return self._chewing

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

    # ---------- placement and size ----------
    def place(self, screen: QScreen) -> None:
        """Top centre of `screen`. Native Wayland ignores move(), so there we say so once."""
        self._use_screen(screen)
        if _native_wayland():
            if not self._told_wayland:
                log.info("wayland: the desktop places windows, so the notch isn't pinned")
                self._told_wayland = True
            return
        area = screen.availableGeometry()
        self.move(area.x() + (area.width() - self.width()) // 2, area.top() + TOP_GAP)

    def _use_screen(self, screen: QScreen | None) -> None:
        """The open panel may use up to 60% of this screen's height; size the window to it."""
        if screen is None:
            return
        cap = max(MIN_CAP, int(screen.availableGeometry().height() * MAX_SHARE))
        if cap == self._cap and self.height() == cap + SLACK_Y:
            return
        self._cap = cap
        self.setFixedSize(WIDE_W + 2 * SLACK_X, cap + SLACK_Y)
        self._last_mask = None
        self.fit()

    def fit(self) -> bool:
        """Measure the content and grow or shrink the open panel to it (animated when you
        can see it). Returns True when it hit the 60% cap, so the answer has to scroll."""
        layout = self.content.layout()
        layout.activate()
        want = layout.sizeHint().height() + 2 * PAD
        self._content_min = layout.minimumSize().height()
        self._open_target = float(min(want, self._cap))
        self._follow_target()
        return want > self._cap

    def _follow_target(self) -> None:
        target = self._open_target
        if not self._expanded:
            if not self._morph.running:   # folded: nobody sees it, so just jump
                self._open_h.jump(target)
            return                        # folding: applied when the fold ends
        if not self.isVisible() or self._morph.value < 0.05:
            self._open_h.jump(target)       # about to open: the morph does the growing
            return
        heading = float(self._open_h.endValue()) if self._open_h.running else self._open_h.value
        if abs(target - heading) > 0.5:   # a new target mid-way carries on from here
            self._open_h.go(target, GROW_MS, QEasingCurve(QEasingCurve.OutCubic))

    # ---------- expand / collapse ----------
    def expand(self) -> None:
        if self._expanded:
            return
        self._expanded = True
        self._clip.show()
        self._find_big_face()
        self._follow_target()
        self.setCursor(Qt.ArrowCursor)
        curve = QEasingCurve(QEasingCurve.OutBack)
        curve.setOvershoot(1.1)   # about 4% past the end, then settle
        self._run_morph(1.0, EXPAND_MS, curve)

    def collapse(self, hand_back: bool = True) -> None:
        """Fold into the pill. hand_back=False keeps the keyboard (Kami is still busy)."""
        if not self._expanded:
            return
        self._expanded = False
        self._hand_back = hand_back
        self._open_h.stop()   # no growing while it folds; a new height waits for the end
        self._run_morph(0.0, COLLAPSE_MS, QEasingCurve(QEasingCurve.InOutCubic))

    def set_chewing(self, chewing: bool) -> None:
        """Fold into the small chewing pill (True) or the normal one with the dots."""
        if chewing == self._chewing:
            return
        self._chewing = chewing
        width = CHEW_W if chewing else PILL_W
        if self.isVisible() and (not self._expanded or self._morph.running):
            self._pill.go(width, PILL_MS, QEasingCurve(QEasingCurve.OutCubic))
        else:
            self._pill.jump(width)

    def _find_big_face(self) -> None:
        """Where the face goes in the open panel: the empty spot in the status card."""
        self.content.layout().activate()
        spot = self._face_spot.mapTo(self, QPoint(0, 0))
        self._big_face = QRectF(spot.x(), spot.y(), FACE_BIG, FACE_BIG)

    def _run_morph(self, end: float, ms: int, curve: QEasingCurve) -> None:
        if not self.isVisible():   # nothing to watch: jump straight there
            self._morph.jump(end)
            self._settle(hand_back=False)
            return
        self._sync_mascot()
        self._morph.go(end, ms, curve)
        if not self._morph.running:   # already there
            self._settle(hand_back=False)

    def _shape(self, progress: float) -> QRectF:
        fold_w = self._pill.value
        w = min(fold_w + (WIDE_W - fold_w) * progress, self.width())
        h = min(PILL_H + (self._open_h.value - PILL_H) * progress, self.height())
        return QRectF((self.width() - w) / 2, 0, w, h)

    def _radius(self, shape: QRectF, progress: float) -> float:
        k = min(max(progress, 0.0), 1.0)
        return min(PILL_H / 2 + (RADIUS - PILL_H / 2) * k, shape.height() / 2)

    def _small_face(self) -> QRectF:
        # The monster's middle sits ~55% down its box; line that up with the pill's.
        left = (self.width() - self._pill.value) / 2 + FACE_X
        return QRectF(left, PILL_H / 2 - FACE_SMALL * 0.55, FACE_SMALL, FACE_SMALL)

    def _apply(self) -> None:
        """Lay everything out for the current morph, open height and pill width."""
        if not self._ready:
            return
        progress = self._morph.value
        shape = self._shape(progress)
        radius = self._radius(shape, progress)
        key = (round(shape.x()), round(shape.width()), round(shape.height()), round(radius))
        if key != self._last_mask:
            self._last_mask = key
            mask = _mask(shape, radius)
            if _native_wayland():
                # A widget mask also limits what Qt repaints, and on Wayland it doesn't clip
                # what you see, so a shrinking shape left old frames behind. The window's
                # mask is only the click area there; the content mask below does the clipping.
                if self.windowHandle() is not None:
                    self.windowHandle().setMask(mask)
            else:
                self.setMask(mask)
        inner_w = WIDE_W - 2 * PAD
        inner_h = max(round(self._open_h.value) - 2 * PAD, self._content_min, 1)
        if self._clip.height() != inner_h or self._clip.width() != inner_w:
            self._clip.setGeometry(SLACK_X + PAD, PAD, inner_w, inner_h)
            self.content.setGeometry(0, 0, inner_w, inner_h)
        # The face travels in the first 60% of the morph; the text fades in after it,
        # so the two never overlap.
        k = min(max(progress / 0.6, 0.0), 1.0)
        k = k * k * (3 - 2 * k)
        small = self._small_face()
        big = self._big_face or small
        self.mascot.setGeometry(QRectF(
            small.x() + (big.x() - small.x()) * k, small.y() + (big.y() - small.y()) * k,
            small.width() + (big.width() - small.width()) * k,
            small.height() + (big.height() - small.height()) * k).toRect())
        opacity = min(max((progress - 0.6) / 0.35, 0.0), 1.0)
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
            self._open_h.jump(self._open_target)   # a fit that came in while folding
            if hand_back and self._hand_back:
                self._hand_back_focus()
        self._sync_mascot()

    def _hand_back_focus(self) -> None:
        # X11: a collapsed pill shouldn't keep the keyboard. Re-showing it without
        # activation makes the window manager focus the app below again. On native
        # Wayland a re-show can move the window, so there the pill keeps focus until
        # you click somewhere else.
        if not self.isActiveWindow() or _native_wayland():
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
        bob = self._expanded and not self._morph.running and self.isActiveWindow()
        self.mascot.set_compact(not self._expanded)
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
        self._last_mask = None   # also sets the Wayland click area, now it can
        self._apply()
        self._sync_mascot()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        moving = any(t.running for t in (self._morph, self._open_h, self._pill))
        if moving:
            self._pill.jump(CHEW_W if self._chewing else PILL_W)
            self._morph.jump(1.0 if self._expanded else 0.0)
            self._open_h.jump(self._open_target)
            self._settle(hand_back=False)   # never re-show a window that is hiding
        self._sync_mascot()

    def mousePressEvent(self, event) -> None:
        if not self._expanded and self._shape(self._morph.value).contains(event.position()):
            self.mascot.hop()
            self.pill_clicked.emit()
            return
        super().mousePressEvent(event)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        progress = self._morph.value
        shape = self._shape(progress)
        radius = self._radius(shape, progress)
        p.setPen(QPen(RIM, 1))
        p.setBrush(SHELL)
        p.drawRoundedRect(shape.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
        # The dots go first when it opens, and when it narrows into the chewing pill.
        wide = min(max((self._pill.value - CHEW_W) / (PILL_W - CHEW_W), 0.0), 1.0)
        fade = (1 - min(max(progress * 4, 0.0), 1.0)) * wide * wide
        if fade > 0.01:
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
