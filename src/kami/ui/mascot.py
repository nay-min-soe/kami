"""Kami's character: a soft pink blob with eyes, drawn in code (no image files).

Moods: idle (blinks; bobs gently in the open panel), listening (looks down at the
input), thinking (looks up, "..." badge), talking (pulse() per streamed repaint),
happy (^ ^ eyes and a jump), worried (brows up, a quick shake) and capture (squint).
A mood change blends the face over ~180 ms instead of cutting. hop() is the little
squash-and-jump every click gets.

Nothing runs while nothing moves: one frame timer ticks only during a hop, a blend,
a blink, the bob or the thinking dots. Blinks are a single-shot timer every few
seconds. set_active(False) stops both.
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import astuple, dataclass
from itertools import pairwise

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

log = logging.getLogger(__name__)

MOODS = ("idle", "listening", "thinking", "talking", "happy", "worried", "capture")
CALM = ("idle", "listening")   # the moods that bob

PINK = QColor("#FF6B9A")
INK = QColor("#1E1B2E")
CREAM = QColor("#FFF4DC")
YELLOW = QColor("#FFC93C")
BLUSH = QColor("#FF3D7F")

BLEND_S = 0.18
HOP_S = 0.26
JUMP_S = 0.34      # the happy jump: a bigger, slower hop
SHAKE_S = 0.32
PULSE_S = 0.14
BLINK_S = 0.14
BLINK_GAPS_MS = (3400, 5200, 2600, 4700, 6100)   # uneven, so it doesn't look mechanical
FAST_MS = 16       # while something hops, blends or blinks
SLOW_MS = 33       # bob and thinking dots only

FULL = QRectF(0, 0, 100, 100)   # the drawing space: room above the body for hops and "..."
TIGHT = QRectF(10, 18, 80, 80)  # just the body, for icons


@dataclass(frozen=True)
class _Face:
    """Everything a mood changes, as numbers we can blend."""
    eyes: float = 1.0     # how open; 0.12 is a squint
    arcs: float = 0.0     # 1 = happy ^ ^ eyes
    look_x: float = 0.0   # where the eyes look, -1..1
    look_y: float = 0.0
    worry: float = 0.0    # brows up in the middle
    smile: float = 0.35   # -1 frown .. 1 big smile
    mouth: float = 0.0    # how open the mouth is
    dots: float = 0.0     # the "..." badge
    blush: float = 0.6

    def blend(self, other: _Face, t: float) -> _Face:
        pairs = zip(astuple(self), astuple(other), strict=True)
        return _Face(*(a + (b - a) * t for a, b in pairs))


FACES = {
    "idle": _Face(),
    "listening": _Face(look_y=0.8, smile=0.25),
    "thinking": _Face(eyes=0.9, look_x=0.75, look_y=-0.85, smile=0.0, dots=1.0),
    "talking": _Face(look_y=0.15, mouth=0.25, smile=0.4),
    "happy": _Face(arcs=1.0, smile=1.0, blush=1.0),
    "worried": _Face(eyes=0.85, look_y=0.25, worry=1.0, smile=-0.7, blush=0.2),
    "capture": _Face(eyes=0.12, smile=0.0, blush=0.3),
}


@dataclass(frozen=True)
class _Motion:
    """Where the body is this frame: offsets in drawing units, scales about the feet."""
    dx: float = 0.0
    dy: float = 0.0
    sx: float = 1.0
    sy: float = 1.0
    mouth: float = 0.0   # added to the face's mouth (talking pulses)
    blink: float = 1.0   # eye openness multiplier


STILL = _Motion()


class Mascot(QWidget):
    """The character. Paints to fit any size; clicks pass through to the widget below."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._mood = "idle"
        self._from = self._to = FACES["idle"]
        self._fx: dict[str, tuple[float, float, float]] = {}   # name -> (start, secs, strength)
        self._active = False
        self._bob = False
        self._blinks = 0
        self._frame = QTimer(self)        # runs only while something moves
        self._frame.timeout.connect(self._tick)
        self._blink = QTimer(self)
        self._blink.setSingleShot(True)
        self._blink.timeout.connect(self._start_blink)

    @property
    def mood(self) -> str:
        return self._mood

    # ---------- public API ----------
    def set_mood(self, mood: str) -> None:
        if mood not in FACES:
            log.warning("unknown mascot mood %r ignored", mood)
            return
        if mood == self._mood:
            return
        now = time.monotonic()
        self._from, self._to, self._mood = self._face(now), FACES[mood], mood
        if not self._active:
            self._from = self._to   # nobody is watching: no animation
            self._fx.clear()
            self.update()
            return
        self._fx["blend"] = (now, BLEND_S, 1.0)
        if mood == "happy":
            self._fx["hop"] = (now, JUMP_S, 1.5)
        elif mood == "worried":
            self._fx["shake"] = (now, SHAKE_S, 1.0)
        self._wake()

    def hop(self) -> None:
        """Squash, jump, land. A hop still in its first half isn't restarted."""
        if not self._active:
            return
        now = time.monotonic()
        t = self._t("hop", now)
        if t is not None and t < 0.5:
            return
        self._fx["hop"] = (now, HOP_S, 1.0)
        self._wake()

    def pulse(self) -> None:
        """A tiny nudge with an open mouth, for each repaint of a streaming answer."""
        if self._active and "pulse" not in self._fx:
            self._fx["pulse"] = (time.monotonic(), PULSE_S, 1.0)
            self._wake()

    def set_active(self, active: bool, bob: bool = False) -> None:
        """False stops every timer (window hidden). True keeps a blink timer armed and
        animates on demand; `bob` adds the gentle idle bob (only in the open panel)."""
        self._bob = bob and active
        if not active:
            self._active = False
            self._frame.stop()
            self._blink.stop()
            self._fx.clear()
            self._from = self._to
            self.update()
            return
        self._active = True
        if not self._blink.isActive():
            self._arm_blink()
        self._wake()

    # ---------- animation ----------
    def _t(self, name: str, now: float) -> float | None:
        """How far effect `name` is, 0..1, or None if it isn't running."""
        if name not in self._fx:
            return None
        start, secs, _ = self._fx[name]
        return min(max((now - start) / secs, 0.0), 1.0)

    def _face(self, now: float) -> _Face:
        t = self._t("blend", now)
        if t is None:
            return self._to
        return self._from.blend(self._to, 1 - (1 - t) ** 3)   # ease out

    def _moving(self) -> bool:
        looping = (self._bob and self._mood in CALM) or self._to.dots > 0
        return bool(self._fx) or looping

    def _wake(self) -> None:
        """Start, slow down or stop the frame timer to match what's moving."""
        if not (self._active and self._moving()):
            self._frame.stop()
            return
        interval = FAST_MS if self._fx else SLOW_MS
        if self._frame.interval() != interval:
            self._frame.setInterval(interval)
        if not self._frame.isActive():
            self._frame.start()

    def _tick(self) -> None:
        now = time.monotonic()
        for name in [n for n in self._fx if self._t(n, now) >= 1.0]:
            del self._fx[name]
        if "blend" not in self._fx:
            self._from = self._to
        self.update()
        self._wake()

    def _arm_blink(self) -> None:
        self._blink.start(BLINK_GAPS_MS[self._blinks % len(BLINK_GAPS_MS)])
        self._blinks += 1

    def _start_blink(self) -> None:
        if not self._active:
            return
        if self._to.eyes > 0.5 and self._to.arcs < 0.5:   # no blinking mid-squint or ^ ^
            self._fx["blink"] = (time.monotonic(), BLINK_S, 1.0)
            self._wake()
        self._arm_blink()

    def _motion(self, now: float) -> _Motion:
        dx = dy = mouth = 0.0
        sx = sy = blink = 1.0
        if self._bob and self._mood in CALM:
            dy += 1.6 * math.sin(now * math.tau / 2.4)
        t = self._t("hop", now)
        if t is not None:
            amp = self._fx["hop"][2]
            k = _squash(t) * amp
            sy *= 1 + k
            sx *= 1 - 0.7 * k
            dy -= 11 * amp * math.sin(math.pi * min(max((t - 0.16) / 0.62, 0.0), 1.0))
        t = self._t("pulse", now)
        if t is not None:
            bump = math.sin(math.pi * t)
            sy *= 1 + 0.05 * bump
            sx *= 1 - 0.03 * bump
            mouth += 0.5 * bump
        t = self._t("shake", now)
        if t is not None:
            dx += 4.5 * math.sin(t * 2 * math.tau) * (1 - t)
        t = self._t("blink", now)
        if t is not None:
            blink = 1 - math.sin(math.pi * t)
        return _Motion(dx, dy, sx, sy, mouth, blink)

    def paintEvent(self, _event) -> None:
        now = time.monotonic()
        side = min(self.width(), self.height())
        box = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        _draw(p, box, self._face(now), self._motion(now), now)


def paint_face(painter: QPainter, rect: QRectF, mood: str = "idle",
               color: QColor | None = None) -> None:
    """Draw a still Kami filling `rect`, e.g. for the tray icon or a chip icon."""
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    _draw(painter, QRectF(rect), FACES.get(mood, FACES["idle"]), body=color or PINK,
          view=TIGHT)
    painter.restore()


def _squash(t: float) -> float:
    """Stretch (+) or squash (-) during a hop: crouch, stretch up, land, settle."""
    keys = ((0.0, 0.0), (0.16, -0.16), (0.34, 0.10), (0.72, 0.0), (0.84, -0.10), (1.0, 0.0))
    for (t0, v0), (t1, v1) in pairwise(keys):
        if t <= t1:
            return v0 + (v1 - v0) * (t - t0) / (t1 - t0)
    return 0.0


def _ink(alpha: float) -> QColor:
    color = QColor(INK)
    color.setAlphaF(min(max(alpha, 0.0), 1.0))
    return color


def _draw(p: QPainter, box: QRectF, face: _Face, motion: _Motion = STILL, now: float = 0.0,
          body: QColor = PINK, view: QRectF = FULL) -> None:
    """Paint in a 100x100 space (`view` of it) scaled into `box`, so any size is crisp."""
    p.save()
    p.translate(box.topLeft())
    p.scale(box.width() / view.width(), box.height() / view.height())
    p.translate(-view.x(), -view.y())

    p.save()
    p.translate(50 + motion.dx, 92 + motion.dy)   # squash and stretch about the feet
    p.scale(motion.sx, motion.sy)
    p.translate(-50, -92)
    _body(p, body)
    _cheeks(p, face)
    _eyes(p, face, motion.blink)
    _mouth(p, face, motion.mouth)
    p.restore()

    if face.dots > 0.01:
        _thinking_badge(p, face.dots, now)
    p.restore()


def _body(p: QPainter, color: QColor) -> None:
    path = QPainterPath(QPointF(50, 24))
    path.cubicTo(75, 24, 89, 42, 89, 63)
    path.cubicTo(89, 85, 76, 92, 50, 92)
    path.cubicTo(24, 92, 11, 85, 11, 63)
    path.cubicTo(11, 42, 25, 24, 50, 24)
    shade = QLinearGradient(50, 24, 50, 92)
    shade.setColorAt(0, color.lighter(115))
    shade.setColorAt(1, color)
    p.setPen(Qt.NoPen)
    p.setBrush(shade)
    p.drawPath(path)
    shine = QColor(CREAM)
    shine.setAlphaF(0.55)
    p.save()
    p.translate(33, 37)
    p.rotate(-28)
    p.setBrush(shine)
    p.drawEllipse(QPointF(0, 0), 8, 4.2)
    p.restore()


def _cheeks(p: QPainter, face: _Face) -> None:
    color = QColor(BLUSH)
    color.setAlphaF(0.45 * face.blush)
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    for x in (29, 71):
        p.drawEllipse(QPointF(x, 69), 6.5, 3.6)


def _eyes(p: QPainter, face: _Face, blink: float) -> None:
    open_ = face.eyes * blink
    round_alpha = 1 - face.arcs
    for side in (-1, 1):
        cx = 50 + side * 12 + face.look_x * 3.5
        cy = 58 + face.look_y * 3.5
        if round_alpha > 0.01:
            w, h = 9.0, max(2.2, 13.0 * open_)
            p.setPen(Qt.NoPen)
            p.setBrush(_ink(round_alpha))
            p.drawRoundedRect(QRectF(cx - w / 2, cy - h / 2, w, h), min(w, h) / 2, min(w, h) / 2)
            if open_ > 0.45:
                glint = QColor(CREAM)
                glint.setAlphaF(round_alpha)
                p.setBrush(glint)
                p.drawEllipse(QPointF(cx + 1.6, cy - h * 0.22), 1.7, 1.7)
        if face.arcs > 0.01:
            arc = QPainterPath(QPointF(cx - 5.5, cy + 2.5))
            arc.quadTo(cx, cy - 7, cx + 5.5, cy + 2.5)
            p.setPen(QPen(_ink(face.arcs), 3.2, Qt.SolidLine, Qt.RoundCap))
            p.setBrush(Qt.NoBrush)
            p.drawPath(arc)
        if face.worry > 0.01:
            inner, outer = QPointF(50 + side * 6.5, 44.5), QPointF(50 + side * 17, 48.5)
            p.setPen(QPen(_ink(face.worry), 2.6, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(inner, outer)


def _mouth(p: QPainter, face: _Face, extra: float) -> None:
    opened = face.mouth + extra
    if opened > 0.12:
        h = 2.5 + 8 * min(opened, 1.0)
        p.setPen(Qt.NoPen)
        p.setBrush(INK)
        p.drawEllipse(QPointF(50, 70 + h / 4), 3.8, h / 2)
        return
    smile = QPainterPath(QPointF(45.5, 69.5))
    smile.quadTo(50, 69.5 + 7 * face.smile, 54.5, 69.5)
    p.setPen(QPen(INK, 2.6, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(Qt.NoBrush)
    p.drawPath(smile)


def _thinking_badge(p: QPainter, amount: float, now: float) -> None:
    """A small yellow "..." bubble at the top right; the dots rise one after another."""
    bubble = QColor(YELLOW)
    bubble.setAlphaF(amount)
    p.setPen(Qt.NoPen)
    p.setBrush(bubble)
    p.drawEllipse(QPointF(64, 24), 2.4, 2.4)
    p.drawRoundedRect(QRectF(66, 4, 30, 15), 7.5, 7.5)
    p.setBrush(_ink(amount))
    for i in range(3):
        lift = max(0.0, math.sin(now * math.tau * 1.2 - i * 0.9))
        p.drawEllipse(QPointF(73.5 + i * 7.5, 11.5 - 1.8 * lift), 2.0, 2.0)
