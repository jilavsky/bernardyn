import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        pytest.skip("PySide6 is not installed")
    app = QApplication.instance() or QApplication([])
    yield app
    app.processEvents()
