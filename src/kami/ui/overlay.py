"""The panel that pops up on the hotkey."""
from __future__ import annotations

import logging

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRect, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
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
        self.copy_button = QPushButton("Copy")
        self.copy_button.setEnabled(False)
        self.copy_button.clicked.connect(self._copy)
        row = QHBoxLayout()
        row.addWidget(self.new_chat_button)
        row.addStretch(1)
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
        screen = QGuiApplication.primaryScreen().availableGeometry()
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

    def _render_chat(self, pending: str | None = None, status: str = "") -> None:
        parts = []
        for turn in self.chat.turns:
            parts.append(("**You:**" if turn.role == "user" else "**Kami:**") + "\n\n" + turn.text)
        if pending is not None:
            parts.append("**You:**\n\n" + pending)
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
    def _begin(self) -> int:
        """Start a request: one at a time, so the input and Copy are off until it ends."""
        self._generation += 1
        self.input.setEnabled(False)
        self.copy_button.setEnabled(False)
        return self._generation

    def _current(self, generation: int) -> bool:
        return generation == self._generation

    def _end(self) -> None:
        self.input.setEnabled(True)
        self.input.setFocus()
        self.copy_button.setEnabled(bool(self._answer))

    def new_chat(self) -> None:
        self._generation += 1   # a reply still on its way now lands nowhere
        self.chat.clear()
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
        log.info("ask turns=%d chars=%d", len(self.chat.turns), self.chat.chars + len(question))
        self._render_chat(question, "_Thinking..._")

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
            self._render_chat(question, f"**Oops:** {message}")
            self.input.setText(question)   # easy to retry with Enter

        run_in_background(self.client.chat, messages, on_done=done, on_error=failed)

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

        def done(lesson: learning.Lesson) -> None:
            if not self._current(generation):
                return
            if lesson.explanation:
                self._answer = lesson.explanation
            self._end()
            self._say(lesson.explanation or "_No explanation returned._")
            if lesson.annotations:
                self.doodles.show_annotations(region, lesson.annotations)

        run_in_background(learning.explain_region, self.client, bytes(data),
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
