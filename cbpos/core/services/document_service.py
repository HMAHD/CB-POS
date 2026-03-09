import logging
from datetime import datetime
from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError
from cbpos.core.database import Database
from cbpos.core.models import Document

logger = logging.getLogger(__name__)


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
        import time

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

        # 2. Parse Date Placeholders
        now = datetime.now()
        year_str = now.strftime("%Y")
        month_str = now.strftime("%m")
        day_str = now.strftime("%d")

        # Replace static parts to find the prefix for DB query
        # We need to identify the static prefix part to filter the DB.
        # E.g. INV-2023-{seq:05d} -> Prefix is INV-2023-
        # This is tricky if {seq} is in the middle.
        # Strategy: Render the pattern without seq, but with a placeholder, then split?
        # Simpler Strategy: We assume the pattern generates a string. We need to find the MAX of that string.
        # But if the pattern changes, the sequence might break.
        # Standard approach: Filter by "Prefix" determined by Reset Period.

        # Determine Reset Scope
        if reset_period == "YEARLY":
            # Filter by Year
            # We need to construct a "Like" query that matches the current year's pattern
            # This is complex if the user changes the pattern mid-year.
            # Industrial Standard: The Sequence is usually stored in a separate Sequence Table or we rely on the ID.
            # Given "Offline First" and SQLite, we will try to parse the pattern to extract a prefix.

            # Let's assume the pattern starts with static text or date.
            # We will render the pattern with {seq:05d} replaced by a wildcard or just look for the max ID
            # that matches the rendered date parts.
            pass

        # RENDER DATE PARTS
        prefix_pattern = pattern.replace("{Y}", year_str).replace("{M}", month_str).replace("{D}", day_str)

        # Extract the part before {seq} to use as DB filter
        # This assumes {seq} is at the end or we can filter by the static part.
        # If {seq} is not at end, 'like' query is harder.
        # Let's assume standard format where we can split by {seq}.

        if "{seq" in prefix_pattern:
            pre_seq, post_seq = prefix_pattern.split("{seq", 1)
            # pre_seq might be "INV-2023-"
            # post_seq might be ":05d}"

            # Clean up pre_seq
            search_prefix = pre_seq
        else:
            # Fallback
            search_prefix = prefix_pattern + "-"

        # 3. Retry Loop for Concurrency
        max_retries = 3
        for attempt in range(max_retries):
            try:
                db = Database()
                with db.get_session() as session:
                    # Get the last document matching the prefix
                    last_doc = (
                        session.query(Document)
                        .filter(Document.document_number.like(f"{search_prefix}%"))
                        .order_by(desc(Document.document_number))
                        .first()
                    )

                    new_seq = 1
                    if last_doc:
                        # Extract sequence
                        # Remove prefix from the actual doc number
                        current_no = last_doc.document_number
                        if current_no.startswith(search_prefix):
                            remainder = current_no[len(search_prefix) :]
                            # Extract digits from remainder (it might have suffix)
                            # If pattern was INV-{Y}-{seq:05d}, remainder is 00001
                            # If pattern was INV-{seq}-X, remainder is 00001-X

                            # Simple digit extraction
                            digits = "".join(filter(str.isdigit, remainder))
                            if digits:
                                new_seq = int(digits) + 1

                    # Format the new number
                    # We need to put new_seq into the pattern
                    # pattern has {seq:05d} or similar.
                    # We can use python's format string if we sanitize it.

                    # Re-render pattern with new_seq
                    # We need to handle the format specifier inside {seq...}
                    # Manual replacement of {seq...} with formatted number

                    final_number = prefix_pattern  # Already has Y/M/D replaced, still has {seq:05d}

                    # Find {seq...}
                    import re

                    match = re.search(r"\{seq(:.*?)?\}", final_number)
                    if match:
                        fmt = match.group(1) or ""  # e.g. :05d
                        # Create a format string like "{:05d}"
                        fmt_str = "{" + fmt + "}"
                        seq_str = fmt_str.format(new_seq)
                        final_number = final_number.replace(match.group(0), seq_str)
                    else:
                        # Fallback append
                        final_number = f"{final_number}{new_seq}"

                    # Check if exists (Race condition check)
                    exists = session.query(Document).filter_by(document_number=final_number).first()
                    if not exists:
                        return final_number

                    # Increment sequence and retry within same session
                    new_seq += 1
                    time.sleep(0.05)  # Small backoff

            except IntegrityError:
                # Another transaction inserted the same number concurrently
                logger.warning("Document number collision on attempt %d, retrying...", attempt + 1)
                time.sleep(0.05)
            except Exception as e:
                logger.error("Error generating document number: %s", e)
                if attempt == max_retries - 1:
                    # Fallback to UUID if all fails
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
