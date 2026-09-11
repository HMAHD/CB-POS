"""
#295: the Users table showed the same ID number twice -- Qt's built-in
row-number gutter (never hidden) on the left, and a real "ID" data
column populated with user.id right next to it. Since users are
created sequentially the two numbers almost always match, reading as
an oversight rather than a deliberate ID column. Keep the real ID
column (genuinely useful data) and hide the redundant row-number
gutter.
"""

import pytest

from cbpos.ui.views.user_view import UserView

pytestmark = pytest.mark.usefixtures("qapp")


class TestUsersTableHasNoRedundantRowNumberGutter:
    def test_vertical_header_is_hidden(self, db_session):
        # isVisible() alone is unreliable here: an unshown widget reports
        # isVisible() == False regardless of whether setVisible(False) was
        # ever called, so a missing fix would still pass. isVisibleTo()
        # checks the explicit hidden state as if the table were shown,
        # without needing to actually .show() the whole view.
        view = UserView()
        assert view.table.verticalHeader().isVisibleTo(view.table) is False
