# Third-party software and provenance

openpw2's independently written Python code and documentation use the MIT
license in `LICENSE`. It uses these separately licensed dependencies:

- **PySide6 / Shiboken / Qt**: the open-source distribution offers LGPL/GPL
  license choices. This application uses QtCore, QtGui and QtWidgets through
  dynamically loaded libraries; they retain their own licenses, not MIT.
  [Qt for Python licenses](https://doc.qt.io/qtforpython-6/licenses.html),
  [source](https://code.qt.io/pyside/pyside-setup.git/).
- **cryptography**: Apache-2.0 OR BSD-3-Clause; its binary distributions also
  include their own dependency notices. [Source](https://github.com/pyca/cryptography).
- **CPython** and supporting runtime components retain their own licenses.
- **PyInstaller** packages the optional desktop build under its bootloader
  exception; its license does not change the application's MIT license.

The portable build keeps dynamic libraries in `_internal`, includes the
installed distributions' license files plus LGPL-3.0/GPL-3.0 texts, and records
versions in `DEPENDENCIES.txt`. Source/editable installs leave dependencies as
ordinary replaceable Python packages. Retain dependency notices when packaging
or redistributing your own build.

The LAN encoder/decoder derives from independently written HamRig PW2
interoperability work by the same project author, based on local RS-PW2 1.0.4
analysis and operator-controlled hardware captures. No Icom code, DLL, artwork,
manual, password, challenge capture or encrypted login is bundled. The selected
status fixtures contain display bytes only. Icom and IC-PW2 are their owners'
names; openpw2 is not affiliated with or endorsed by Icom.
