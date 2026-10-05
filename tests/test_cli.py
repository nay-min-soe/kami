import os
import subprocess
import sys
from pathlib import Path

import pytest

from kami import __version__
from kami.cli import main

SRC = Path(__file__).resolve().parent.parent / "src"


def test_version_prints_and_exits_without_qt():
    # A fresh interpreter, so earlier imports in this test run can't hide a Qt import.
    code = ("import sys\nfrom kami.cli import main\n"
            "try:\n    main(['--version'])\nexcept SystemExit:\n    pass\n"
            "print('qt loaded' if 'PySide6.QtWidgets' in sys.modules else 'no qt')")
    env = {**os.environ, "PYTHONPATH": str(SRC)}
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env=env, timeout=30).stdout
    assert f"kami {__version__}" in out
    assert "no qt" in out


def test_unknown_command_errors(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["frobnicate"])
    assert exit_info.value.code == 2
    assert "usage: kami" in capsys.readouterr().err
