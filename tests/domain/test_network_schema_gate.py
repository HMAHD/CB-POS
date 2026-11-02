"""Tests for network schema startup gate (#799)."""

from unittest.mock import patch

import pytest

from cbpos.ui.network_schema_gate import GateAction, NetworkSchemaGate, UpgradeWorker, decide


@pytest.mark.domain
def test_issue_799_gate_decide_pure_matrix():
    """Verify decide() pure function covers all branching conditions."""
    head = "e9f2a1b4c803"
    known = {"07efbe333f81", "e9f2a1b4c803"}

    # 1. Matches head -> CONTINUE
    assert decide(rev=head, head=head, known=known, is_owner=False) == GateAction.CONTINUE
    assert decide(rev=head, head=head, known=known, is_owner=True) == GateAction.CONTINUE

    # 2. None (fresh DB) -> CONTINUE
    assert decide(rev=None, head=head, known=known, is_owner=False) == GateAction.CONTINUE
    assert decide(rev=None, head=head, known=known, is_owner=True) == GateAction.CONTINUE

    # 3. Revision not in known set (DB is newer than this client) -> BLOCK_APP_TOO_OLD
    assert decide(rev="future_rev_999", head=head, known=known, is_owner=False) == GateAction.BLOCK_APP_TOO_OLD
    assert decide(rev="future_rev_999", head=head, known=known, is_owner=True) == GateAction.BLOCK_APP_TOO_OLD

    # 4. Revision behind head, machine is not owner -> BLOCK_NEEDS_OWNER_UPDATE
    assert decide(rev="07efbe333f81", head=head, known=known, is_owner=False) == GateAction.BLOCK_NEEDS_OWNER_UPDATE

    # 5. Revision behind head, machine is owner -> PROMPT_OWNER_UPDATE
    assert decide(rev="07efbe333f81", head=head, known=known, is_owner=True) == GateAction.PROMPT_OWNER_UPDATE


@pytest.mark.domain
def test_issue_799_upgrade_worker_signals():
    """Verify UpgradeWorker signals on success and failure."""
    worker = UpgradeWorker("sqlite:///:memory:", user_id=1)

    success_called = []
    error_called = []

    worker.success.connect(lambda: success_called.append(True))
    worker.error.connect(lambda err: error_called.append(err))

    with patch("cbpos.core.services.schema_migration_service.SchemaMigrationService.upgrade_with_lock") as mock_upgrade:
        mock_upgrade.return_value = None
        worker.run()
        assert len(success_called) == 1
        assert len(error_called) == 0

    with patch("cbpos.core.services.schema_migration_service.SchemaMigrationService.upgrade_with_lock") as mock_upgrade:
        mock_upgrade.side_effect = RuntimeError("Lock timeout")
        worker.run()
        assert len(error_called) == 1
        assert "Lock timeout" in error_called[0]


@pytest.mark.domain
def test_issue_799_gate_skipped_when_not_network_mode():
    """When DB_MODE is not network, check_and_gate proceeds immediately."""
    with patch("cbpos.core.services.config_service.ConfigService.get", return_value="local"):
        assert NetworkSchemaGate.check_and_gate() is True
