import pytest

from hornero_qa.keys import KeySpecError, parse_key, text_to_chords


def test_modifier_chords() -> None:
    assert parse_key("super+shift+b") == ["meta_l", "shift", "b"]
    assert parse_key("CTRL+Space") == ["ctrl", "spc"]
    assert parse_key("escape") == ["esc"]
    assert parse_key("ctrl+print") == ["ctrl", "print"]


def test_text_uses_shift_for_upper_case() -> None:
    assert text_to_chords("aB") == [["a"], ["shift", "b"]]


@pytest.mark.parametrize("spec", ["", "hyper+a", "super+nosuchkey"])
def test_bad_specs(spec: str) -> None:
    with pytest.raises(KeySpecError):
        parse_key(spec)
