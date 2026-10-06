"""Key specs ("super+shift+b") and text to QEMU qcodes."""

from __future__ import annotations

MODIFIERS = {
    "super": "meta_l",
    "meta": "meta_l",
    "ctrl": "ctrl",
    "control": "ctrl",
    "shift": "shift",
    "alt": "alt",
}

NAMED = {
    "enter": "ret",
    "return": "ret",
    "ret": "ret",
    "escape": "esc",
    "esc": "esc",
    "tab": "tab",
    "space": "spc",
    "backspace": "backspace",
    "delete": "delete",
    "print": "print",
    "printscreen": "print",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "home": "home",
    "end": "end",
    "pageup": "pgup",
    "pagedown": "pgdn",
    **{f"f{i}": f"f{i}" for i in range(1, 13)},
}

# Plain characters on a US layout: char -> (qcode, needs_shift)
_CHARS: dict[str, tuple[str, bool]] = {}
for _c in "abcdefghijklmnopqrstuvwxyz":
    _CHARS[_c] = (_c, False)
    _CHARS[_c.upper()] = (_c, True)
for _d in "0123456789":
    _CHARS[_d] = (_d, False)
for _ch, _q in {
    " ": "spc",
    "-": "minus",
    "=": "equal",
    "[": "bracket_left",
    "]": "bracket_right",
    ";": "semicolon",
    "'": "apostrophe",
    "`": "grave_accent",
    "\\": "backslash",
    ",": "comma",
    ".": "dot",
    "/": "slash",
    "\n": "ret",
}.items():
    _CHARS[_ch] = (_q, False)
for _ch, _q in {
    "!": "1",
    "@": "2",
    "#": "3",
    "$": "4",
    "%": "5",
    "^": "6",
    "&": "7",
    "*": "8",
    "(": "9",
    ")": "0",
    "_": "minus",
    "+": "equal",
    "{": "bracket_left",
    "}": "bracket_right",
    ":": "semicolon",
    '"': "apostrophe",
    "~": "grave_accent",
    "|": "backslash",
    "<": "comma",
    ">": "dot",
    "?": "slash",
}.items():
    _CHARS[_ch] = (_q, True)


class KeySpecError(ValueError):
    pass


def parse_key(spec: str) -> list[str]:
    """'super+shift+b' -> ['meta_l', 'shift', 'b'] (modifiers first)."""
    parts = [p.strip().lower() for p in spec.split("+") if p.strip()]
    if not parts:
        raise KeySpecError(f"empty key spec: {spec!r}")
    *mods, key = parts
    codes: list[str] = []
    for m in mods:
        if m not in MODIFIERS:
            raise KeySpecError(f"unknown modifier {m!r} in {spec!r}")
        codes.append(MODIFIERS[m])
    if key in NAMED:
        codes.append(NAMED[key])
    elif key in MODIFIERS:
        codes.append(MODIFIERS[key])
    elif len(key) == 1 and key in _CHARS:
        q, shifted = _CHARS[key]
        if shifted and "shift" not in codes:
            codes.append("shift")
        codes.append(q)
    else:
        raise KeySpecError(f"unknown key {key!r} in {spec!r}")
    return codes


def text_to_chords(text: str) -> list[list[str]]:
    """Text -> one chord per character (US layout)."""
    chords: list[list[str]] = []
    for ch in text:
        if ch not in _CHARS:
            raise KeySpecError(f"cannot type character {ch!r}")
        q, shifted = _CHARS[ch]
        chords.append(["shift", q] if shifted else [q])
    return chords
