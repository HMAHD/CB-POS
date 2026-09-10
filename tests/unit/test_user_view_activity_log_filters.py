import pytest

from cbpos.ui.views.user_view import UserView

pytestmark = pytest.mark.usefixtures("qapp")


def test_construct_only(db_session):
    UserView()
