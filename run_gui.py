#!/usr/bin/env python
"""Script para executar a interface gráfica do SonyDateDV Converter."""

import os
import sys
from pathlib import Path

from gui import main_gui


def configure_bundled_tools():
    if getattr(sys, "frozen", False):
        tools_dir = Path(__file__).resolve().parent / "bin"
        os.environ["PATH"] = str(tools_dir) + os.pathsep + os.environ.get("PATH", "")


if __name__ == "__main__":
    configure_bundled_tools()
    main_gui()
