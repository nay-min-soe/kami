"""Kami's character: a shaggy red monster with gold ram horns, drawn in code (no images).

Moods: idle (blinks; bobs gently in the open panel), listening (looks down at the
input), thinking (chews: the jaw works, the eyes squint, the cheeks puff), talking
(pulse() per streamed repaint), happy (grin, arms up and a jump), worried (brows up,
small pupils, a sweat drop and a quick shake) and capture (a focused squint).
open_mouth(True) puts a wide-open "eating" mouth over any mood, for swallowing your
question. A mood change blends the face over ~180 ms instead of cutting. hop() is the
little squash-and-jump every click gets; set_compact(True) keeps it small enough to
stay inside the pill.

Small sizes are drawn simpler (fewer, bigger tufts, flat bright horns, bigger eyes,
three fat teeth), so the horns, eyes and teeth still read at 24-30 px. The parts that
never change with the mood (horns, legs, crest, fur) are rendered once per size into a
cached image; while the widget is being resized (the notch morph) a coarse version is
used and the sharp one comes back as soon as the size settles.

Nothing runs while nothing moves: one frame timer ticks only during a hop, a blend, a
blink, the bob or chewing. Blinks are a single-shot timer every few seconds.
set_active(False) stops both.
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import astuple, dataclass, replace
from functools import lru_cache
from itertools import pairwise

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QWidget

log = logging.getLogger(__name__)

MOODS = ("idle", "listening", "thinking", "talking", "happy", "worried", "capture")
CALM = ("idle", "listening")   # the moods that bob

BLEND_S = 0.18
HOP_S = 0.26
JUMP_S = 0.34      # the happy jump: a bigger, slower hop
SHAKE_S = 0.32
PULSE_S = 0.14
BLINK_S = 0.14
BLINK_GAPS_MS = (3400, 5200, 2600, 4700, 6100)   # uneven, so it doesn't look mechanical
FAST_MS = 16       # while something hops, blends or blinks
SLOW_MS = 33       # bob and chewing only
SHARPEN_MS = 150   # after the last resize, repaint once at full detail
COMPACT_HOP = 0.45  # hops in the pill: small enough that the horns stay inside it
CHEW_HZ = 2.8      # bites per second while thinking

# The drawing space is 100x100; these are the parts of it a box shows.
FULL = QRectF(-6, -14, 112, 112)  # room above the horns for a jump, beside for raised arms
TIGHT = QRectF(4, 5, 92, 92)      # just the monster, for icons

# ---------- palette ----------
HORN = QColor("#E3A532")
HORN_HI = QColor("#FFE49A")
HORN_DARK = QColor("#8E5B0E")
HORN_SMALL = QColor("#F4BC3C")    # brighter flat gold for tiny sizes
SCLERA = QColor("#FCF8F2")
SCLERA_EDGE = QColor("#D8B4B0")
IRIS_HI = QColor("#FFCB5C")
IRIS = QColor("#F2801C")
IRIS_DARK = QColor("#8F3506")
PUPIL = QColor("#130507")
MOUTH_TOP = QColor("#3E0816")
MOUTH_BOTTOM = QColor("#1A0308")
TONGUE = QColor("#C9475F")
TOOTH = QColor("#F4EDB8")
TOOTH_SHADE = QColor("#C9BB66")
TOOTH_LINE = QColor("#5E4E18")
CLAW = QColor("#3A2A2E")          # dark grey, not black: black vanishes on the notch
TOE = QColor("#EFE2C0")
SWEAT = QColor("#8FD3FF")
SWEAT_EDGE = QColor("#1D4E78")


@dataclass(frozen=True)
class _Fur:
    """The fur colours, light to deep. The default is Kami's crimson; paint_face can tint."""
    hi: str = "#F47A97"
    base: str = "#D5385C"
    mid: str = "#B42549"
    dark: str = "#82153A"
    deep: str = "#560A24"
    tip: str = "#9E1A3E"


CRIMSON = _Fur()


@lru_cache(maxsize=16)
def _tinted(rgb: int) -> _Fur:
    base = QColor.fromRgb(rgb)
    return _Fur(base.lighter(135).name(), base.name(), base.darker(118).name(),
                base.darker(165).name(), base.darker(250).name(), base.darker(135).name())


# ---------- the face, as numbers ----------
@dataclass(frozen=True)
class Face:
    """Everything a mood changes, as numbers we can blend."""
    eyes: float = 1.0      # upper lids: 1 open, 0 shut; >1 widens the eyes a little
    lower: float = 0.0     # lower lids pushed up: smiling / squinting eyes
    look_x: float = 0.0    # where the irises look, -1..1
    look_y: float = 0.0
    pupil: float = 1.0     # pupil size (small = scared)
    brow: float = 0.0      # how strong the fur brows are
    tilt: float = 0.0      # +1 worried (inner ends up), -1 focused (inner ends down)
    smile: float = 0.0     # -1 frown .. 1 grin
    mouth: float = 0.45    # jaw open, 0..1
    wide: float = 0.0      # the eating gape: a bigger, rounder mouth
    narrow: float = 0.0    # a smaller, rounder mouth (talking)
    chew: float = 0.0      # 1 = the jaw works on its own (thinking)
    arms: float = 0.0      # 0 hanging .. 1 raised
    sweat: float = 0.0     # a worry drop by the right horn

    def blend(self, other: Face, t: float) -> Face:
        pairs = zip(astuple(self), astuple(other), strict=True)
        return Face(*(a + (b - a) * t for a, b in pairs))


FACES = {
    "idle": Face(),
    "listening": Face(look_x=0.3, look_y=0.8, pupil=1.15, smile=0.3, mouth=0.1),
    "thinking": Face(eyes=0.88, lower=0.26, look_x=0.3, look_y=-0.3, smile=0.3,
                     mouth=0.0, chew=1.0),
    "talking": Face(look_y=0.1, smile=0.3, mouth=0.62, narrow=0.38),
    "happy": Face(eyes=0.96, lower=0.46, smile=1.0, mouth=0.6, arms=0.85),
    "worried": Face(eyes=1.08, pupil=0.55, brow=1.0, tilt=1.0, smile=-0.85, mouth=0.22,
                    look_y=0.15, arms=0.3, sweat=1.0),
    "capture": Face(eyes=0.45, lower=0.12, brow=1.0, tilt=-0.9, smile=0.05, mouth=0.0),
    "eating": Face(eyes=1.1, pupil=1.25, look_x=0.45, look_y=0.45, smile=0.25, mouth=1.0,
                   wide=1.0, arms=0.45),
}
FACES["chewing"] = FACES["thinking"]


@dataclass(frozen=True)
class _Motion:
    """Where the body is this frame: offsets in drawing units, scales about the feet."""
    dx: float = 0.0
    dy: float = 0.0
    sx: float = 1.0
    sy: float = 1.0
    mouth: float = 0.0   # added to the jaw (talking pulses)
    blink: float = 1.0   # eye openness multiplier


STILL = _Motion()


# ---------- the widget ----------
class Mascot(QWidget):
    """The character. Paints to fit any size; clicks pass through to the widget below."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._mood = "idle"
        self._mouth_open = False
        self._compact = False
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
        self._sharpen = QTimer(self)      # running = the size is still changing
        self._sharpen.setSingleShot(True)
        self._sharpen.setInterval(SHARPEN_MS)
        self._sharpen.timeout.connect(self.update)

    @property
    def mood(self) -> str:
        return self._mood

    # ---------- public API ----------
    def set_mood(self, mood: str) -> None:
        if mood not in MOODS:
            log.warning("unknown mascot mood %r ignored", mood)
            return
        if mood == self._mood:
            return
        self._mood = mood
        self._retarget(mood)

    def open_mouth(self, wide: bool) -> None:
        """The wide-open eating mouth, over whatever the mood is. False goes back to it."""
        if wide == self._mouth_open:
            return
        self._mouth_open = wide
        self._retarget()

    def set_compact(self, compact: bool) -> None:
        """Compact (in the pill): hops and jumps stay small enough to fit inside it."""
        self._compact = compact

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
            self._sharpen.stop()
            self._fx.clear()
            self._from = self._to
            self.update()
            return
        self._active = True
        if not self._blink.isActive():
            self._arm_blink()
        self._wake()

    def mouth_point(self) -> QPointF:
        """The middle of the mouth in the parent's coordinates (ignores hops): where the
        words of a question fly to."""
        box, scale = self._box()
        face = self._face(time.monotonic())
        local = box.center() + (QPointF(50, _mouth_centre_y(face)) - FULL.center()) * scale
        return QPointF(self.pos()) + local

    # ---------- animation ----------
    def _retarget(self, mood: str | None = None) -> None:
        now = time.monotonic()
        self._from = self._face(now)
        self._to = FACES["eating"] if self._mouth_open else FACES[self._mood]
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

    def _t(self, name: str, now: float) -> float | None:
        """How far effect `name` is, 0..1, or None if it isn't running."""
        if name not in self._fx:
            return None
        start, secs, _ = self._fx[name]
        return min(max((now - start) / secs, 0.0), 1.0)

    def _face(self, now: float) -> Face:
        t = self._t("blend", now)
        if t is None:
            return self._to
        return self._from.blend(self._to, 1 - (1 - t) ** 3)   # ease out

    def _moving(self) -> bool:
        calm = self._bob and self._mood in CALM and not self._mouth_open
        return bool(self._fx) or calm or self._to.chew > 0

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
        if self._to.eyes > 0.5 and self._to.lower < 0.2:   # no blinking mid-squint or grin
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
            amp = self._fx["hop"][2] * (COMPACT_HOP if self._compact else 1.0)
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

    def _box(self) -> tuple[QRectF, float]:
        side = min(self.width(), self.height())
        box = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        return box, side / FULL.width()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sharpen.start()   # restarts on every step of a morph

    def paintEvent(self, _event) -> None:
        now = time.monotonic()
        box, _ = self._box()
        p = QPainter(self)
        paint_monster(p, box, self._face(now), self._motion(now), now, FULL,
                      quick=self._sharpen.isActive())


def paint_face(painter: QPainter, rect: QRectF, mood: str = "idle",
               color: QColor | None = None) -> None:
    """Draw a still Kami filling `rect`, e.g. for the tray icon. `color` tints the fur."""
    face = replace(FACES.get(mood, FACES["idle"]), chew=0.0)
    fur = CRIMSON if color is None else _tinted(QColor(color).rgb())
    painter.save()
    paint_monster(painter, QRectF(rect), face, view=TIGHT, fur=fur)
    painter.restore()


def _squash(t: float) -> float:
    """Stretch (+) or squash (-) during a hop: crouch, stretch up, land, settle."""
    keys = ((0.0, 0.0), (0.16, -0.16), (0.34, 0.10), (0.72, 0.0), (0.84, -0.10), (1.0, 0.0))
    for (t0, v0), (t1, v1) in pairwise(keys):
        if t <= t1:
            return v0 + (v1 - v0) * (t - t0) / (t1 - t0)
    return 0.0


# ---------- drawing ----------
BODY = (50.0, 54.0, 34.0, 31.0)   # centre x, centre y, radius x, radius y
EYE_Y, EYE_DX, EYE_R = 36.0, 11.2, 10.4
MOUTH_Y = 47.6
HORN_PTS = (
    (30.0, 39.0), (22.0, 36.6), (15.4, 32.6), (10.4, 26.6), (8.4, 19.8), (9.4, 13.0),
    (13.2, 8.4), (18.6, 7.8), (21.8, 11.4), (21.4, 16.2), (17.8, 18.6), (14.6, 16.8),
    (14.6, 13.6),
)
STATIC_BOX = QRectF(-2, -2, 104, 102)   # horns, legs, crest and fur fit in here


def _mouth_centre_y(face: Face) -> float:
    gap = 2.6 + face.mouth * 19.0 * (1 + 0.22 * face.wide)
    return MOUTH_Y - 1.8 * face.wide + 2.4 * face.smile + gap * 0.55


def paint_monster(p: QPainter, rect: QRectF, face: Face, motion: _Motion = STILL,
                  now: float = 0.0, view: QRectF = TIGHT, fur: _Fur = CRIMSON,
                  quick: bool = False) -> None:
    """Paint the monster so `view` (a part of the 100x100 space) fits `rect`, centred.
    `quick` (mid-resize) uses the simple drawing and a coarse cached size."""
    rect = QRectF(rect)
    scale = min(rect.width() / view.width(), rect.height() / view.height())
    if scale <= 0:
        return
    size = scale * 100.0
    lod = 0 if quick or size < 46 else 1 if size < 80 else 2
    geo = _geometry(lod)

    phase = 0.5 - 0.5 * math.cos(now * math.tau * CHEW_HZ)   # 0 shut .. 1 open
    chew = face.chew
    bite = 0.5 if lod > 0 else 0.8           # small: a bigger bite, or it doesn't show
    jaw = face.mouth + motion.mouth + chew * bite * phase
    side_shift = chew * 1.3 * math.sin(now * math.tau * CHEW_HZ)
    lower = face.lower + chew * (0.14 if lod > 0 else 0.3) * (1 - phase)
    puff = chew * (1 - phase)
    lift = chew * 2.2 * phase                # the head bobs up as the jaw drops

    dpr = p.device().devicePixelRatioF() if p.device() is not None else 1.0
    step = 1.25 if quick else 1.03   # cache sizes: coarse while resizing, else within 3%
    px = step ** math.ceil(math.log(max(scale * dpr, 0.01)) / math.log(step))
    layer = _static_layer(lod, round(px, 4), fur)

    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.translate(rect.center())
    p.scale(scale, scale)
    p.translate(-view.center())
    p.translate(50 + motion.dx, 96 + motion.dy - lift)   # squash/stretch about the feet
    p.scale(motion.sx * (1 + 0.025 * puff), motion.sy * (1 - 0.02 * puff))
    p.translate(-50, -96)

    p.drawImage(STATIC_BOX, layer)        # horns, legs, crest, fur: cached per size
    for side in (-1, 1):
        _arm(p, geo, side, face.arms, lod, fur)
    open_ = face.eyes * motion.blink
    for side in (-1, 1):
        _eye(p, side, face, open_, lower, lod, fur)
    _mouth(p, face, jaw, side_shift, lod, fur)
    if face.sweat > 0.02:
        _sweat(p, face.sweat, lod)
    p.restore()


@lru_cache(maxsize=32)
def _static_layer(lod: int, px: float, fur: _Fur) -> QImage:
    """Horns, legs, crest and fur rendered once at `px` device pixels per unit."""
    w = max(1, math.ceil(STATIC_BOX.width() * px))
    h = max(1, math.ceil(STATIC_BOX.height() * px))
    img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    q = QPainter(img)
    q.setRenderHint(QPainter.Antialiasing)
    q.scale(w / STATIC_BOX.width(), h / STATIC_BOX.height())
    q.translate(-STATIC_BOX.x(), -STATIC_BOX.y())
    geo = _geometry(lod)
    for side in (-1, 1):
        _horn(q, geo.horns[side], lod)
    for x in (39.0, 61.0):
        _leg(q, geo, x, lod, fur)
    _crest(q, geo, fur)
    _body(q, geo, fur)
    q.end()
    return img


# ---------- geometry (built once per level of detail) ----------
def _rnd(i: int, salt: float) -> float:
    """A fixed 0..1 'random' number, so the fur is the same every frame."""
    v = math.sin(i * 12.9898 + salt * 78.233) * 43758.5453
    return v - math.floor(v)


def _unit(x: float, y: float) -> tuple[float, float]:
    d = math.hypot(x, y) or 1.0
    return x / d, y / d


@dataclass(frozen=True)
class _Horn:
    path: QPainterPath
    centre: tuple
    widths: tuple
    lefts: tuple
    rights: tuple


@dataclass(frozen=True)
class _Geo:
    horns: dict
    back: QPainterPath | None
    body: QPainterPath
    crest: tuple
    strokes: tuple
    arm: QPainterPath
    leg: QPainterPath


def _fur(cx: float, cy: float, rx: float, ry: float, n: int, tuft: float, seed: float,
         droop: float = 0.45, fringe: float = 0.0) -> QPainterPath:
    """An ellipse whose outline is n soft pointed tufts; side tufts droop, bottom ones hang."""
    def on(a: float, k: float = 1.0) -> QPointF:
        return QPointF(cx + rx * k * math.cos(a), cy + ry * k * math.sin(a))

    path = QPainterPath()
    step = math.tau / n
    start = -math.pi / 2 + seed * 0.37
    for i in range(n):
        av = start + i * step
        at = av + step * (0.5 + (_rnd(i, seed) - 0.5) * 0.5)
        an = av + step
        dx, dy = _unit(math.cos(at), math.sin(at) + droop)
        length = tuft * (0.6 + 0.8 * _rnd(i, seed + 1)) + fringe * max(0.0, math.sin(at)) ** 2
        tip = on(at) + QPointF(dx, dy) * length
        if i == 0:
            path.moveTo(on(av, 0.97))
        path.quadTo(on((av + at) / 2, 1.0) + QPointF(dx, dy) * length * 0.25, tip)
        path.quadTo(on((at + an) / 2, 1.0) + QPointF(dx, dy) * length * 0.2, on(an, 0.97))
    path.closeSubpath()
    return path


def _catmull(pts, steps: int) -> list[tuple[float, float]]:
    out = []
    n = len(pts)
    for i in range(n - 1):
        p0, p1, p2, p3 = pts[max(i - 1, 0)], pts[i], pts[i + 1], pts[min(i + 2, n - 1)]
        for s in range(steps):
            t = s / steps
            t2, t3 = t * t, t * t * t
            out.append(tuple(
                0.5 * (2 * p1[k] + (-p0[k] + p2[k]) * t
                       + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t2
                       + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t3)
                for k in (0, 1)))
    out.append(tuple(pts[-1]))
    return out


def _build_horn(side: int, lod: int) -> _Horn:
    """A ram's curl: a tapered tube around a smooth centre line."""
    pts = HORN_PTS if lod > 0 else HORN_PTS[:-3]       # shorter curl when tiny
    if side > 0:
        pts = tuple((100 - x, y) for x, y in pts)
    c = _catmull(pts, 7)
    run = [0.0]
    for a, b in pairwise(c):
        run.append(run[-1] + math.dist(a, b))
    total = run[-1]
    fat = 1.5 if lod == 0 else 1.0
    widths, lefts, rights = [], [], []
    for i, (x, y) in enumerate(c):
        t = run[i] / total
        w = (1.2 + 7.0 * (1 - t) ** 0.8) * fat
        a, b = c[max(i - 1, 0)], c[min(i + 1, len(c) - 1)]
        tx, ty = _unit(b[0] - a[0], b[1] - a[1])
        nx, ny = -ty, tx
        widths.append(w)
        lefts.append(QPointF(x + nx * w / 2, y + ny * w / 2))
        rights.append(QPointF(x - nx * w / 2, y - ny * w / 2))
    path = QPainterPath(lefts[0])
    for q in lefts[1:]:
        path.lineTo(q)
    tip = QPointF(*c[-1])
    path.quadTo(tip + (tip - QPointF(*c[-2])) * 0.6, rights[-1])
    for q in reversed(rights[:-1]):
        path.lineTo(q)
    path.closeSubpath()
    return _Horn(path, tuple(c), tuple(widths), tuple(lefts), tuple(rights))


def _build_crest(lod: int) -> tuple:
    """The fan of fur spikes on top of the head."""
    n = (5, 10, 15)[lod]
    hw = (2.6, 1.9, 1.5)[lod]
    cx, cy, rx, ry = BODY
    spikes = []
    for i in range(n):
        t = i / (n - 1)
        deg = -140 + 100 * t + (_rnd(i, 7) - 0.5) * 5
        a = math.radians(deg)
        base = QPointF(cx + rx * 0.88 * math.cos(a), cy + ry * 0.88 * math.sin(a))
        fan = math.radians(-90 + (deg + 90) * 1.4)
        d = QPointF(math.cos(fan), math.sin(fan))
        perp = QPointF(-d.y(), d.x())
        length = 6 + 11 * math.exp(-((deg + 90) / 30) ** 2) + 3 * _rnd(i, 8)
        if lod == 0:
            length *= 1.05
        bend = (_rnd(i, 9) - 0.5) * 3.0
        tip = base + d * length + perp * bend
        mid = base + d * length * 0.55 + perp * bend * 0.4
        path = QPainterPath(base - perp * hw)
        path.quadTo(mid - perp * hw * 0.4, tip)
        path.quadTo(mid + perp * hw * 0.4, base + perp * hw)
        path.closeSubpath()
        spikes.append((path, base, tip))
    return tuple(spikes)


def _build_strokes(lod: int) -> tuple:
    """Short fur strokes, light and dark, flowing out from the crown and down."""
    if lod == 0:
        return ()
    n = 70 if lod == 1 else 190
    cx, cy, rx, ry = BODY
    light, dark = QPainterPath(), QPainterPath()
    for i in range(n):
        r = math.sqrt(_rnd(i, 11)) * 0.96
        a = _rnd(i, 12) * math.tau
        x, y = cx + rx * r * math.cos(a), cy + ry * r * math.sin(a)
        dx, dy = _unit(x - 50, y - 24 + 6)
        dx, dy = _unit(dx, dy + 0.55)
        length = 2.0 + 2.8 * _rnd(i, 13)
        bend = (_rnd(i, 14) - 0.5) * 1.6
        start = QPointF(x, y)
        end = start + QPointF(dx, dy) * length
        ctrl = (start + end) / 2 + QPointF(-dy, dx) * bend
        path = light if _rnd(i, 15) < 0.48 else dark
        path.moveTo(start)
        path.quadTo(ctrl, end)
    return (light, dark)


@lru_cache(maxsize=3)
def _geometry(lod: int) -> _Geo:
    cx, cy, rx, ry = BODY
    n = (15, 30, 46)[lod]
    tuft = (3.6, 2.8, 2.5)[lod]
    back = None
    if lod > 0:
        back = _fur(cx, cy + 0.6, rx + 1.2, ry + 1.2, int(n * 0.8), tuft * 1.7, 3.0,
                    droop=0.25, fringe=1.6)
    body = _fur(cx, cy, rx, ry, n, tuft, 1.0, droop=0.18, fringe=1.4)
    arm = _fur(0, 9.0, 4.3, 9.8, (8, 11, 14)[lod], (2.0, 1.8, 1.6)[lod], 5.0, droop=0.9)
    leg = _fur(0, 0, 6.6, 5.6, (8, 11, 14)[lod], (1.8, 1.6, 1.4)[lod], 6.0, droop=0.3)
    return _Geo(
        horns={s: _build_horn(s, lod) for s in (-1, 1)},
        back=back, body=body, crest=_build_crest(lod), strokes=_build_strokes(lod),
        arm=arm, leg=leg,
    )


# ---------- painting the parts ----------
def _alpha(color: QColor | str, a: float) -> QColor:
    c = QColor(color)
    c.setAlphaF(min(max(a, 0.0), 1.0))
    return c


def _horn(p: QPainter, h: _Horn, lod: int) -> None:
    p.setPen(Qt.NoPen)
    if lod == 0:
        p.setBrush(HORN_SMALL)
        p.drawPath(h.path)
        p.save()
        p.setClipPath(h.path)
        p.setPen(QPen(_alpha(HORN_HI, 0.85), 1.6, Qt.SolidLine, Qt.RoundCap))
        for a, b, w in zip(h.centre, h.centre[1:], h.widths, strict=False):
            off = QPointF(-0.22, -0.28) * w
            p.drawLine(QPointF(*a) + off, QPointF(*b) + off)
        p.restore()
        return
    p.setBrush(HORN)
    p.drawPath(h.path)
    p.save()
    p.setClipPath(h.path)
    for a, b, w in zip(h.centre, h.centre[1:], h.widths, strict=False):   # shadow side
        off = QPointF(0.3, 0.32) * w
        p.setPen(QPen(_alpha(HORN_DARK, 0.55), w * 0.42, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(*a) + off, QPointF(*b) + off)
    for a, b, w in zip(h.centre, h.centre[1:], h.widths, strict=False):   # then shine
        off = QPointF(-0.2, -0.24) * w
        p.setPen(QPen(_alpha(HORN_HI, 0.75), w * 0.24, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(*a) + off, QPointF(*b) + off)
    every = 2 if lod == 2 else 3
    p.setPen(QPen(_alpha(HORN_DARK, 0.6), 0.42 if lod == 2 else 0.6, Qt.SolidLine,
                  Qt.RoundCap))
    p.setBrush(Qt.NoBrush)
    last = int(len(h.centre) * 0.88)
    for i in range(3, last, every):                          # the ribs
        mid = QPointF(*h.centre[i])
        a, b = QPointF(*h.centre[i - 1]), QPointF(*h.centre[i + 1])
        rib = QPainterPath(h.lefts[i])
        rib.quadTo(mid + (b - a) * 0.6, h.rights[i])
        p.drawPath(rib)
    p.restore()
    p.setPen(QPen(_alpha(HORN_DARK, 0.7), 0.5 if lod == 2 else 0.7))
    p.setBrush(Qt.NoBrush)
    p.drawPath(h.path)


def _leg(p: QPainter, geo: _Geo, x: float, lod: int, fur: _Fur) -> None:
    p.save()
    p.translate(x, 90.0)
    g = QLinearGradient(0, -6, 0, 6)
    g.setColorAt(0, QColor(fur.deep))
    g.setColorAt(1, QColor(fur.mid))
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawPath(geo.leg)
    if lod > 0:
        p.setBrush(TOE)
        for tx in (-3.6, 0.0, 3.6):
            toe = QPainterPath(QPointF(tx - 1.1, 5.0))
            toe.quadTo(QPointF(tx - 0.2, 7.8), QPointF(tx + 0.4, 7.6))
            toe.quadTo(QPointF(tx + 1.0, 6.4), QPointF(tx + 1.1, 5.0))
            toe.closeSubpath()
            p.drawPath(toe)
    p.restore()


def _crest(p: QPainter, geo: _Geo, fur: _Fur) -> None:
    p.setPen(Qt.NoPen)
    for path, base, tip in geo.crest:
        g = QLinearGradient(base, tip)
        g.setColorAt(0, QColor(fur.mid))
        g.setColorAt(1, QColor(fur.tip))
        p.setBrush(g)
        p.drawPath(path)


def _fur_light(fur: _Fur) -> QRadialGradient:
    """The body's lighting; eyelids reuse it so they melt into the fur."""
    cx, cy, rx, _ = BODY
    g = QRadialGradient(QPointF(cx, cy - 2), rx * 1.25, QPointF(cx - 9, cy - 16))
    g.setColorAt(0.0, QColor(fur.hi))
    g.setColorAt(0.42, QColor(fur.base))
    g.setColorAt(0.8, QColor(fur.mid))
    g.setColorAt(1.0, QColor(fur.dark))
    return g


def _body(p: QPainter, geo: _Geo, fur: _Fur) -> None:
    p.setPen(Qt.NoPen)
    if geo.back is not None:
        p.setBrush(QColor(fur.deep))
        p.drawPath(geo.back)
    p.setBrush(_fur_light(fur))
    p.drawPath(geo.body)
    if geo.strokes:
        p.save()
        p.setClipPath(geo.body)
        p.setBrush(Qt.NoBrush)
        light, dark = geo.strokes
        p.setPen(QPen(_alpha(fur.hi, 0.5), 0.6, Qt.SolidLine, Qt.RoundCap))
        p.drawPath(light)
        p.setPen(QPen(_alpha(fur.deep, 0.42), 0.6, Qt.SolidLine, Qt.RoundCap))
        p.drawPath(dark)
        p.restore()


def _arm(p: QPainter, geo: _Geo, side: int, raised: float, lod: int, fur: _Fur) -> None:
    p.save()
    p.translate(50 + side * 30.0, 58.5)
    if side > 0:
        p.scale(-1, 1)
    p.rotate(20 + 115 * raised)          # left arm; the mirror makes the right one
    p.setPen(Qt.NoPen)
    if lod > 0:                          # a soft shadow on the body, so the arm separates
        p.save()
        p.translate(1.6, 0.4)
        p.setBrush(_alpha(fur.deep, 0.7))
        p.drawPath(geo.arm)
        p.restore()
    g = QLinearGradient(-4, 0, 4, 18)
    g.setColorAt(0, QColor(fur.hi))
    g.setColorAt(0.5, QColor(fur.base))
    g.setColorAt(1, QColor(fur.mid))
    p.setBrush(g)
    p.drawPath(geo.arm)
    if lod > 0:
        p.setBrush(CLAW)
        p.setPen(QPen(_alpha(TOE, 0.7), 0.35))
        for i, tx in enumerate((-2.4, 0.0, 2.4)):
            claw = QPainterPath(QPointF(tx - 1.0, 17.6))
            claw.quadTo(QPointF(tx - 0.6, 20.8 + 0.5 * (i == 1)), QPointF(tx + 0.6, 21.4))
            claw.quadTo(QPointF(tx + 0.4, 19.4), QPointF(tx + 1.0, 17.6))
            claw.closeSubpath()
            p.drawPath(claw)
    p.restore()


def _sweat(p: QPainter, amount: float, lod: int) -> None:
    """A worry drop beside the right horn root; big and plain when tiny."""
    k = 1.5 if lod == 0 else 1.0
    x, y = 79.0, 30.0
    drop = QPainterPath(QPointF(x, y - 4.2 * k))
    drop.cubicTo(QPointF(x + 1.0 * k, y - 1.8 * k), QPointF(x + 2.6 * k, y),
                 QPointF(x + 2.6 * k, y + 1.4 * k))
    drop.cubicTo(QPointF(x + 2.6 * k, y + 3.2 * k), QPointF(x - 2.6 * k, y + 3.2 * k),
                 QPointF(x - 2.6 * k, y + 1.4 * k))
    drop.cubicTo(QPointF(x - 2.6 * k, y), QPointF(x - 1.0 * k, y - 1.8 * k),
                 QPointF(x, y - 4.2 * k))
    p.setPen(QPen(_alpha(SWEAT_EDGE, amount * 0.8), 0.5) if lod > 0 else Qt.NoPen)
    p.setBrush(_alpha(SWEAT, amount))
    p.drawPath(drop)
    if lod > 0:
        p.setPen(Qt.NoPen)
        p.setBrush(_alpha("white", amount * 0.85))
        p.drawEllipse(QPointF(x - 0.9, y + 1.0), 0.7, 1.0)


def _eye(p: QPainter, side: int, face: Face, open_: float, lower: float, lod: int,
         fur: _Fur) -> None:
    grow = 1.0 + 0.6 * max(face.eyes - 1.0, 0.0) + (0.1 if lod == 0 else 0.0)
    r = EYE_R * grow
    cx, cy = 50 + side * EYE_DX, EYE_Y
    open_ = min(open_, 1.0)
    if lod == 0:                     # tiny: squint less, or the eyes vanish
        open_ = 1 - (1 - open_) * 0.6
        lower *= 0.65
    seen = min(max(open_ - lower, 0.0), 1.0)
    p.setPen(Qt.NoPen)
    if lod > 0:                                            # furry socket shadow
        p.setBrush(_alpha(fur.deep, 0.25 + 0.5 * seen))
        p.drawEllipse(QPointF(cx, cy + 0.6), r + 1.5, r + 1.4)
    ball = QPainterPath()
    ball.addEllipse(QPointF(cx, cy), r, r)
    if lod == 0:
        p.setBrush(SCLERA)
    else:
        g = QRadialGradient(QPointF(cx, cy), r, QPointF(cx - r * 0.3, cy - r * 0.35))
        g.setColorAt(0.0, SCLERA)
        g.setColorAt(0.72, SCLERA)
        g.setColorAt(1.0, SCLERA_EDGE)
        p.setBrush(g)
    p.drawPath(ball)

    p.save()
    p.setClipPath(ball)
    ir = r * (0.56 if lod == 0 else 0.5)
    ix, iy = cx + face.look_x * r * 0.36, cy + face.look_y * r * 0.36
    ig = QRadialGradient(QPointF(ix, iy), ir, QPointF(ix, iy + ir * 0.35))
    ig.setColorAt(0.0, IRIS_HI)
    ig.setColorAt(0.55, IRIS)
    ig.setColorAt(1.0, IRIS_DARK)
    p.setBrush(ig)
    p.drawEllipse(QPointF(ix, iy), ir, ir)
    p.setBrush(PUPIL)
    pr = ir * (0.56 if lod == 0 else 0.5) * face.pupil
    p.drawEllipse(QPointF(ix, iy), pr, pr)
    p.setBrush(_alpha("white", 0.95))
    p.drawEllipse(QPointF(ix - ir * 0.38, iy - ir * 0.42), ir * 0.3, ir * 0.27)
    if lod > 0:
        p.drawEllipse(QPointF(ix + ir * 0.4, iy + ir * 0.38), ir * 0.11, ir * 0.11)
    p.restore()

    if lod > 0:                                            # rim, then lids cover it
        p.setPen(QPen(_alpha(fur.deep, 0.85), 0.7 if lod == 2 else 0.9))
        p.setBrush(Qt.NoBrush)
        p.drawPath(ball)

    cover = QPainterPath()
    cover.addEllipse(QPointF(cx, cy), r + 0.7, r + 0.7)
    lash_pen = QPen(QColor(fur.deep), (1.6, 1.0, 0.85)[lod], Qt.SolidLine, Qt.RoundCap)
    shine_pen = QPen(_alpha(fur.hi, 0.75), (0.0, 0.8, 0.6)[lod], Qt.SolidLine, Qt.RoundCap)
    p.save()
    p.setClipPath(cover)
    if open_ < 0.985:                                      # upper lid comes down
        edge = cy - r + 2 * r * (1 - open_)
        a, b = QPointF(cx + r + 1, edge - r * 0.22), QPointF(cx - r - 1, edge - r * 0.22)
        c = QPointF(cx, edge + r * 0.28)
        lid = QPainterPath(QPointF(cx - r - 1, cy - r - 1))
        lid.lineTo(cx + r + 1, cy - r - 1)
        lid.lineTo(a)
        lid.quadTo(c, b)
        lid.closeSubpath()
        _lid(p, lid, fur, QLinearGradient(cx, cy - r, cx, edge + r * 0.1), 0.35)
        lash = QPainterPath(a)
        lash.quadTo(c, b)
        if lod > 0:                                         # the lid's rounded edge
            p.setPen(shine_pen)
            p.drawPath(lash.translated(0, -1.0))
        p.setPen(lash_pen)
        p.drawPath(lash)
    if lower > 0.015:                                      # lower lid pushes up, curved
        edge = cy + r - 2 * r * lower
        a, b = QPointF(cx + r + 1, edge + r * 0.32), QPointF(cx - r - 1, edge + r * 0.32)
        c = QPointF(cx, edge - r * 0.42)
        lid = QPainterPath(QPointF(cx - r - 1, cy + r + 1))
        lid.lineTo(cx + r + 1, cy + r + 1)
        lid.lineTo(a)
        lid.quadTo(c, b)
        lid.closeSubpath()
        _lid(p, lid, fur, QLinearGradient(cx, cy + r, cx, edge - r * 0.3), 0.3)
        rim = QPainterPath(a)
        rim.quadTo(c, b)
        if lod > 0:
            p.setPen(shine_pen)
            p.drawPath(rim.translated(0, 0.9))
        p.setPen(lash_pen)
        p.drawPath(rim)
    p.restore()

    if face.brow > 0.02:                                   # fur brow tufts
        y = cy - r - 1.6 + (1 - open_) * r * 0.55
        inner = QPointF(cx - side * r * 0.45, y - face.tilt * 3.0)
        outer = QPointF(cx + side * r * 0.95, y + face.tilt * 1.2)
        d = outer - inner
        ln = math.hypot(d.x(), d.y()) or 1.0
        nrm = QPointF(-d.y() / ln, d.x() / ln) * side
        brow = QPainterPath(inner + nrm * 1.9)
        brow.quadTo((inner + outer) / 2 + nrm * 1.6, outer)
        brow.quadTo((inner + outer) / 2 - nrm * 0.6, inner - nrm * 1.4)
        brow.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(_alpha(fur.deep, face.brow))
        p.drawPath(brow)


def _lid(p: QPainter, lid: QPainterPath, fur: _Fur, shade: QLinearGradient,
         dark: float) -> None:
    """A furry eyelid: the body's own gradient, darker towards its edge."""
    p.setPen(Qt.NoPen)
    p.setBrush(_fur_light(fur))
    p.drawPath(lid)
    shade.setColorAt(0, _alpha(fur.deep, 0.0))
    shade.setColorAt(1, _alpha(fur.deep, dark))
    p.setBrush(shade)
    p.drawPath(lid)
    p.setBrush(Qt.NoBrush)


def _tooth(length: float, w: float) -> QPainterPath:
    """A crooked peg hanging down from (0, 0)."""
    path = QPainterPath(QPointF(-w / 2, -0.8))
    path.lineTo(-w * 0.42, length - w * 0.45)
    path.quadTo(QPointF(-w * 0.38, length), QPointF(0.05 * w, length))
    path.quadTo(QPointF(w * 0.42, length), QPointF(w * 0.45, length - w * 0.5))
    path.lineTo(w / 2, -0.8)
    path.closeSubpath()
    return path


UPPER_TEETH = (0.66, 0.92, 1.0, 0.8, 0.97, 0.6)   # relative lengths, left to right
LOWER_TEETH = (0.7, 1.0, 0.75, 0.95, 0.65)


def _mouth(p: QPainter, face: Face, jaw: float, shift: float, lod: int, fur: _Fur) -> None:
    jaw = min(max(jaw, 0.0), 1.3)
    smile = face.smile
    cx = 50 + shift
    hw = (21.0 + 4.0 * face.wide + 1.5 * max(smile, 0.0)) * (1 - 0.32 * face.narrow)
    if lod == 0:
        hw *= 1.06
    top = MOUTH_Y - 1.8 * face.wide
    corner = top + 3.0 - 4.5 * smile
    y_u = top + 2.4 * smile
    gap = (2.6 if lod > 0 else 3.6) + jaw * 19.0 * (1 + 0.22 * face.wide)
    y_l = y_u + gap + 2.0 * max(smile, 0.0)
    k = 0.5 + 0.38 * min(jaw, 1.0) + 0.1 * face.narrow       # rounder bottom when open
    ctrl_u = 2 * y_u - corner
    ctrl_l = (8 * y_l - 2 * corner) / 6

    def upper_y(x: float) -> float:
        s = (x - (cx - hw)) / (2 * hw)
        return (1 - s) ** 2 * corner + 2 * (1 - s) * s * ctrl_u + s * s * corner

    def lower_y(x: float) -> float:
        lo, hi = 0.0, 1.0      # the lower lip is monotone in x: find it by bisection
        x0, x1, x2, x3 = cx + hw, cx + hw * k, cx - hw * k, cx - hw
        for _ in range(18):
            s = (lo + hi) / 2
            xs = ((1 - s) ** 3 * x0 + 3 * (1 - s) ** 2 * s * x1 + 3 * (1 - s) * s * s * x2
                  + s ** 3 * x3)
            if xs > x:
                lo = s
            else:
                hi = s
        s = (lo + hi) / 2
        return ((1 - s) ** 3 * corner + 3 * (1 - s) ** 2 * s * ctrl_l
                + 3 * (1 - s) * s * s * ctrl_l + s ** 3 * corner)

    left, right = QPointF(cx - hw, corner), QPointF(cx + hw, corner)
    mouth = QPainterPath(left)
    mouth.quadTo(QPointF(cx, ctrl_u), right)
    mouth.cubicTo(QPointF(cx + hw * k, ctrl_l), QPointF(cx - hw * k, ctrl_l), left)
    mouth.closeSubpath()

    g = QLinearGradient(cx, y_u, cx, y_l)
    g.setColorAt(0, MOUTH_TOP)
    g.setColorAt(1, MOUTH_BOTTOM)
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawPath(mouth)

    if gap > 8 and lod > 0:                                 # tongue in a wide-open mouth
        p.save()
        p.setClipPath(mouth)
        p.setBrush(_alpha(TONGUE, min(1.0, (gap - 8) / 6)))
        p.drawEllipse(QPointF(cx + shift * 0.5, y_l - gap * 0.08), hw * 0.5, gap * 0.28)
        p.restore()

    n_up, n_lo = ((3, 2), (5, 4), (6, 5))[lod]
    pick_up = (1, 2, 4) if n_up == 3 else (0, 1, 2, 4, 5) if n_up == 5 else range(6)
    pick_lo = (1, 3) if n_lo == 2 else (0, 1, 3, 4) if n_lo == 4 else range(5)
    fat = 1.3 if lod == 0 else 1.0
    line = QPen(_alpha(TOOTH_LINE, 0.55), 0.35 if lod == 2 else 0.5)

    def draw_row(count, lens, picks, span, down, base_len):
        for j, i in enumerate(picks):
            t = (j + 0.5) / count
            x = cx - hw * span + 2 * hw * span * t + (_rnd(i, 21 + down) - 0.5) * 1.2
            local = lower_y(x) - upper_y(x)
            if local < 0.6:
                continue
            w = 2 * hw * span / count * (0.6 + 0.16 * _rnd(i, 23 + down)) * fat
            if down:
                length = min(lens[i] * base_len, local * 0.88 + 1.0)
                y = upper_y(x)
            else:
                length = min(lens[i] * base_len, local * 0.5 + 0.6)
                y = lower_y(x)
            tilt = (_rnd(i, 25 + down) - 0.5) * 16
            p.save()
            p.translate(x, y)
            p.rotate(tilt if down else 180 + tilt)
            tg = QLinearGradient(0, 0, 0, length)
            tg.setColorAt(0, TOOTH_SHADE)
            tg.setColorAt(0.3, TOOTH)
            tg.setColorAt(1, TOOTH_SHADE if lod > 0 else TOOTH)
            p.setBrush(tg)
            p.setPen(line if lod > 0 else Qt.NoPen)
            p.drawPath(_tooth(length, w))
            p.restore()

    p.save()
    p.setClipPath(mouth)
    draw_row(n_lo, LOWER_TEETH, pick_lo, 0.66, 0, 5.4)
    draw_row(n_up, UPPER_TEETH, pick_up, 0.8, 1, 11.5)
    p.restore()

    if lod > 0:                                             # lips
        p.setPen(QPen(_alpha(fur.deep, 0.9), 1.0 if lod == 2 else 1.3, Qt.SolidLine,
                      Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.drawPath(mouth)
