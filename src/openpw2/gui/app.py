"""Application entry point; starts disconnected unless --demo was requested."""

import argparse
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from openpw2 import __version__

from .window import Window


def main():
    parser = argparse.ArgumentParser(description="openpw2 · independent IC-PW2 LAN remote")
    parser.add_argument("--demo", action="store_true", help="Use the local simulator, no hardware")
    parser.add_argument("--version", action="version", version=f"openpw2 {__version__}")
    parser.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("openpw2")
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")
    window = Window(demo=args.demo or args.smoke_test)
    window.show()
    if args.smoke_test:
        QTimer.singleShot(2200, window.close)
    raise SystemExit(app.exec())
