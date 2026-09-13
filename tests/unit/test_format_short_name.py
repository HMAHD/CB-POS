from cbpos.core.utils.formatters import format_short_name


class TestFormatShortName:
    def test_two_part_name_keeps_first_name_and_initial(self):
        assert format_short_name("Nimal Perera") == "Nimal P"

    def test_three_part_name_keeps_first_name_and_both_initials(self):
        assert format_short_name("Nimal Kasun Perera") == "Nimal K P"

    def test_single_part_name_is_unchanged(self):
        assert format_short_name("Nimal") == "Nimal"

    def test_empty_name_returns_empty(self):
        assert format_short_name("") == ""

    def test_extra_whitespace_is_collapsed(self):
        assert format_short_name("  Nimal   Kasun  Perera  ") == "Nimal K P"
