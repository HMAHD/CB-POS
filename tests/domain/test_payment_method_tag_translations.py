"""
#338: tag_cash/tag_opens_drawer were left as literal untranslated
English ("Cash"/"Opens Drawer") in both si.json and ta.json, unlike the
neighboring status_active/status_inactive keys in the same section,
which are properly localized -- a real gap in the trilingual guarantee.
"""

from cbpos.i18n import translate_in


class TestPaymentMethodTagsAreLocalized:
    def test_tag_cash_is_translated_in_sinhala(self):
        assert translate_in("si", "payment_methods.tag_cash") != "Cash"

    def test_tag_cash_is_translated_in_tamil(self):
        assert translate_in("ta", "payment_methods.tag_cash") != "Cash"

    def test_tag_opens_drawer_is_translated_in_sinhala(self):
        assert translate_in("si", "payment_methods.tag_opens_drawer") != "Opens Drawer"

    def test_tag_opens_drawer_is_translated_in_tamil(self):
        assert translate_in("ta", "payment_methods.tag_opens_drawer") != "Opens Drawer"
