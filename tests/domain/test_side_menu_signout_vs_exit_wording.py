"""
#606: Sinhala and Tamil used the same word for "Sign Out" (leave your
user account) and "Exit Application" (close the whole POS), so a cashier
could quit the POS mid-shift while trying to log out.
"""

import pytest

from cbpos.i18n import translate_in

LOGOUT_KEYS = ("side_menu.sign_out", "side_menu.btn_sign_out", "management.sidebar_logout")
EXIT_KEYS = ("side_menu.exit_tooltip", "side_menu.tooltip_exit")


@pytest.mark.parametrize("lang", ["en", "si", "ta"])
def test_sign_out_and_exit_read_differently(lang: str) -> None:
    logout = {translate_in(lang, key) for key in LOGOUT_KEYS}
    exits = {translate_in(lang, key) for key in EXIT_KEYS}
    assert logout.isdisjoint(exits)
