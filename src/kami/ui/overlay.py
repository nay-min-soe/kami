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
QTextBrowser { background: #2A2640; color: #FFF4DC; border: none;
               border-radius: 10px; padding: 8px; font-size: 14px; }
QPushButton { background: #FFC93C; color: #1E1B2E; border: none; border-radius: 10px;
              padding: 8px 12px; font-weight: 700; }
QPushButton:hover { background: #FF6B9A; }
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

        self._answer = ""  # Markdown source of the last real answer, never status/errors
        self.copy_button = QPushButton("Copy")
        self.copy_button.setEnabled(False)
        self.copy_button.clicked.connect(self._copy)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.copy_button)
        layout.addLayout(row)

        self.setStyleSheet(STYLE)
        self.resize(520, 420)

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

    # ---------- actions ----------
    def _say(self, text: str) -> None:
        self.output.setMarkdown(text)

    def _busy(self, status: str) -> None:
        self._say(status)
        self.copy_button.setEnabled(False)

    def _show_answer(self, text: str) -> None:
        self._answer = text
        self._say(text)
        self._refresh_copy()

    def _error(self, message: str) -> None:
        self._say(f"**Oops:** {message}")
        self._refresh_copy()

    def _refresh_copy(self) -> None:
        self.copy_button.setEnabled(bool(self._answer))

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self._answer)
        self.copy_button.setText("Copied ✓")
        QTimer.singleShot(1500, lambda: self.copy_button.setText("Copy"))

    def _open_link(self, url: QUrl) -> None:
        if learning.is_safe_link(url.toString()):
            QDesktopServices.openUrl(url)
        else:
            log.info("blocked link with scheme %r", url.scheme()[:20])

    def ask(self) -> None:
        prompt = self.input.text().strip()
        if not prompt:
            return
        self._busy("_Thinking..._")
        run_in_background(self.client.ask, prompt, on_done=self._show_answer,
                          on_error=self._error)

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
            self._error(CAPTURE_FAILED)
            return
        self._busy("_Looking at your screen..._")

        def done(lesson: learning.Lesson) -> None:
            if lesson.explanation:
                self._show_answer(lesson.explanation)
            else:
                self._say("_No explanation returned._")
                self._refresh_copy()
            if lesson.annotations:
                self.doodles.show_annotations(region, lesson.annotations)

        run_in_background(learning.explain_region, self.client, bytes(data),
                          on_done=done, on_error=self._error)

    def meeting_notes(self) -> None:
        text = self.input.text().strip()
        if not text:
            self._say("Live capture is coming soon. For now, paste a transcript into the "
                      "box and press **Meeting notes**.")
            return
        self._busy("_Writing notes..._")
        run_in_background(meetings.summarize_transcript, self.client, text,
                          on_done=self._show_answer, on_error=self._error)
