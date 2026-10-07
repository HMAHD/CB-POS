import logging
import re
import time
from datetime import datetime

from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError

from cbpos.core.database import Database
from cbpos.core.models import Document

logger = logging.getLogger(__name__)

# Pre-compiled regex for {seq:05d} or {seq} placeholders
_SEQ_RE = re.compile(r"\{seq(:.*?)?\}")
# Every {...} token, plus any stray brace that isn't part of one
_TOKEN_RE = re.compile(r"\{[^{}]*\}|[{}]")
# The only accepted sequence forms: {seq} or {seq:0Nd} with N 1-9
_VALID_SEQ_RE = re.compile(r"\{seq(?::0[1-9]d)?\}")
_STATIC_PLACEHOLDERS = ("{Y}", "{M}", "{D}", "{T}", "{terminal}")
DOC_NUMBER_MAX_LENGTH: int = Document.__table__.c.document_number.type.length

DEFAULT_PATTERNS: dict[str, str] = {
    "SALE": "INV-{Y}-{seq:05d}",
    "PURCHASE": "GRN-{Y}-{seq:05d}",
    "PURCHASE_ORDER": "PO-{Y}-{seq:05d}",
    "RETURN": "CN-{Y}-{seq:05d}",
    "STOCK_COUNT": "STK-{Y}-{seq:05d}",
    "ADJUSTMENT": "ADJ-{Y}-{seq:05d}",
    "PROFORMA": "QUO-{Y}-{seq:05d}",
}
_FALLBACK_PATTERN = "DOC-{Y}-{seq:05d}"
# Receipts that synced tills (terminal_mode "main"/"terminal") number in
# their own local database and later push to the Main PC.
_TERMINAL_SCOPED_TYPES = ("SALE", "RETURN")
_SYNC_TERMINAL_MODES = ("main", "terminal")


def _terminal_short(terminal_id: str) -> str:
    """Return the short terminal suffix: "TERM-01" -> "01", "T3" -> "T3"."""
    return terminal_id.split("-")[-1] if "-" in terminal_id else terminal_id


def _render_static(pattern: str, now: datetime, terminal_id: str) -> str:
    """Replace the date and terminal placeholders, leaving {seq} untouched."""
    terminal = _terminal_short(terminal_id)
    return (
        pattern.replace("{Y}", now.strftime("%Y"))
        .replace("{M}", now.strftime("%m"))
        .replace("{D}", now.strftime("%d"))
        .replace("{T}", terminal)
        .replace("{terminal}", terminal)
    )


def render_pattern(pattern: str, seq: int, now: datetime, terminal_id: str) -> str:
    """Render a document number pattern into a concrete number.

    Shared by generate_number() and the Settings preview so the two can
    never disagree.

    Args:
        pattern: Format such as ``"GRN-{Y}-{seq:05d}"``.
        seq: Sequence number to fill into ``{seq}``.
        now: Date used for ``{Y}``, ``{M}`` and ``{D}``.
        terminal_id: Terminal ID; its short suffix fills ``{T}``/``{terminal}``.

    Returns:
        The rendered document number.
    """
    rendered = _render_static(pattern, now, terminal_id)
    match = _SEQ_RE.search(rendered)
    if not match:
        return f"{rendered}{seq}"
    seq_str = ("{" + (match.group(1) or "") + "}").format(seq)
    return rendered.replace(match.group(0), seq_str)


def validate_doc_pattern(pattern: str, terminal_id: str = "TERM-01") -> str | None:
    """Check a document number pattern before it is saved or used.

    Rules: not empty; exactly one ``{seq}``/``{seq:0Nd}`` (N 1-9) and it is
    the last thing in the pattern; only known placeholders; no ``%`` or
    ``_`` (they break the LIKE prefix search); rendered length fits the
    ``document_number`` column.

    Args:
        pattern: Format to check.
        terminal_id: Terminal ID used to measure the rendered length.

    Returns:
        An i18n error key under ``settings.documents``, or None if valid.
    """
    if not pattern or not pattern.strip():
        return "settings.documents.fmt_error_empty"
    if "%" in pattern or "_" in pattern:
        return "settings.documents.fmt_error_bad_char"

    seq_tokens = []
    for token in _TOKEN_RE.findall(pattern):
        if token.startswith("{seq"):
            if not _VALID_SEQ_RE.fullmatch(token):
                return "settings.documents.fmt_error_bad_seq"
            seq_tokens.append(token)
        elif token not in _STATIC_PLACEHOLDERS:
            return "settings.documents.fmt_error_unknown_placeholder"

    if len(seq_tokens) != 1:
        return "settings.documents.fmt_error_seq_once"
    if not pattern.endswith(seq_tokens[0]):
        return "settings.documents.fmt_error_seq_not_last"
    # Leave room for at least five sequence digits
    if len(render_pattern(pattern, 99999, datetime.now(), terminal_id)) > DOC_NUMBER_MAX_LENGTH:
        return "settings.documents.fmt_error_too_long"
    return None


def terminal_scoped_pattern(pattern: str, doc_type: str, terminal_mode: str) -> str:
    """Put the terminal in front of a sale/return format on synced tills.

    In sync mode each till numbers receipts offline in its own database and
    pushes them to the Main PC, where ``document_number`` is unique. A shared
    ``INV-{Y}-{seq}`` series would hand two tills the same number, so unless
    the format already names the terminal, ``{T}-`` is prefixed. The result
    starts with the terminal, so each till's LIKE prefix (and sequence) is
    its own.

    Args:
        pattern: The (valid) stored format.
        doc_type: e.g. "SALE", "RETURN", "PURCHASE".
        terminal_mode: "standalone", "main" or "terminal".

    Returns:
        The format generate_number() actually uses.
    """
    if (
        doc_type in _TERMINAL_SCOPED_TYPES
        and terminal_mode in _SYNC_TERMINAL_MODES
        and "{T}" not in pattern
        and "{terminal}" not in pattern
    ):
        return "{T}-" + pattern
    return pattern


def _search_prefix(pattern: str, reset_period: str, now: datetime, terminal_id: str) -> str:
    """Build the LIKE prefix that scopes the sequence to the reset period.

    YEARLY wildcards the month/day, MONTHLY wildcards the day, NEVER uses
    the rendered text before ``{seq}`` as-is.
    """
    pre_seq = pattern.split("{seq", 1)[0]
    if reset_period == "YEARLY":
        pre_seq = pre_seq.replace("{M}", "%").replace("{D}", "%")
    elif reset_period == "MONTHLY":
        pre_seq = pre_seq.replace("{D}", "%")
    return _render_static(pre_seq, now, terminal_id)


def _next_seq(session, search_prefix: str) -> int:
    """Return the sequence that follows the highest number under ``search_prefix``."""
    last_doc = (
        session.query(Document)
        .filter(Document.document_number.like(f"{search_prefix}%"))
        .order_by(desc(Document.document_number))
        .first()
    )
    if last_doc:
        # {seq} is always last (validate_doc_pattern), so the trailing
        # digits are the sequence.
        match = re.search(r"(\d+)$", last_doc.document_number)
        if match:
            return int(match.group(1)) + 1
    return 1


class DocumentService:
    """
    Service to generate unique document numbers (e.g., INV-2023-00001).
    """

    PREFIXES = {
        "SALE": "INV",
        "PURCHASE": "GRN",
        "RETURN": "CN",  # Credit Note
        "STOCK_COUNT": "STK",
        "ADJUSTMENT": "ADJ",
        "PROFORMA": "QUO",
    }

    @staticmethod
    def adds_terminal_prefix(pattern: str, doc_type: str) -> bool:
        """Return True if this till puts its terminal in front of ``pattern`` (see terminal_scoped_pattern())."""
        from cbpos.core.services.config_service import ConfigService

        terminal_mode = ConfigService.get("terminal_mode") or "standalone"
        return terminal_scoped_pattern(pattern, doc_type, terminal_mode) != pattern

    @staticmethod
    def preview_number(pattern: str, reset_period: str, terminal_id: str, doc_type: str = "") -> str:
        """Return the number the next document would get with this pattern.

        Read-only: nothing is reserved. Used by the Settings live preview.

        Args:
            pattern: A valid format (see validate_doc_pattern()).
            reset_period: YEARLY, MONTHLY or NEVER.
            terminal_id: Terminal ID for ``{T}``/``{terminal}``.
            doc_type: Document type, so the preview matches
                terminal_scoped_pattern() for sales/returns on synced tills.

        Returns:
            The rendered next number (sequence 1 if the lookup fails).
        """
        from cbpos.core.services.config_service import ConfigService

        pattern = terminal_scoped_pattern(pattern, doc_type, ConfigService.get("terminal_mode") or "standalone")
        now = datetime.now()
        seq = 1
        try:
            with Database().get_session() as session:
                seq = _next_seq(session, _search_prefix(pattern, reset_period, now, terminal_id))
        except Exception as e:
            logger.warning("Document number preview lookup failed: %s", e)
        return render_pattern(pattern, seq, now, terminal_id)

    @staticmethod
    def generate_number(doc_type: str, session=None) -> str:
        """Generate the next sequential document number for the given type.

        Supports configurable patterns and concurrency retries. A stored
        pattern that fails validate_doc_pattern() (settings.json can be
        hand-edited) is logged and replaced by the default pattern.

        Args:
            doc_type: e.g. "SALE", "RETURN", "PURCHASE", "PROFORMA".
            session: The caller's open session. When given, the number is
                read inside the caller's transaction (it sees the caller's
                own flushed documents, and nothing is committed here); the
                caller inserts the document in that same transaction and
                relies on the unique ``document_number`` index to catch a
                number another till took meanwhile. Errors propagate
                instead of yielding an ``ERR-`` number.

        Returns:
            The new document number.
        """
        from cbpos.core.services.config_service import ConfigService

        settings = ConfigService.get_all()
        default_pattern = DEFAULT_PATTERNS.get(doc_type, _FALLBACK_PATTERN)
        key = f"doc_format_{doc_type.lower()}"
        pattern = settings.get(key, default_pattern)
        reset_period = settings.get("doc_reset_period", "YEARLY")  # YEARLY, MONTHLY, NEVER
        terminal_id = settings.get("terminal_id", "TERM-01") or "TERM-01"

        error = validate_doc_pattern(pattern, terminal_id)
        if error:
            logger.warning("Invalid %s %r (%s); using default %r", key, pattern, error, default_pattern)
            pattern = default_pattern
        pattern = terminal_scoped_pattern(pattern, doc_type, settings.get("terminal_mode") or "standalone")

        now = datetime.now()
        search_prefix = _search_prefix(pattern, reset_period, now, terminal_id)

        if session is not None:
            return render_pattern(pattern, _next_seq(session, search_prefix), now, terminal_id)

        # Retry loop for concurrency. Use serializable isolation in network
        # mode to prevent two terminals from reading the same max sequence.
        max_retries = 5
        for attempt in range(max_retries):
            try:
                db = Database()
                with db.get_session(serializable=True) as session:
                    final_number = render_pattern(pattern, _next_seq(session, search_prefix), now, terminal_id)

                    # Verify uniqueness within the same serializable
                    # transaction — concurrent terminals will block here.
                    exists = session.query(Document).filter_by(document_number=final_number).first()
                    if not exists:
                        return final_number

                    # Number already exists — retry with next sequence
                    logger.info("Document number %s already exists, retrying...", final_number)

            except IntegrityError:
                logger.warning("Document number collision on attempt %d, retrying...", attempt + 1)
                time.sleep(0.05)
            except Exception as e:
                logger.error("Error generating document number: %s", e)
                if attempt == max_retries - 1:
                    import uuid

                    return f"ERR-{uuid.uuid4().hex[:8].upper()}"

        return "ERR-TIMEOUT"

    @staticmethod
    def generate_tax_invoice_number() -> str:
        """
        Generate a compliant Sri Lankan tax invoice serial number.

        Format: YYMMM_QQQQ_XXXX where:
            YY   = last 2 digits of year
            MMM  = first 3 letters of month in English capitals
            QQQQ = branch counter (0001 for single-branch)
            XXXX = sequential invoice counter within month
        """
        import time

        now = datetime.now()
        yy = now.strftime("%y")
        mmm = now.strftime("%b").upper()[:3]
        branch = "0001"
        prefix = f"{yy}{mmm}_{branch}_"

        max_retries = 3
        for attempt in range(max_retries):
            try:
                db = Database()
                with db.get_session() as session:
                    last_doc = (
                        session.query(Document)
                        .filter(Document.document_number.like(f"{prefix}%"))
                        .order_by(desc(Document.document_number))
                        .first()
                    )

                    new_seq = 1
                    if last_doc:
                        current_no = last_doc.document_number
                        if current_no.startswith(prefix):
                            remainder = current_no[len(prefix) :]
                            digits = "".join(filter(str.isdigit, remainder))
                            if digits:
                                new_seq = int(digits) + 1

                    final_number = f"{prefix}{new_seq:04d}"

                    exists = session.query(Document).filter_by(document_number=final_number).first()
                    if not exists:
                        return final_number

                    new_seq += 1
                    time.sleep(0.05)

            except IntegrityError:
                logger.warning(
                    "Tax invoice number collision on attempt %d, retrying...",
                    attempt + 1,
                )
                time.sleep(0.05)
            except Exception as e:
                logger.error("Error generating tax invoice number: %s", e)
                if attempt == max_retries - 1:
                    import uuid

                    return f"TI-ERR-{uuid.uuid4().hex[:8].upper()}"

        return "TI-ERR-TIMEOUT"
