"""Small reusable widgets shared by the dialogs and the inspector."""

from __future__ import annotations

import math
import re

from bernardyn.gui._qt import QDoubleSpinBox, QValidator

__all__ = ["ScientificSpinBox", "color_swatch_qss", "format_scientific"]

# Anything that can still become a number while the user types: "", "-",
# "1.", "1e", "1e-", ".5" ...
_PARTIAL_NUMBER = re.compile(r"^\s*[+-]?(\d+[.,]?\d*|[.,]\d*)?([eE][+-]?\d*)?\s*$")


def color_swatch_qss(rgba) -> str:
    """Stylesheet for a "Choose…" colour-swatch button showing ``rgba``.

    The label text is black or white, whichever contrasts with the swatch;
    with a fixed dark text a black swatch made the label unreadable.  A
    translucent colour is judged as drawn over white.
    """
    red, green, blue, alpha = (int(channel) for channel in rgba)
    opacity = alpha / 255
    over_white = [opacity * channel + (1 - opacity) * 255 for channel in (red, green, blue)]
    # ITU-R BT.601 luma; good enough to pick between black and white text.
    luma = 0.299 * over_white[0] + 0.587 * over_white[1] + 0.114 * over_white[2]
    text = "black" if luma >= 140 else "white"
    return f"background: rgba({red}, {green}, {blue}, {alpha}); color: {text}"


def format_scientific(value: float) -> str:
    """Shortest text that reads back as exactly ``value``.

    ``3.2e-10`` stays ``3.2e-10`` and ``1.5e12`` becomes ``1500000000000``;
    a whole number loses its trailing ``.0``.
    """
    text = repr(float(value))
    if "e" not in text and "inf" not in text and "nan" not in text and text.endswith(".0"):
        text = text[:-2]
    return text


def _parse(text: str) -> float | None:
    stripped = text.strip()
    if "," in stripped and "." not in stripped:
        # Decimal comma, as typed in many locales.
        stripped = stripped.replace(",", ".")
    try:
        value = float(stripped)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


class ScientificSpinBox(QDoubleSpinBox):
    """A double spin box that keeps full float precision.

    ``QDoubleSpinBox`` rounds every value to its fixed number of decimals, so
    with 8 decimals 3.2e-10 became 0.0, and Porod, Kratky or Zimm values,
    annotation positions on those axes, and tiny multipliers could not be
    entered.  This box shows and accepts plain or exponent notation
    (``3.2e-10``, ``1.5E12``) and stores the value unrounded.  The arrows
    step by one tenth of the value's decade (1 → 1.1, 3.2e-10 → 3.3e-10).
    """

    def __init__(self, parent=None, *, minimum: float = -1e300, maximum: float = 1e300) -> None:
        super().__init__(parent)
        # Qt caps decimals at what a double can hold; at that setting its
        # internal rounding no longer changes any value.
        self.setDecimals(1000)
        self.setRange(minimum, maximum)
        self.setKeyboardTracking(False)

    def textFromValue(self, value: float) -> str:  # noqa: N802 - Qt API
        return format_scientific(value)

    def valueFromText(self, text: str) -> float:  # noqa: N802 - Qt API
        value = _parse(text)
        return self.value() if value is None else value

    def validate(self, text: str, position: int):
        value = _parse(text)
        if value is not None:
            if self.minimum() <= value <= self.maximum():
                return QValidator.State.Acceptable, text, position
            return QValidator.State.Intermediate, text, position
        if _PARTIAL_NUMBER.match(text):
            return QValidator.State.Intermediate, text, position
        return QValidator.State.Invalid, text, position

    def fixup(self, text: str) -> str:
        return format_scientific(self.value())

    def stepBy(self, steps: int) -> None:  # noqa: N802 - Qt API
        value = self.value()
        if value == 0:
            step = 0.1
        else:
            step = 10.0 ** (math.floor(math.log10(abs(value))) - 1)
        self.setValue(min(self.maximum(), max(self.minimum(), value + steps * step)))
