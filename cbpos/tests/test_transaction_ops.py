from unittest.mock import MagicMock, patch

from cbpos.core.models import Sale, User
from cbpos.core.services.transaction_service import TransactionService


@patch("cbpos.core.services.transaction_service.Database")
def test_lock_order(mock_db):
    # Setup
    mock_session = MagicMock()
    mock_db.return_value.SessionLocal.return_value = mock_session

    mock_sale = MagicMock(spec=Sale)
    mock_sale.status = "COMPLETED"
    mock_session.query.return_value.get.return_value = mock_sale

    # Execute
    result = TransactionService.lock_order(1)

    # Verify
    assert result is True
    assert mock_sale.status == "LOCKED"
    mock_session.commit.assert_called_once()


@patch("cbpos.core.services.transaction_service.Database")
def test_transfer_order(mock_db):
    # Setup
    mock_session = MagicMock()
    mock_db.return_value.SessionLocal.return_value = mock_session

    mock_sale = MagicMock(spec=Sale)
    mock_sale.user_id = 1
    mock_sale.document_number = "REC-123"

    mock_user = MagicMock(spec=User)
    mock_user.id = 2
    mock_user.username = "NewUser"

    def get_side_effect(model_id):
        if model_id == 100:
            return mock_sale
        if model_id == 200:
            return mock_user
        return None

    mock_session.query.return_value.get.side_effect = get_side_effect

    # Execute
    # sale_id=100, target_user_id=200
    result = TransactionService.transfer_order(100, 200)

    # Verify
    assert result is True
    assert mock_sale.user_id == 200
    mock_session.add.assert_called()  # Audit Log added
    mock_session.commit.assert_called_once()
