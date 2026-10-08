"""The panel that pops up on the hotkey."""
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
    QVBoxLayout,
    QWidget,
)

from kami.config import Config
from kami.conversation import Conversation
from kami.geometry import scaled_size
from kami.llm import LLMClient
from kami.modes import learning, meetings
from kami.ui.annotation import AnnotationLayer
from kami.ui.region_select import RegionSelector
from kami.ui.worker import run_in_background

log = logging.getLogger(__name__)

CAPTURE_FAILED = (
    "Kami couldn't capture your screen. On Wayland, screen capture isn't supported yet: "
    'log in with "Ubuntu on Xorg" (or "GNOME on Xorg") to use Explain screen.'
)

STYLE = """
#panel { background: #1E1B2E; border: 3px solid #FF6B9A; border-radius: 18px; }
QLabel#title { color: #FFC93C; font-size: 22px; font-weight: 800; }
QLabel#context { color: #FFC93C; font-size: 12px; }
QLineEdit { background: #2A2640; color: #FFF4DC; border: 2px solid #4A4560;
            border-radius: 10px; padding: 8px; font-size: 15px; }
QLineEdit:disabled { color: #8A85A0; }
QTextBrowser { background: #2A2640; color: #FFF4DC; border: none;
               border-radius: 10px; padding: 8px; font-size: 14px; }
QPushButton { background: #FFC93C; color: #1E1B2E; border: none; border-radius: 10px;
              padding: 8px 12px; font-weight: 700; }
QPushButton:hover { background: #FF6B9A; }
QPushButton:disabled { background: #4A4560; color: #8A85A0; }
"""


class KamiOverlay(QWidget):
    def __init__(self, config: Config) -> None:
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.config = config
        self.client = LLMClient(config.llm)
        self.selector = RegionSelector()
        self.selector.selected.connect(self._on_region)
        self.selector.cancelled.connect(self.summon)
        self.doodles = AnnotationLayer()
        self.chat = Conversation()
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
        panel = QWidget()
        panel.setObjectName("panel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(panel)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 14, 16, 16)
        title = QLabel("Kami")
        title.setObjectName("title")
        layout.addWidget(title)

        buttons = QHBoxLayout()
        for text, slot in (
            ("Explain screen", self.explain_screen),
            ("Meeting notes", self.meeting_notes),
            ("Clear doodles", self.doodles.clear),
        ):
            button = QPushButton(text)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        layout.addLayout(buttons)

        self.context = QLabel("📷 Asking about your screen capture · New chat to stop")
        self.context.setObjectName("context")
        self.context.hide()
        layout.addWidget(self.context)

        self.input = QLineEdit()
        self.input.setPlaceholderText("Ask anything, then press Enter")
        self.input.returnPressed.connect(self.ask)
        layout.addWidget(self.input)

        self.output = QTextBrowser()
        # Answers can repeat links from a screenshot, so we vet every click ourselves.
        # openLinks=False also stops the browser loading file: links into itself.
        self.output.setOpenLinks(False)
        self.output.setOpenExternalLinks(False)
        self.output.anchorClicked.connect(self._open_link)
        layout.addWidget(self.output, 1)

        self.new_chat_button = QPushButton("New chat")
        self.new_chat_button.clicked.connect(self.new_chat)
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self._stop)
        self.stop_button.hide()
        self.copy_button = QPushButton("Copy")
        self.copy_button.setEnabled(False)
        self.copy_button.clicked.connect(self._copy)
        row = QHBoxLayout()
        row.addWidget(self.new_chat_button)
        row.addStretch(1)
        row.addWidget(self.stop_button)
        row.addWidget(self.copy_button)
        layout.addLayout(row)

        self.setStyleSheet(STYLE)
        self.resize(520, 460)

    # ---------- show / hide ----------
    def toggle(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            self.summon()

    def summon(self) -> None:
        # Open on the monitor you're working on, not always the primary one.
        here = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        screen = here.availableGeometry()
        self.move(screen.right() - self.width() - 24, screen.top() + 48)
        self.show()
        self.raise_()
        self.activateWindow()
        self.input.setFocus()

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_Escape:
            self.hide()

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
        self.chat = chat   # the old chat (and any screenshot in it) is dropped here
        self.context.setVisible(chat.has_image)

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

    def new_chat(self) -> None:
        self._generation += 1   # a reply still on its way now lands nowhere
        self._set_chat(Conversation())
        self._answer = ""
        self._end()
        self._render_chat()

    # ---------- actions ----------
    def ask(self) -> None:
        question = self.input.text().strip()
        if not question or not self.input.isEnabled():
            return
        self.input.clear()
        generation = self._begin()
        messages = self.chat.messages_with(question)
        # Counts only: chat text and the screenshot never reach the log.
        log.info("ask turns=%d chars=%d image=%s", len(self.chat.turns),
                 self.chat.chars + len(question), "yes" if self.chat.has_image else "no")
        self._render_chat(question, "_Thinking..._")
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

        def failed(message: str) -> None:
            if not self._current(generation):
                return
            self._end()
            partial = "".join(pieces)
            self._render_chat(question, f"**Oops:** {message}",
                              reply=partial + "\n\n_(cut off)_" if partial else None)
            self.input.setText(question)   # easy to retry with Enter

        run_in_background(self.client.chat_stream, messages, on_done=done, on_error=failed,
                          on_progress=progress, cancel=cancel)

    def explain_screen(self) -> None:
        self.hide()
        QTimer.singleShot(150, self.selector.start)

    def _on_region(self, region: QRect) -> None:
        # Give the selector a moment to disappear before capturing.
        QTimer.singleShot(150, lambda: self._capture_and_explain(region))

    def _capture_and_explain(self, region: QRect) -> None:
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
            self._say(f"**Oops:** {CAPTURE_FAILED}")
            return
        generation = self._begin()
        self._say("_Looking at your screen..._")

        png = bytes(data)

        def done(lesson: learning.Lesson) -> None:
            if not self._current(generation):
                return
            # Follow-ups reuse this capture, are text-only, and never redraw the doodles.
            self._set_chat(learning.follow_up_conversation(png, lesson))
            self._answer = lesson.explanation
            self._end()
            self._render_chat()
            if lesson.annotations:
                self.doodles.show_annotations(region, lesson.annotations, screen.geometry())

        if os.environ.get("KAMI_DEBUG_DOODLES") == "1":
            log.info("calibration mode: drawing the test pattern, no AI call")
            done(learning.calibration_lesson())
            return
        run_in_background(learning.explain_region, self.client, png,
                          on_done=done, on_error=self._failed_for(generation))

    def meeting_notes(self) -> None:
        text = self.input.text().strip()
        if not text:
            self._say("Live capture is coming soon. For now, paste a transcript into the "
                      "box and press **Meeting notes**.")
            return
        generation = self._begin()
        self._say("_Writing notes..._")

        def done(notes: str) -> None:
            if not self._current(generation):
                return
            self._answer = notes
            self._end()
            self._say(notes)

        run_in_background(meetings.summarize_transcript, self.client, text,
                          on_done=done, on_error=self._failed_for(generation))

    def _failed_for(self, generation: int):
        def failed(message: str) -> None:
            if self._current(generation):
                self._end()
                self._say(f"**Oops:** {message}")
        return failed
