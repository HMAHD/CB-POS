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
    def generate_number(doc_type: str) -> str:
        """
        Generate the next sequential document number for the given type.
        Supports configurable patterns and concurrency retries.
        """
        from cbpos.core.services.config_service import ConfigService

        # 1. Get Configuration
        settings = ConfigService.get_all()

        # Default Patterns
        defaults = {
            "SALE": "INV-{Y}-{seq:05d}",
            "PURCHASE": "GRN-{Y}-{seq:05d}",
            "RETURN": "CN-{Y}-{seq:05d}",
            "STOCK_COUNT": "STK-{Y}-{seq:05d}",
            "ADJUSTMENT": "ADJ-{Y}-{seq:05d}",
            "PROFORMA": "QUO-{Y}-{seq:05d}",
        }

        pattern = settings.get(
            f"doc_format_{doc_type.lower()}",
            defaults.get(doc_type, "DOC-{Y}-{seq:05d}"),
        )
        reset_period = settings.get("doc_reset_period", "YEARLY")  # YEARLY, MONTHLY, NEVER

        # 2. Parse placeholders
        now = datetime.now()
        year_str = now.strftime("%Y")
        month_str = now.strftime("%m")
        day_str = now.strftime("%d")
        terminal_id = settings.get("terminal_id", "TERM-01") or "TERM-01"
        # Short terminal suffix: "TERM-01" → "01", "T3" → "T3"
        terminal_short = terminal_id.split("-")[-1] if "-" in terminal_id else terminal_id

        # Render static placeholders (date + terminal)
        prefix_pattern = (
            pattern.replace("{Y}", year_str)
            .replace("{M}", month_str)
            .replace("{D}", day_str)
            .replace("{T}", terminal_short)
            .replace("{terminal}", terminal_short)
        )

        # Determine reset scope filter
        if reset_period == "MONTHLY":
            # Filter documents whose number matches the current year+month prefix
            scope_prefix = (
                pattern.split("{seq")[0]
                .replace("{Y}", year_str)
                .replace("{M}", month_str)
                .replace("{D}", "%")
                .replace("{T}", terminal_short)
                .replace("{terminal}", terminal_short)
            )
        elif reset_period == "YEARLY":
            scope_prefix = (
                pattern.split("{seq")[0]
                .replace("{Y}", year_str)
                .replace("{M}", "%")
                .replace("{D}", "%")
                .replace("{T}", terminal_short)
                .replace("{terminal}", terminal_short)
            )
        else:
            # NEVER — no date scoping, just prefix
            scope_prefix = None  # handled below

        # Extract the part before {seq} to use as DB filter
        # This assumes {seq} is at the end or we can filter by the static part.
        # If {seq} is not at end, 'like' query is harder.
        # Let's assume standard format where we can split by {seq}.

        if "{seq" in prefix_pattern:
            pre_seq, _ = prefix_pattern.split("{seq", 1)
            search_prefix = scope_prefix if scope_prefix else pre_seq
        else:
            search_prefix = prefix_pattern + "-"

        # 3. Retry Loop for Concurrency
        # Use serializable isolation in network mode to prevent two
        # terminals from reading the same max sequence simultaneously.
        max_retries = 5
        for attempt in range(max_retries):
            try:
                db = Database()
                with db.get_session(serializable=True) as session:
                    # Get the last document matching the prefix
                    like_filter = f"{search_prefix}%" if search_prefix else f"{pre_seq}%"
                    last_doc = (
                        session.query(Document)
                        .filter(Document.document_number.like(like_filter))
                        .order_by(desc(Document.document_number))
                        .first()
                    )

                    new_seq = 1
                    if last_doc:
                        current_no = last_doc.document_number
                        # Extract the numeric sequence from the document number
                        compare_prefix = search_prefix if search_prefix else pre_seq
                        if current_no.startswith(compare_prefix):
                            remainder = current_no[len(compare_prefix) :]
                            digits = "".join(filter(str.isdigit, remainder))
                            if digits:
                                new_seq = int(digits) + 1

                    # Render the final document number
                    final_number = prefix_pattern
                    match = _SEQ_RE.search(final_number)
                    if match:
                        fmt = match.group(1) or ""
                        fmt_str = "{" + fmt + "}"
                        seq_str = fmt_str.format(new_seq)
                        final_number = final_number.replace(match.group(0), seq_str)
                    else:
                        final_number = f"{final_number}{new_seq}"

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

                    final_number = f"{prefix}{new_seq:04d}"  # noqa: E231

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
