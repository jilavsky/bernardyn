import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Exit status recorded at session end, used by pytest_unconfigure below.
_EXIT_STATUS = 0


@pytest.fixture(scope="session")
def qapp():
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        pytest.skip("PySide6 is not installed")
    app = QApplication.instance() or QApplication([])
    yield app
    app.processEvents()


def pytest_sessionfinish(session, exitstatus):
    global _EXIT_STATUS
    _EXIT_STATUS = int(exitstatus)


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config):
    """End the test process before Python's teardown destroys Qt objects.

    After every test has passed, CPython's finalisation can destroy PySide6
    and pyqtgraph objects in an order Qt does not expect.  On CI runners this
    intermittently crashed the process (segmentation fault, or "Fatal Python
    error: bool_dealloc") and turned a green run red.  Leaving with
    ``os._exit`` skips that finalisation and keeps pytest's own exit status;
    it runs last, after other plugins have written their reports.  Forcing
    widget deletion first is not safe (Python still holds references), so
    nothing is deleted.  Set BERNARDYN_TEST_NORMAL_EXIT=1 for the normal
    interpreter shutdown, e.g. when investigating such a crash.

    Not used on Windows: the crash was never seen there, and on the Windows
    runners this early exit itself ended passing runs with status 1 (cause
    not identified), so Windows keeps the normal shutdown.
    """
    if (
        sys.platform == "win32"
        or os.environ.get("BERNARDYN_TEST_NORMAL_EXIT")
        or "PySide6.QtWidgets" not in sys.modules
    ):
        return
    print(f"conftest: ending the test process with status {_EXIT_STATUS}", file=sys.stderr)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_EXIT_STATUS)
