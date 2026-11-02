"""
#638: Settings -> Documents stored number formats with no validation. A
format without {seq} made generate_number() return ERR-TIMEOUT (so the
second GRN failed the unique constraint), {seq} in the middle made the
numbers explode, and a bad spec produced random ERR- numbers.

validate_doc_pattern() now rejects those formats, generate_number() falls
back to the default pattern when settings.json holds a bad one, and the
shared render_pattern() keeps the Settings preview and the generator in
step.
"""

import logging
from datetime import datetime

import pytest

from cbpos.core.models import Document, User
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.document_service import (
    DEFAULT_PATTERNS,
    DocumentService,
    render_pattern,
    validate_doc_pattern,
)


class TestValidateDocPattern:
    @pytest.mark.parametrize(
        "pattern",
        [
            "GRN-{Y}",  # no {seq}
            "GRN-{seq:05d}-{Y}",  # {seq} not last
            "GRN-{Y}-{seq:5d}",  # bad spec (space padding)
            "GRN-{Y}-{seq:010d}",  # bad spec (width > 9)
            "GRN-{Y}-{seq:abc}",  # bad spec
            "",  # empty
            "   ",  # blank
            "GRN-{X}-{seq}",  # unknown placeholder
            "GRN-{Y-{seq}",  # unbalanced brace
            "GRN_{Y}-{seq}",  # LIKE wildcard
            "GRN%-{seq}",  # LIKE wildcard
            "{seq}-{seq}",  # two {seq}
            "G" * 60 + "{seq}",  # longer than the column
        ],
    )
    def test_invalid_patterns_are_rejected(self, pattern):
        assert validate_doc_pattern(pattern) is not None

    @pytest.mark.parametrize(
        "pattern",
        [*DEFAULT_PATTERNS.values(), "GRN-{seq}", "P{T}-{Y}{M}{D}-{seq:09d}", "X-{terminal}-{seq:01d}"],
    )
    def test_valid_patterns_are_accepted(self, pattern):
        assert validate_doc_pattern(pattern) is None


def test_render_pattern_fills_every_placeholder():
    now = datetime(2026, 3, 7)
    assert render_pattern("GRN-{Y}{M}{D}-{T}-{seq:05d}", 42, now, "TERM-01") == "GRN-20260307-TERM01-00042"
    assert render_pattern("X-{terminal}-{seq}", 7, now, "T3") == "X-T3-7"


@pytest.fixture
def user(db_session):
    u = User(username="docfmt_user", pin_hash="x", role_id=None, is_active=True)
    db_session.add(u)
    db_session.flush()
    return u


def _settings(monkeypatch, **overrides):
    data = {"doc_reset_period": "YEARLY", "terminal_id": "TERM-01", **overrides}
    monkeypatch.setattr(ConfigService, "get_all", lambda: dict(data))


def _save(db_session, user, number):
    db_session.add(Document(document_number=number, type="document", user_id=user.id))
    db_session.flush()


class TestGenerateNumber:
    def test_invalid_stored_pattern_falls_back_to_default(self, db_session, user, monkeypatch, caplog):
        _settings(monkeypatch, doc_format_purchase="GRN-{Y}")
        year = datetime.now().strftime("%Y")

        numbers = []
        with caplog.at_level(logging.WARNING):
            for _ in range(3):
                number = DocumentService.generate_number("PURCHASE")
                _save(db_session, user, number)
                numbers.append(number)

        assert numbers == [f"GRN-{year}-00001", f"GRN-{year}-00002", f"GRN-{year}-00003"]
        assert any("GRN-{Y}" in r.getMessage() for r in caplog.records)

    def test_generator_matches_render_pattern(self, db_session, user, monkeypatch):
        pattern = "TST{T}-{Y}{M}-{seq:04d}"
        _settings(monkeypatch, doc_format_purchase=pattern, doc_reset_period="MONTHLY")

        first = DocumentService.generate_number("PURCHASE")
        assert first == render_pattern(pattern, 1, datetime.now(), "TERM-01")
        _save(db_session, user, first)

        second = DocumentService.generate_number("PURCHASE")
        assert second == render_pattern(pattern, 2, datetime.now(), "TERM-01")

    def test_preview_number_matches_next_generated_number(self, db_session, user, monkeypatch):
        pattern = "PV-{Y}-{seq:03d}"
        _settings(monkeypatch, doc_format_purchase=pattern)
        _save(db_session, user, DocumentService.generate_number("PURCHASE"))

        preview = DocumentService.preview_number(pattern, "YEARLY", "TERM-01")
        assert preview == DocumentService.generate_number("PURCHASE")
