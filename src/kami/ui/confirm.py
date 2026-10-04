"""The confirmation dialog for sensitive actions."""
from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from kami.safety import ProposedAction


def confirm_dialog(action: ProposedAction, parent=None) -> bool:
    risks = "\n".join(f"• {r}" for r in action.risks)
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Warning)
    box.setWindowTitle("Kami wants to do something")
    box.setText(f"<b>In {action.app}:</b> {action.description}")
    box.setInformativeText(f"What could happen:\n{risks}\n\nAllow it?")
    allow = box.addButton("Do it", QMessageBox.AcceptRole)
    nope = box.addButton("Nope", QMessageBox.RejectRole)
    box.setDefaultButton(nope)  # safe default: Enter means no
    box.exec()
    return box.clickedButton() is allow
