"""
light.qss's CustomerPanel card (POS main screen, ActionPanel's customer
card) still used the retired navy #001F3F for both its background and
its border -- the border was invisible against its own identical
background, and CustTitle/CustomerLabel/PointsLabel all hardcoded white
text, which the dark theme's equivalent (a neutral #252528 surface with
a real #3E3E42 border) never needed. Missed during the earlier
navy-retirement pass (#260) -- found while fixing #255 (#387).
"""

from pathlib import Path

from tests.helpers.qss import rendered_qss

STYLES_DIR = Path(__file__).resolve().parents[2] / "cbpos" / "ui" / "styles"


def _load(theme_file: str) -> str:
    return rendered_qss(theme_file)


def _block(css: str, selector: str) -> str:
    start = css.index(selector)
    end = css.index("}", start)
    return css[start : end + 1]


class TestCustomerPanelLightTheme:
    def test_customer_panel_no_longer_uses_navy(self):
        css = _load("light.qss")
        block = _block(css, "QFrame#CustomerPanel {")
        assert "#001F3F" not in block

    def test_customer_panel_border_is_distinct_from_its_background(self):
        css = _load("light.qss")
        block = _block(css, "QFrame#CustomerPanel {")
        assert "background-color: #FFFFFF" in block
        # The strong border token (D20: #D0D5DB snapped to #CED4DA), visibly darker than the white fill.
        assert "border: 1px solid #CED4DA" in block

    def test_cust_title_is_readable_on_the_new_light_surface(self):
        css = _load("light.qss")
        block = _block(css, "QLabel#CustTitle {")
        assert "color: #FFFFFF" not in block

    def test_customer_label_is_readable_on_the_new_light_surface(self):
        css = _load("light.qss")
        block = _block(css, "QLabel#CustomerLabel {")
        assert "color: white" not in block

    def test_points_divider_is_visible_on_a_white_card(self):
        css = _load("light.qss")
        block = _block(css, "QFrame#PointsDivider {")
        assert "rgba(255, 255, 255" not in block

    def test_points_label_is_no_longer_white_on_near_white(self):
        css = _load("light.qss")
        block = _block(css, "QFrame#CustomerPanel QLabel#PointsLabel {")
        assert "color: white" not in block
