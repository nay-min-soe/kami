"""Kami's panel inside the notch: Ask, Explain screen, Meeting notes.

The notch shell (pill, expand/collapse, status card, chips) is `ui/island.py`; this
file fills it and runs the requests. The mascot's mood follows each request.
"""
from __future__ import annotations

import logging
import os
import threading

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRect, Qt, QTimer, QUrl
from PySide6.QtGui import QCursor, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextBrowser,
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
QPushButton { background: #2A2640; color: #FFF4DC; border: none; border-radius: 12px;
              padding: 7px 14px; font-weight: 700; }
QPushButton:hover { background: #4A4560; }
QPushButton:disabled { background: #1E1B2E; color: #4A4560; }
QPushButton#stop { background: #FF6B9A; color: #1E1B2E; }
"""

# Chip colours; the pill's four dots use them too.
CHIP_PINK, CHIP_YELLOW, CHIP_MUTED, CHIP_CREAM = "#FF6B9A", "#FFC93C", "#8A85A0", "#FFF4DC"


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

        self.output = QTextBrowser()
        # Answers can repeat links from a screenshot, so we vet every click ourselves.
        # openLinks=False also stops the browser loading file: links into itself.
        self.output.setOpenLinks(False)
        self.output.setOpenExternalLinks(False)
        self.output.anchorClicked.connect(self._open_link)
        layout.addWidget(self.output, 1)

        self.new_chat_button = self._button("New chat", self._new_chat_clicked)
        self.stop_button = self._button("Stop", self._stop)
        self.stop_button.setObjectName("stop")
        self.stop_button.hide()
        self.copy_button = self._button("Copy", self._copy)
        self.copy_button.setEnabled(False)
        row = QHBoxLayout()
        row.addWidget(self.new_chat_button)
        row.addStretch(1)
        row.addWidget(self.stop_button)
        row.addWidget(self.copy_button)
        layout.addLayout(row)

        self.setStyleSheet(self.styleSheet() + STYLE)   # after the island's own style

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
            self.collapse()
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
        click already focused the window, so there's no re-show (and no flicker)."""
        self.expand()
        self.raise_()
        self.activateWindow()
        self.input.setFocus()
        if self.input.isEnabled():   # not while a reply is still on its way
            self.set_status("Ready", "listening")

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_Escape:
            self.collapse()

    def _typing(self) -> None:
        if self.input.isEnabled():
            self.set_mood("listening")

    # ---------- output ----------
    def _say(self, text: str) -> None:
        self.output.setMarkdown(text)
        bar = self.output.verticalScrollBar()
        bar.setValue(bar.maximum())

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
        self._say("\n\n".join(parts) or "_New chat. Ask anything._")

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

    def _talk(self) -> None:
        """Mascot: start talking on the first repaint, then a little nudge per repaint."""
        if self.mood != "talking":
            self.set_status("Writing...", "talking")
        else:
            self.mascot.pulse()

    def _react(self, text: str, mood: str) -> None:
        """A request ended. Folded into the pill? Then the pill hops too, but stays shut."""
        self.set_status(text, mood)
        if not self.is_expanded:
            self.mascot.hop()

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

    def new_chat(self) -> None:
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
        self.input.clear()
        generation = self._begin()
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
        self.input.clear()
        generation = self._begin()
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
        generation = self._begin()
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
