from kanban_tui.themes import DEFAULT_THEME, get_theme, theme_names


def test_builtin_theme_catalog_is_stable():
    assert DEFAULT_THEME == "arch"
    assert theme_names() == ("arch", "nord", "gruvbox", "dracula", "mono")


def test_theme_lookup_is_case_insensitive():
    assert get_theme("NORD").name == "nord"


def test_unknown_theme_is_rejected():
    try:
        get_theme("missing")
    except ValueError as exc:
        assert "unknown theme" in str(exc)
        assert "arch" in str(exc)
    else:
        raise AssertionError("unknown theme should fail")
