"""
#421: an unmapped SyncClient state fell back to the raw internal string
(e.g. "reconnecting") instead of a translated label. Confirms the fallback
now goes through _t("common.unknown") instead.
#906: failing push must not report "Synced"; server bind error must show error badge;
connected terminals must count distinct active terminals within 5 minutes.
"""

import urllib.error
from datetime import datetime, timedelta

from cbpos.core.models import SyncTerminal
from cbpos.infrastructure.sync_client import SyncClient
from cbpos.ui.widgets.sync_status_widget import SyncStatusWidget


def test_unmapped_state_falls_back_to_translated_unknown(qapp):
    widget = SyncStatusWidget()
    widget.set_mode("terminal")
    widget.set_state("reconnecting")

    details = widget._build_details_text()

    assert "reconnecting" not in details
    assert "Unknown" in details


def test_issue_906_push_500_shows_error_with_pending(qapp, monkeypatch):
    widget = SyncStatusWidget()
    widget.set_mode("terminal")

    client = SyncClient("TERM-02", "127.0.0.1:5555", shared_secret="secret")
    client.status_changed.connect(widget.set_state)
    if hasattr(client, "pending_changed"):
        client.pending_changed.connect(widget.set_pending_count)
    client.error_signal.connect(widget.on_sync_error)

    # Mock pending count to 3
    monkeypatch.setattr(SyncClient, "pending_count", property(lambda self: 3))

    # Mock successful register, but push returning 500
    monkeypatch.setattr(client, "_try_register", lambda: True)
    client._state = SyncClient.STATE_CONNECTED
    monkeypatch.setattr(client, "_collect_unsynced", lambda: ({"sales": [{"id": 1}]}, {("sales", 1): "fp"}))

    def mock_urlopen(req, timeout=10, context=None):
        raise urllib.error.HTTPError(
            req.full_url,
            500,
            "Internal Server Error",
            {},
            None,
        )

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    # Execute one sync cycle
    client._push_transactions()

    # Even if register succeeds afterwards, state must remain error
    client._try_register()

    assert widget._pending == 3
    assert widget._dot.property("status") == "error"
    assert "Synced" not in widget._label.text()


def test_issue_906_server_bind_failure_shows_error(qapp):
    widget = SyncStatusWidget()
    widget.set_mode("main")

    # Simulate server error (e.g. port already bound)
    if hasattr(widget, "on_server_error"):
        widget.on_server_error("Sync server failed to start on port 5555: Address already in use")
    else:
        widget.on_sync_error("Sync server failed to start on port 5555: Address already in use")

    assert widget._dot.property("status") == "error"
    assert "Main PC error" in widget._label.text() or "error" in widget._label.text().lower()


def test_issue_906_connected_terminals_counts_distinct(qapp, db_session):
    now = datetime.now()
    # Add active terminal 1
    t1 = SyncTerminal(terminal_id="TERM-01", db_instance_id="inst-1", last_seen=now, released=False)
    # Add active terminal 2
    t2 = SyncTerminal(
        terminal_id="TERM-02", db_instance_id="inst-2", last_seen=now - timedelta(minutes=2), released=False
    )
    # Add stale terminal 3 (seen 10 minutes ago)
    t3 = SyncTerminal(
        terminal_id="TERM-03", db_instance_id="inst-3", last_seen=now - timedelta(minutes=10), released=False
    )
    # Add released terminal 4
    t4 = SyncTerminal(terminal_id="TERM-04", db_instance_id="inst-4", last_seen=now, released=True)
    db_session.add_all([t1, t2, t3, t4])
    db_session.flush()

    widget = SyncStatusWidget()
    widget.set_mode("main")

    # Trigger terminal connect
    widget.on_terminal_connected("TERM-01")

    assert widget._connected_terminals == 2
    assert "2" in widget._label.text()
