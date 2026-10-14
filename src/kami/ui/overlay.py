"""Kami's panel inside the notch: Ask, Explain screen, Meeting notes.

The notch shell (pill, expand/collapse, status card, chips) is `ui/island.py`; this
file fills it and runs the requests. The mascot's mood follows each request, and each
request plays out on the notch: press Enter and the words you typed fly into the
monster's mouth, the panel folds into the small chewing pill while Kami thinks, then
opens again and grows with the answer as it streams in (an error always reopens it).
The answer area and its buttons only show when there is something in them.
"""
from __future__ import annotations

import logging
import math
import os
import re
import threading
import time
from collections.abc import Callable

from PySide6.QtCore import (
    QBuffer,
    QByteArray,
    QIODevice,
    QPoint,
    QPointF,
    QRect,
    QSize,
    Qt,
    QTimer,
    QUrl,
)
from PySide6.QtGui import (
    QColor,
    QCursor,
    QDesktopServices,
    QFont,
    QFontMetricsF,
    QGuiApplication,
    QPainter,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextBrowser,
    QWidget,
)

from kami.config import Config
from kami.conversation import Conversation
from kami.geometry import scaled_size
from kami.llm import LLMClient
from kami.modes import learning, meetings
from kami.session import Session, capture_failed_message
from kami.ui.annotation import AnnotationLayer
from kami.ui.island import Island
from kami.ui.region_select import RegionSelector
from kami.ui.worker import run_in_background

log = logging.getLogger(__name__)

CONTEXT_READY = "📷 Screen captured · type your question, or press Enter to explain it"
CONTEXT_CHAT = "📷 Asking about your screen capture · New chat to stop"
PLACEHOLDER_ASK = "Ask anything, then press Enter"
PLACEHOLDER_CAPTURE = "Ask about the capture (or just press Enter)"

STYLE = """
QLabel#context { color: #FFC93C; font-size: 12px; }
QLineEdit { background: #1E1B2E; color: #FFF4DC; border: 2px solid #2A2640;
            border-radius: 12px; padding: 8px; font-size: 15px; }
QLineEdit:focus { border-color: #FF6B9A; }
QLineEdit:disabled { color: #8A85A0; }
QTextBrowser { background: #1E1B2E; color: #FFF4DC; border: none;
               border-radius: 14px; padding: 8px; font-size: 14px; }
QScrollBar:vertical { background: transparent; width: 6px; margin: 6px 0; }
QScrollBar::handle:vertical { background: #4A4560; border-radius: 3px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QPushButton { background: #2A2640; color: #FFF4DC; border: none; border-radius: 12px;
              padding: 7px 14px; font-weight: 700; }
QPushButton:hover { background: #4A4560; }
QPushButton:disabled { background: #1E1B2E; color: #4A4560; }
QPushButton#stop { background: #FF6B9A; color: #1E1B2E; }
"""

# Chip colours; the pill's four dots use them too.
CHIP_PINK, CHIP_YELLOW, CHIP_MUTED, CHIP_CREAM = "#FF6B9A", "#FFC93C", "#8A85A0", "#FFF4DC"

ONE_LINE = 36       # the answer area is never shorter than one line
MAX_BITES = 12      # words that fly into the mouth; the rest go as one "…"
BITE_CHARS = 18     # a longer word is cut short with "…"
STAGGER_MS = 40     # between one word and the next
FLIGHT_MS = 350     # one word's trip into the mouth
GULP_MS = 260       # nothing to fly (an empty question): just the open mouth and a gulp


class KamiOverlay(Island):
    def __init__(self, config: Config, session: Session) -> None:
        super().__init__()
        self.config = config
        self.session = session   # from session.detect() in app.py; never re-read here
        self.client = LLMClient(config.llm)
        self.selector = RegionSelector()
        self.selector.selected.connect(self._on_region)
        self.selector.cancelled.connect(self.summon)
        self.doodles = AnnotationLayer()
        self.chat = Conversation()
        # (png, region, screen) waiting for the user's question; memory only, never logged
        self._capture: tuple[bytes, QRect, QRect] | None = None
        self._answer = ""      # Markdown source of the last real answer, never status/errors
        self._generation = 0   # bumped per request and on New chat; stale replies are dropped
        self._cancel: threading.Event | None = None      # set to stop the running stream
        self._stream: tuple[str, list[str]] | None = None  # (question, pieces so far)
        self._repaint = QTimer(self)
        self._repaint.setSingleShot(True)
        self._repaint.setInterval(50)   # repaint at most every 50 ms, not on every token
        self._repaint.timeout.connect(self._paint_stream)
        self._bites: _Bites | None = None   # the question's words on their way into the mouth
        self._after_eat = "fold"            # once they're swallowed: "fold" or "show"
        self._auto_folded = False           # we folded into the chewing pill, not you
        self._has_answer = False            # the answer area has something in it
        self._build()

    # ---------- layout ----------
    def _build(self) -> None:
        self.pill_clicked.connect(self._open)
        for text, color, slot in (
            ("Explain screen", CHIP_PINK, self.explain_screen),
            ("Meeting notes", CHIP_YELLOW, self.meeting_notes),
            ("Clear doodles", CHIP_MUTED, self.doodles.clear),
        ):
            self.add_chip(text, color).clicked.connect(slot)
        self.keep_button = self.add_chip("Keep", CHIP_CREAM)
        self.keep_button.setCheckable(True)
        self.keep_button.setToolTip("Keep doodles on screen until you click Clear doodles")
        self.keep_button.toggled.connect(self.doodles.set_keep)

        layout = self.body
        self.context = QLabel(CONTEXT_CHAT)
        self.context.setObjectName("context")
        self.context.hide()
        layout.addWidget(self.context)

        self.input = QLineEdit()
        self.input.setPlaceholderText(PLACEHOLDER_ASK)
        self.input.returnPressed.connect(self.ask)
        self.input.textEdited.connect(self._typing)
        layout.addWidget(self.input)

        self.output = _Answer()
        # Answers can repeat links from a screenshot, so we vet every click ourselves.
        # openLinks=False also stops the browser loading file: links into itself.
        self.output.setOpenLinks(False)
        self.output.setOpenExternalLinks(False)
        self.output.anchorClicked.connect(self._open_link)
        self.output.setMinimumHeight(ONE_LINE)
        self.output.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)   # on at the 60% cap
        self.output.hide()   # until there's something to show
        layout.addWidget(self.output, 1)

        self.new_chat_button = self._button("New chat", self._new_chat_clicked)
        self.stop_button = self._button("Stop", self._stop)
        self.stop_button.setObjectName("stop")
        self.stop_button.hide()
        self.copy_button = self._button("Copy", self._copy)
        self.copy_button.setEnabled(False)
        self._actions = QWidget()   # New chat / Stop / Copy, shown with the answer area
        row = QHBoxLayout(self._actions)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.new_chat_button)
        row.addStretch(1)
        row.addWidget(self.stop_button)
        row.addWidget(self.copy_button)
        self._actions.hide()
        layout.addWidget(self._actions)

        self.setStyleSheet(self.styleSheet() + STYLE)   # after the island's own style
        self._fit()

    def _button(self, text: str, slot) -> QPushButton:
        button = QPushButton(text)
        button.clicked.connect(self.mascot.hop)   # every click gets a little hop
        button.clicked.connect(slot)
        return button

    # ---------- show / hide ----------
    # The pill stays on screen; the hotkey opens and folds it. Only Explain screen
    # hides the window, so it never ends up in the screenshot.
    def toggle(self) -> None:
        if self.isVisible() and self.is_expanded:
            self._fold()
        else:
            self.summon()

    def summon(self) -> None:
        # Open on the monitor you're working on, not always the primary one.
        here = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        self.place(here)
        if self.isVisible() and not self.isActiveWindow():
            self.hide()   # a fresh show takes the keyboard, like the old panel did
        self.show_quietly(False)
        self.show()
        self._open()

    def _open(self) -> None:
        """Expand and take the keyboard. A click on the pill comes straight here: the
        click already focused the window, so there's no re-show (and no flicker).
        From the chewing pill it shows the question, "Thinking..." and Stop."""
        self._auto_folded = False
        self.expand()
        self.raise_()
        self.activateWindow()
        if self.input.isEnabled():   # not while a reply is still on its way
            self.input.setFocus()
            self.set_status("Ready", "listening")
        else:
            self.setFocus()          # Esc and the hotkey still work; no hidden chip fires
            if self.mood == "capture":   # you cancelled the region pick mid-reply
                self.set_mood("talking" if self._stream and self._stream[1] else "thinking")

    def _fold(self) -> None:
        """You folded the panel: into the chewing pill while Kami is still busy. A reply
        then waits in the pill (it hops) instead of opening the panel on you."""
        self._cancel_eat()
        self._auto_folded = False
        self.set_chewing(self._busy())
        self.collapse()

    def _busy(self) -> bool:
        return not self.input.isEnabled()   # off from _begin() to _end()

    def keyPressEvent(self, e) -> None:
        if e.key() != Qt.Key_Escape:
            return
        if self.is_expanded:
            self._fold()
        elif self._stream is not None:   # the chewing pill still has the keyboard
            self._stop()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._cancel_eat()

    def _typing(self) -> None:
        if self.input.isEnabled():
            self.set_mood("listening")

    # ---------- output ----------
    def _say(self, text: str) -> None:
        self.output.setMarkdown(text)
        bar = self.output.verticalScrollBar()
        bar.setValue(bar.maximum())
        self._has_answer = True
        self._show_answer()

    def _clear_answer(self) -> None:
        self.output.clear()
        self._has_answer = False
        self._show_answer()

    def _show_answer(self) -> None:
        """The answer area and its buttons show only when there's something in them, and
        the panel fits itself to them. Not while words are flying in: the panel keeps its
        shape until the last one is swallowed."""
        if self._bites is not None:
            return
        self.output.setVisible(self._has_answer)
        self._actions.setVisible(self._has_answer)
        self._fit()

    def _fit(self) -> None:
        """Grow or shrink the panel to the content. Called at most once per 50 ms repaint
        while a reply streams in. At the 60% cap the answer area gets its scrollbar."""
        if self._bites is not None:
            return
        self.output.updateGeometry()
        capped = self.fit()
        policy = Qt.ScrollBarAsNeeded if capped else Qt.ScrollBarAlwaysOff
        if self.output.verticalScrollBarPolicy() != policy:
            self.output.setVerticalScrollBarPolicy(policy)   # the text rewraps: measure again
            self.output.updateGeometry()
            self.fit()

    def _render_chat(self, pending: str | None = None, status: str = "",
                     reply: str | None = None) -> None:
        parts = []
        for turn in self.chat.turns:
            who = "**Kami:**" if turn.role == "assistant" else "**You:**"
            if turn.image:
                who += " _(screen capture)_"
            parts.append(who + "\n\n" + turn.text)
        if pending is not None:
            parts.append("**You:**\n\n" + pending)
        if reply is not None:
            parts.append("**Kami:**\n\n" + reply)
        if status:
            parts.append(status)
        if parts:
            self._say("\n\n".join(parts))
        else:
            self._clear_answer()   # a new chat: just the input, no empty answer box

    def _open_link(self, url: QUrl) -> None:
        if learning.is_safe_link(url.toString()):
            QDesktopServices.openUrl(url)
        else:
            log.info("blocked link with scheme %r", url.scheme()[:20])

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self._answer)
        self.copy_button.setText("Copied ✓")
        QTimer.singleShot(1500, lambda: self.copy_button.setText("Copy"))

    # ---------- request lifecycle ----------
    def _paint_stream(self) -> None:
        if self._stream is not None:
            question, pieces = self._stream
            self._render_chat(question, reply="".join(pieces) + " ▍")
            self._talk()
            self._reveal()

    def _talk(self) -> None:
        """Mascot: start talking on the first repaint, then a little nudge per repaint."""
        if self.mood != "talking":
            self.set_status("Writing...", "talking")
        else:
            self.mascot.pulse()

    def _react(self, text: str, mood: str) -> None:
        """A request ended: the panel opens again from the chewing pill to show it. If you
        folded it yourself, the pill hops instead and stays shut, unless it's an error."""
        self.set_status(text, mood)
        self._reveal(always=mood == "worried")
        if not self.is_expanded:
            self.mascot.hop()

    # ---------- the eat -> chew -> grow animation ----------
    def _words_in_input(self) -> list[tuple[str, QPointF]]:
        """Each word in the input and where it sits (in this window), for the eating
        animation: at most MAX_BITES words, then the rest as one "…". Read before the
        input is cleared. Plain strings: they're painted as text, never as markup."""
        text = self.input.text()
        metrics = self.input.fontMetrics()
        cursor = self.input.cursorRect()
        origin = cursor.center().x() - metrics.horizontalAdvance(
            text[: self.input.cursorPosition()])   # where character 0 is drawn (scrolling)
        room = self.input.contentsRect().adjusted(10, 0, -10, 0)
        y = cursor.center().y()
        spots: list[tuple[str, QPointF]] = []
        for match in re.finditer(r"\S+", text):
            last = len(spots) == MAX_BITES
            word = "…" if last else match.group()
            if len(word) > BITE_CHARS:
                word = word[: BITE_CHARS - 1] + "…"
            x = origin + metrics.horizontalAdvance(text[: match.start()])
            x += metrics.horizontalAdvance(word) / 2
            x = min(max(x, room.left()), room.right())
            spots.append((word, QPointF(self.input.mapTo(self, QPoint(round(x), y)))))
            if last:
                break
        return spots

    def _eat(self, words: list[tuple[str, QPointF]]) -> None:
        """Start a request's animation: the words fly into the wide-open mouth, then the
        panel folds into the chewing pill (_swallowed). The request itself has already
        started; this never holds it up."""
        self._cancel_eat()
        self._after_eat = "fold"
        self.setFocus()   # the input is off now: keys come here (Esc), not to a hidden chip
        if not (self.isVisible() and self.is_expanded):
            return        # nothing to watch
        self.mascot.open_mouth(True)
        self._bites = _Bites(self, words, self.input.font(), self.mascot.mouth_point,
                             self.mascot.pulse, self._swallowed)
        self.mascot.raise_()
        self.input.setPlaceholderText("")   # the words sit where the hint would show

    def _swallowed(self) -> None:
        """The last word went down: fold into the chewing pill while Kami thinks, or show
        what came back in the meantime."""
        bites, self._bites = self._bites, None
        if bites is not None:
            bites.finish()
        self.mascot.open_mouth(False)
        self.mascot.hop()   # gulp
        self._refresh_context()   # the input's hint comes back
        if self._after_eat == "fold" and self._busy() and self.is_expanded:
            self.set_chewing(True)
            self._auto_folded = True
            self.collapse(hand_back=False)   # you're waiting on Kami: keep the keyboard
        self._show_answer()

    def _cancel_eat(self) -> None:
        """Stop the eating animation now (New chat, hide, fold): no words left behind, no
        mouth left open."""
        if self._bites is None:
            return
        bites, self._bites = self._bites, None
        bites.finish()
        self.mascot.open_mouth(False)
        self._refresh_context()
        self._show_answer()

    def _reveal(self, always: bool = False) -> None:
        """The running request has something to show. Still eating? Then right after the
        last word. Folded into the chewing pill by us (or `always`)? Then open up."""
        if self._bites is not None:
            self._after_eat = "show"
            return
        if self.is_expanded or not self.isVisible():
            return
        if self._auto_folded or always:
            self._auto_folded = False
            self.expand()   # no activateWindow(): if you're typing elsewhere, it stays there

    def _begin(self) -> int:
        """Start a request: one at a time, so the input and Copy are off until it ends."""
        self._abandon()
        self._generation += 1
        self.input.setEnabled(False)
        self.copy_button.setEnabled(False)
        return self._generation

    def _current(self, generation: int) -> bool:
        return generation == self._generation

    def _abandon(self) -> None:
        """Forget the running stream; the worker closes the connection at the next piece."""
        if self._cancel is not None:
            self._cancel.set()
            self._cancel = None
        self._stream = None
        self._repaint.stop()
        self.stop_button.hide()

    def _end(self) -> None:
        self._abandon()
        self.input.setEnabled(True)
        self.input.setFocus()
        self.copy_button.setEnabled(bool(self._answer))
        self.set_chewing(False)

    def _set_chat(self, chat: Conversation) -> None:
        self.chat = chat   # the old chat and any screenshot (held or in it) are dropped here
        self._capture = None
        self._refresh_context()

    def _refresh_context(self) -> None:
        if self._capture is not None:
            self.context.setText(CONTEXT_READY)
            self.context.show()
            self.input.setPlaceholderText(PLACEHOLDER_CAPTURE)
        else:
            self.context.setText(CONTEXT_CHAT)
            self.context.setVisible(self.chat.has_image)
            self.input.setPlaceholderText(PLACEHOLDER_ASK)
        self._fit()

    def _stop(self) -> None:
        if self._stream is None:
            return
        question, pieces = self._stream
        self._generation += 1   # whatever the worker still sends is dropped
        partial = "".join(pieces)
        if partial:
            self.chat.record(question, partial + "\n\n_(stopped)_")
            self._answer = partial
        self._end()
        if partial:
            self._render_chat()
        else:
            self._render_chat(status="_(stopped)_")
            self.input.setText(question)
        self.set_status("Stopped", "idle")
        self._reveal(always=True)

    def new_chat(self) -> None:
        self._cancel_eat()
        self._auto_folded = False
        self._generation += 1   # a reply still on its way now lands nowhere
        self._set_chat(Conversation())
        self._answer = ""
        self._end()
        self._render_chat()

    def _new_chat_clicked(self) -> None:
        self.new_chat()
        self.set_status("New chat", "idle")

    # ---------- actions ----------
    def ask(self) -> None:
        question = self.input.text().strip()
        if not self.input.isEnabled():
            return
        if self._capture is not None:
            self._ask_about_capture(question)   # an empty question means "explain it"
            return
        if not question:
            return
        words = self._words_in_input()
        self.input.clear()
        generation = self._begin()
        self._eat(words)
        messages = self.chat.messages_with(question)
        # Counts only: chat text and the screenshot never reach the log.
        log.info("ask turns=%d chars=%d image=%s", len(self.chat.turns),
                 self.chat.chars + len(question), "yes" if self.chat.has_image else "no")
        self._render_chat(question, "_Thinking..._")
        self.set_status("Thinking...", "thinking")
        pieces: list[str] = []
        self._cancel = cancel = threading.Event()
        self._stream = (question, pieces)
        self.stop_button.show()

        def progress(piece: str) -> None:
            if self._current(generation):
                pieces.append(piece)
                if not self._repaint.isActive():
                    self._repaint.start()

        def done(answer: str) -> None:
            if not self._current(generation):
                return
            self.chat.record(question, answer)
            self._answer = answer
            self._end()
            self._render_chat()
            self._react("Done", "happy")

        def failed(message: str) -> None:
            if not self._current(generation):
                return
            self._end()
            partial = "".join(pieces)
            self._render_chat(question, f"**Oops:** {message}",
                              reply=partial + "\n\n_(cut off)_" if partial else None)
            self.input.setText(question)   # easy to retry with Enter
            self._react("Oops", "worried")

        run_in_background(self.client.chat_stream, messages, on_done=done, on_error=failed,
                          on_progress=progress, cancel=cancel)

    def explain_screen(self) -> None:
        self.set_status("Pick an area", "capture")
        self.hide()
        self.doodles.clear()   # old doodles would end up in the new screenshot
        QTimer.singleShot(150, self.selector.start)

    def _on_region(self, region: QRect) -> None:
        # Give the selector a moment to disappear before capturing.
        QTimer.singleShot(150, lambda: self._capture_region(region))

    def _capture_region(self, region: QRect) -> None:
        screen = QGuiApplication.screenAt(region.center()) or QGuiApplication.primaryScreen()
        local = region.translated(-screen.geometry().topLeft())
        pixmap = screen.grabWindow(0, local.x(), local.y(), local.width(), local.height())
        if not pixmap.isNull():
            # At 200% a 1000x800 box is 2000x1600 real pixels. Doodle coordinates are
            # fractions of the image, so shrinking it doesn't move them.
            w, h = scaled_size(pixmap.width(), pixmap.height(), learning.MAX_IMAGE_EDGE)
            if (w, h) != (pixmap.width(), pixmap.height()):
                pixmap = pixmap.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.WriteOnly)
        saved = not pixmap.isNull() and pixmap.save(buffer, "PNG")

        self.summon()
        if not saved or data.isEmpty():
            # Wayland gives Qt an empty pixmap; sending it would just get a 400.
            log.warning("screen capture returned an empty image")
            self._say(f"**Oops:** {capture_failed_message(self.session)}")
            self.set_status("Capture failed", "worried")
            return
        png, where = bytes(data), screen.geometry()
        self.new_chat()   # a capture starts a fresh chat; anything still running is dropped
        if os.environ.get("KAMI_DEBUG_DOODLES") == "1":
            log.info("calibration mode: drawing the test pattern, no AI call")
            self._show_lesson(png, region, where, "", learning.calibration_lesson())
            return
        # Nothing is sent yet: the user types a question first (or presses Enter).
        self._capture = (png, region, where)
        self._refresh_context()
        log.info("capture ready bytes=%d", len(png))
        self._say("_Screen captured. What do you want to know about it?_")
        self.set_status("Screen captured", "listening")
        self.input.setFocus()

    def _ask_about_capture(self, question: str) -> None:
        png, region, where = self._capture
        shown = learning.first_question(question)
        words = self._words_in_input()
        self.input.clear()
        generation = self._begin()
        self._eat(words)
        log.info("capture question chars=%d", len(question))
        self._render_chat(shown, "_Looking at your screen..._")
        self.set_status("Looking at your screen...", "thinking")

        def done(lesson: learning.Lesson) -> None:
            if self._current(generation):
                self._show_lesson(png, region, where, question, lesson)

        def failed(message: str) -> None:
            if not self._current(generation):
                return
            self._end()   # the capture is still held, so Enter tries again
            self._render_chat(shown, f"**Oops:** {message}")
            self.input.setText(question)
            self._react("Oops", "worried")

        run_in_background(learning.explain_region, self.client, png, question,
                          on_done=done, on_error=failed)

    def _show_lesson(self, png: bytes, region: QRect, where: QRect, question: str,
                     lesson: learning.Lesson) -> None:
        # Follow-ups reuse this capture, are text-only, and never redraw the doodles.
        self._set_chat(learning.follow_up_conversation(png, lesson, question))
        self._answer = lesson.explanation
        self._end()
        self._render_chat()
        self._react("Explained", "happy")
        if lesson.annotations:
            self.doodles.show_annotations(region, lesson.annotations, where)

    def meeting_notes(self) -> None:
        text = self.input.text().strip()
        if not text:
            self._say("Live capture is coming soon. For now, paste a transcript into the "
                      "box and press **Meeting notes**.")
            return
        words = self._words_in_input()
        generation = self._begin()
        self._eat(words)
        self._say("_Writing notes..._")
        self.set_status("Writing notes...", "thinking")

        def done(notes: str) -> None:
            if not self._current(generation):
                return
            self._answer = notes
            self._end()
            self._say(notes)
            self._react("Notes ready", "happy")

        run_in_background(meetings.summarize_transcript, self.client, text,
                          on_done=done, on_error=self._failed_for(generation))

    def _failed_for(self, generation: int):
        def failed(message: str) -> None:
            if self._current(generation):
                self._end()
                self._say(f"**Oops:** {message}")
                self._react("Oops", "worried")
        return failed


class _Answer(QTextBrowser):
    """The answer area. Its size hint is the height of its text, so the panel can fit
    itself to the answer as it streams in; it stays scrolled to the newest line."""

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        edge = self.contentsMargins()   # the border plus the stylesheet's padding
        width = self.width() - edge.left() - edge.right()
        if self.verticalScrollBarPolicy() != Qt.ScrollBarAlwaysOff:
            width -= self.verticalScrollBar().sizeHint().width()
        doc = self.document()
        if width > 0 and abs(doc.textWidth() - width) > 0.5:
            doc.setTextWidth(width)   # what the view will wrap to, even while it's hidden
        return QSize(hint.width(), math.ceil(doc.size().height()) + edge.top() + edge.bottom())

    def resizeEvent(self, event) -> None:
        bar = self.verticalScrollBar()
        newest = bar.value() >= bar.maximum() - 4
        super().resizeEvent(event)
        if newest:   # growing or shrinking keeps the newest line in view
            bar.setValue(bar.maximum())


class _Bites(QWidget):
    """The question's words flying into the mascot's mouth, one after another, shrinking
    and fading as they go. Painted with drawText, which never reads markup, so they stay
    plain text. Lives only for the animation: finish() stops it and deletes it."""

    def __init__(self, parent: QWidget, words: list[tuple[str, QPointF]], font: QFont,
                 mouth: Callable[[], QPointF], gulp: Callable[[], None],
                 done: Callable[[], None]) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setGeometry(parent.rect())
        self._words = words
        self._font = QFont(font)
        self._metrics = QFontMetricsF(self._font)
        self._mouth, self._gulp, self._done = mouth, gulp, done
        self._eaten = 0
        self._ms = (len(words) - 1) * STAGGER_MS + FLIGHT_MS if words else GULP_MS
        self._start = time.monotonic()
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self.show()

    def finish(self) -> None:
        self._timer.stop()
        self.hide()
        self.deleteLater()

    def _elapsed(self) -> float:
        return (time.monotonic() - self._start) * 1000

    def _tick(self) -> None:
        ms = self._elapsed()
        eaten = sum(1 for i in range(len(self._words)) if ms >= i * STAGGER_MS + FLIGHT_MS)
        while self._eaten < eaten:   # a little gulp per word
            self._eaten += 1
            self._gulp()
        if ms >= self._ms:
            self._timer.stop()
            self._done()
            return
        self.update()

    def paintEvent(self, _event) -> None:
        ms = self._elapsed()
        mouth = self._mouth()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setFont(self._font)
        ink = QColor("#FFF4DC")
        for i, (word, start) in enumerate(self._words):
            t = min(max((ms - i * STAGGER_MS) / FLIGHT_MS, 0.0), 1.0)
            if t >= 1.0:
                continue
            e = t * t   # slow, then sucked in
            lift = QPointF((start.x() + mouth.x()) / 2, min(start.y(), mouth.y()) - 36)
            pos = start * (1 - e) ** 2 + lift * (2 * (1 - e) * e) + mouth * (e * e)
            ink.setAlphaF(1.0 - min(max((t - 0.7) / 0.3, 0.0), 1.0))
            p.save()
            p.translate(pos)
            p.scale(1 - 0.75 * e, 1 - 0.75 * e)
            p.rotate(-25 * e)
            p.setPen(ink)
            width = self._metrics.horizontalAdvance(word)
            p.drawText(QPointF(-width / 2, (self._metrics.ascent() - self._metrics.descent()) / 2),
                       word)
            p.restore()
