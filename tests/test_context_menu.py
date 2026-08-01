import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.actions.context_menu import click_context_menu_item


def test_click_context_menu_prefers_uia() -> None:
    item = MagicMock()
    menu = MagicMock()
    menu.element_info.class_name = "Menu"
    menu.descendants.return_value = [item]
    item.window_text.return_value = "Kick Player"

    desktop = MagicMock()
    desktop.windows.return_value = [menu]

    with patch("pywinauto.Desktop", return_value=desktop):
        assert click_context_menu_item(["Kick Player"], down_presses=3) is True
    item.click_input.assert_called_once()


def test_click_context_menu_falls_back_to_keyboard() -> None:
    mock_gui = MagicMock()
    with patch("antismurf.actions.context_menu._click_via_uia", return_value=False):
        with patch.dict(sys.modules, {"pyautogui": mock_gui}):
            assert click_context_menu_item(["Missing"], down_presses=2) is True
            assert mock_gui.press.call_count == 3
