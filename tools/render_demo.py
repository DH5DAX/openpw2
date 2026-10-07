"""Render the actual Qt widgets offscreen, without a desktop or any hardware."""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

from openpw2.gui.window import Window

app = QApplication([])
app.setStyle("Fusion")
# Qt's Windows offscreen plugin does not discover the system font database.
# Use installed fonts for rendering only; no Microsoft fonts are redistributed.
for filename in ("segoeui.ttf", "segoeuib.ttf", "consola.ttf"):
    font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / filename
    if font.exists():
        QFontDatabase.addApplicationFont(str(font))
window = Window(demo=True)
window.show()
QTimer.singleShot(200, lambda: window.bridge.command("operate", value=True))
QTimer.singleShot(500, lambda: window.demo_tx.setChecked(True))


def capture():
    destination = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/images/demo.png")
    destination.parent.mkdir(parents=True, exist_ok=True)
    assert window.grab().save(str(destination))
    window.close()


QTimer.singleShot(1100, capture)
app.exec()
