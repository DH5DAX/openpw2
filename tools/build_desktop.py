"""Portable folder build, with visible dependencies and their notices."""

import importlib.metadata
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    env = os.environ.copy()
    if sys.platform == "win32":
        # DLL discovery must not harvest same-named libraries from unrelated
        # tools on PATH (e.g. Poppler ICU instead of the Windows ICU API).
        windows = Path(os.environ["SystemRoot"])
        env["PATH"] = os.pathsep.join(
            map(
                str,
                (
                    windows / "System32",
                    windows,
                    Path(sys.executable).parent,
                    Path(sys.base_prefix),
                ),
            )
        )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--windowed",
            "--onedir",
            "--name",
            "openpw2",
            "--paths",
            str(ROOT / "src"),
            "--collect-data",
            "openpw2",
            "--specpath",
            str(ROOT / "build"),
            "--distpath",
            str(ROOT / "dist"),
            "--workpath",
            str(ROOT / "build/pyinstaller"),
            str(ROOT / "tools/desktop_entry.py"),
        ],
        cwd=ROOT,
        env=env,
        check=True,
    )
    output = ROOT / "dist/openpw2"
    for name in ("LICENSE", "THIRD_PARTY.md", "README.md", "CONTRIBUTING.md"):
        shutil.copyfile(ROOT / name, output / name)
    shutil.copytree(ROOT / "docs", output / "docs", dirs_exist_ok=True)
    notices = output / "licenses"
    notices.mkdir(exist_ok=True)
    # License files as shipped by each installed runtime distribution.
    versions = []
    for name in (
        "PySide6",
        "PySide6_Essentials",
        "PySide6_Addons",
        "shiboken6",
        "cryptography",
        "cffi",
        "pycparser",
        "pyinstaller",
    ):
        dist = importlib.metadata.distribution(name)
        versions.append(f"{name}=={dist.version}")
        for item in dist.files or []:
            if any(term in item.name.lower() for term in ("license", "copying", "notice")):
                source = Path(dist.locate_file(item))
                if source.is_file() and source.suffix.lower() not in (".py", ".pyc", ".pyd", ".dll"):
                    destination = (notices / name / str(item)).resolve()
                    if not destination.is_relative_to(notices.resolve()):
                        raise ValueError(f"Unsafe license path in {name}: {item}")
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, destination)
    for source in (ROOT / "licenses").glob("*.txt"):
        shutil.copyfile(source, notices / source.name)
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.exists():
        shutil.copyfile(python_license, notices / "Python-LICENSE.txt")
    (output / "DEPENDENCIES.txt").write_text(
        "Python " + sys.version + "\n" + "\n".join(versions) + "\n", encoding="utf-8"
    )
    print(f"Portable app: {output}")


if __name__ == "__main__":
    main()
