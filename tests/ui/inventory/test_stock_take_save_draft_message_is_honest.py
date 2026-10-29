"""
#313: "Save Draft" performed no save action of its own -- every counted
value is already persisted the moment it's typed, via update_count()
inside the model's setData(). But the button's confirmation dialog said
"Stock count saved as draft," implying an action had just occurred,
which erodes trust once a user realizes clicking it does nothing extra.
Rather than remove a button users may already rely on as a checkpoint,
make its message honestly describe the auto-save that's actually
happening.
"""

from unittest.mock import patch

import pytest

from cbpos.ui.views.stock_take_view import StockTakeView

pytestmark = pytest.mark.usefixtures("qapp")


class TestSaveDraftMessageIsHonestAboutAutosave:
    def test_message_describes_the_automatic_save_not_a_just_performed_action(self, db_session):
        view = StockTakeView()

        with patch("cbpos.ui.views.stock_take_view.QMessageBox.information") as mock_info:
            view.save_draft()

        mock_info.assert_called_once()
        args, _ = mock_info.call_args
        message = args[2]
        assert "already" in message.lower() or "automatically" in message.lower()
