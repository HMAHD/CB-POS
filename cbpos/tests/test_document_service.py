from unittest.mock import patch, MagicMock
from cbpos.core.services.document_service import DocumentService


@patch("cbpos.core.services.document_service.Database")
@patch("cbpos.core.services.config_service.ConfigService")
def test_generate_number_default(mock_config, mock_db):
    # Setup

    mock_session = MagicMock()
    mock_db.return_value.get_session.return_value.__enter__.return_value = mock_session

    # Mock no existing document
    mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

    # Mock collision check
    mock_session.query.return_value.filter_by.return_value.first.return_value = None

    # Execute
    doc_num = DocumentService.generate_number("SALE")

    # Verify
    # Default format: INV-{Y}-{seq:05d}
    # Should contain INV- and -00001
    assert "INV-" in doc_num
    assert "-00001" in doc_num


@patch("cbpos.core.services.document_service.Database")
@patch("cbpos.core.services.config_service.ConfigService")
def test_generate_number_custom_pattern(mock_config, mock_db):
    # Setup
    mock_config.get_all.return_value = {"doc_format_sale": "MYINV-{Y}-{seq:03d}"}

    mock_session = MagicMock()
    mock_db.return_value.get_session.return_value.__enter__.return_value = mock_session

    # Mock existing document
    mock_last_doc = MagicMock()
    mock_last_doc.document_number = "MYINV-2023-005"
    mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = mock_last_doc

    # Mock collision check (filter_by) to return None (does not exist)
    mock_session.query.return_value.filter_by.return_value.first.return_value = None

    # Execute
    with patch("cbpos.core.services.document_service.datetime") as mock_date:
        mock_date.now.return_value.strftime.side_effect = lambda fmt: ("2023" if fmt == "%Y" else "01")

        doc_num = DocumentService.generate_number("SALE")

        # Verify
        # Should be MYINV-2023-006
        assert "MYINV-2023-006" in doc_num


@patch("cbpos.core.services.document_service.Database")
@patch("cbpos.core.services.config_service.ConfigService")
def test_generate_number_retry_logic(mock_config, mock_db):
    # Setup
    mock_config.get_all.return_value = {}

    mock_session = MagicMock()
    mock_db.return_value.get_session.return_value.__enter__.return_value = mock_session

    # Mock no existing document initially
    mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

    # Mock collision check: First attempt returns Exists, Second returns None
    mock_exists = MagicMock()
    mock_session.query.return_value.filter_by.return_value.first.side_effect = [
        mock_exists,
        None,
    ]

    # Execute
    doc_num = DocumentService.generate_number("SALE")

    # Verify
    # Should succeed eventually
    assert "INV-" in doc_num
