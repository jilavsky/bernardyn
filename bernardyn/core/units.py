"""Display formatting and comparison of the unit strings carried by curves.

Units stay stored exactly as the producer wrote them (``1/angstrom``,
``1/cm``, ``cm2/cm3``, ...).  This module only turns them into axis-label
text and decides whether two spellings describe the same quantity, so that a
graph can warn before it overlays incompatible curves on one axis.

Strings that cannot be parsed are shown unchanged and compared literally;
they are never guessed at.
"""

from __future__ import annotations

import re
from fractions import Fraction

# Canonical display symbol for each recognised base-unit spelling.
_BASE_UNITS = {
    "a": "Å",
    "å": "Å",
    "ang": "Å",
    "angstrom": "Å",
    "angstroms": "Å",
    "nm": "nm",
    "pm": "pm",
    "um": "µm",
    "µm": "µm",
    "mm": "mm",
    "cm": "cm",
    "m": "m",
    "sr": "sr",
    # Dimensionless, but kept visible because it states the quantity.
    "volume_fraction": "vol. fraction",
}
# Arbitrary/relative intensity scales.  Treated as one opaque "unit" so that
# arb data are never reported as compatible with absolute intensity.
_ARBITRARY = {"arb", "arb.", "arb. units", "arb.units", "a.u.", "au", "arbitrary", "counts"}
_ARBITRARY_SYMBOL = "arb. units"
_DIMENSIONLESS = {"", "1", "dimensionless", "none", "unitless"}

_SUPERSCRIPT_DIGITS = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")
_FROM_SUPERSCRIPT = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789-")

UnitPowers = dict[str, Fraction]


def _split_top_level(text: str, separator: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    current = ""
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == separator and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += char
    parts.append(current)
    return parts


def _combine(left: UnitPowers, right: UnitPowers, sign: int = 1) -> UnitPowers:
    result = dict(left)
    for symbol, power in right.items():
        result[symbol] = result.get(symbol, Fraction(0)) + sign * power
    return {symbol: power for symbol, power in result.items() if power != 0}


def _scaled(powers: UnitPowers, factor: Fraction) -> UnitPowers:
    return {symbol: power * factor for symbol, power in powers.items()}


def parse_unit(unit: str | None) -> UnitPowers | None:
    """Return ``{symbol: exponent}`` for a unit string, or None if unrecognised.

    Handles products (``·``, ``*``), division (``/``), parentheses, ``√``,
    and integer exponents written as ``^n``, trailing digits (``cm2``), or
    Unicode superscripts (``²``).  An empty mapping means dimensionless.
    """
    text = "" if unit is None else str(unit).strip()
    # Some NXcanSAS writers store a bracketed unit ("[cm2/cm3]"), which view
    # units then embed ("[cm2/cm3]·(1/angstrom)²").  Read brackets as parentheses.
    text = text.replace("[", "(").replace("]", ")")
    if text.lower() in _DIMENSIONLESS:
        return {}
    if text.lower() in _ARBITRARY:
        return {_ARBITRARY_SYMBOL: Fraction(1)}
    try:
        return _parse(text)
    except (ValueError, ZeroDivisionError):
        return None


def _parse(text: str) -> UnitPowers:
    # Spaces around operators are layout, not multiplication: "1 / cm".
    text = re.sub(r"\s*([/·*^()])\s*", r"\1", text.strip())
    if not text:
        raise ValueError("empty unit factor")
    factors = _split_top_level(text.replace("*", "·"), "·")
    if len(factors) == 1 and text.lower() not in _ARBITRARY:
        # A space also multiplies, as in pyIrena's "1/(cm^3 angstrom)".
        factors = [factor for factor in _split_top_level(text, " ") if factor]
    if len(factors) > 1:
        result: UnitPowers = {}
        for factor in factors:
            if factor:
                result = _combine(result, _parse(factor))
        return result
    divided = _split_top_level(text, "/")
    if len(divided) > 1:
        numerator = divided[0].strip()
        result = {} if numerator in {"", "1"} else _parse(numerator)
        for denominator in divided[1:]:
            result = _combine(result, _parse(denominator), sign=-1)
        return result
    return _parse_power(text)


def _parse_power(text: str) -> UnitPowers:
    if text.startswith("√"):
        return _scaled(_parse_power(text[1:]), Fraction(1, 2))
    match = re.fullmatch(r"(.+?)(?:\^\(?(-?\d+)\)?|([⁻]?[⁰¹²³⁴⁵⁶⁷⁸⁹]+))", text)
    if match is not None and (match.group(2) or match.group(3)):
        exponent = int(match.group(2) or match.group(3).translate(_FROM_SUPERSCRIPT))
        return _scaled(_parse_power(match.group(1)), Fraction(exponent))
    if text.startswith("(") and text.endswith(")"):
        return _parse(text[1:-1])
    lowered = text.lower()
    if lowered in _DIMENSIONLESS:
        return {}
    if lowered in _ARBITRARY:
        return {_ARBITRARY_SYMBOL: Fraction(1)}
    if lowered in _BASE_UNITS:
        return {_BASE_UNITS[lowered]: Fraction(1)}
    trailing = re.fullmatch(r"([a-zµå]+)(-?\d+)", lowered)
    if trailing is not None and trailing.group(1) in _BASE_UNITS:
        return {_BASE_UNITS[trailing.group(1)]: Fraction(int(trailing.group(2)))}
    raise ValueError(f"unrecognised unit {text!r}")


def _format_power(symbol: str, power: Fraction) -> str:
    base = f"({symbol})" if " " in symbol and power != 1 else symbol
    if power == 1:
        return base
    if power.denominator == 1:
        return base + str(power.numerator).translate(_SUPERSCRIPT_DIGITS)
    return f"{base}^({power.numerator}/{power.denominator})"


def format_unit(unit: str | None) -> str:
    """Return a compact display form, e.g. ``(1/angstrom)²`` → ``Å⁻²``.

    Dimensionless quantities return an empty string.  Unrecognised strings are
    returned unchanged rather than reinterpreted.
    """
    powers = parse_unit(unit)
    if powers is None:
        return str(unit).strip()
    # Positive powers first reads naturally: "cm⁻¹·Å⁻²", "arb. units·Å⁻²".
    ordered = sorted(powers.items(), key=lambda item: item[1] < 0)
    return "·".join(_format_power(symbol, power) for symbol, power in ordered)


def axis_label(quantity: str, unit: str | None) -> str:
    """Return ``"quantity [unit]"``, or just the quantity when dimensionless."""
    shown = format_unit(unit)
    return f"{quantity} [{shown}]" if shown else quantity


def units_equivalent(first: str | None, second: str | None) -> bool:
    """Whether two unit strings describe the same unit (no conversion factors).

    ``1/A`` and ``1/angstrom``, or ``cm2/cm3`` and ``1/cm``, are equivalent.
    ``1/nm`` and ``1/angstrom`` are not: they need a numeric conversion.
    """
    left, right = parse_unit(first), parse_unit(second)
    if left is None or right is None:
        return str(first or "").strip().lower() == str(second or "").strip().lower()
    return left == right
