from unittest.mock import patch

import pytest

from cbpos.ui.views.user_view import UserView

pytestmark = pytest.mark.usefixtures("qapp")


def test_construct_only(db_session):
    UserView()


def test_user_view_terminal_filter_combo_and_clear(db_session):
    with patch(
        "cbpos.core.services.user_service.UserService.get_distinct_terminals", return_value=["MAIN-01", "TERM-02"]
    ):
        view = UserView()
        view.tabs.setCurrentIndex(1)  # Activity Log tab

        assert hasattr(view, "log_terminal_filter")
        assert view.log_terminal_filter.count() == 3  # "All tills", "MAIN-01", "TERM-02"
        assert view.log_terminal_filter.itemData(0) is None
        assert view.log_terminal_filter.itemData(1) == "MAIN-01"
        assert view.log_terminal_filter.itemData(2) == "TERM-02"

        # Select TERM-02
        view.log_terminal_filter.setCurrentIndex(2)

        with patch("cbpos.core.services.user_service.UserService.get_recent_activity", return_value=[]) as mock_get:
            view.log_filter_btn.click()
            mock_get.assert_called_once()
            _, kwargs = mock_get.call_args
            assert kwargs.get("terminal_id") == "TERM-02"

        # Clear filter
        view.log_clear_btn.click()
        assert view.log_terminal_filter.currentIndex() == 0
        assert view.log_terminal_filter.currentData() is None
