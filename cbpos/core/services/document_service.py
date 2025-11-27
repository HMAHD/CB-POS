from datetime import datetime
from sqlalchemy import desc
from cbpos.core.database import Database
from cbpos.core.models import Document


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
    }

    @staticmethod
    def generate_number(doc_type: str) -> str:
        """
        Generate the next sequential document number for the given type.
        Format: PREFIX-YEAR-SEQUENCE (e.g., INV-2023-00001)
        """
        prefix = DocumentService.PREFIXES.get(doc_type, "DOC")
        year = datetime.now().year
        prefix_year = f"{prefix}-{year}"

        db = Database()
        with db.get_session() as session:
            # Get the last document of this type for this year
            last_doc = (
                session.query(Document)
                .filter(Document.document_number.like(f"{prefix_year}-%"))
                .order_by(desc(Document.document_number))
                .first()
            )

            if last_doc:
                # Extract sequence part
                try:
                    last_seq_str = last_doc.document_number.split("-")[-1]
                    last_seq = int(last_seq_str)
                    new_seq = last_seq + 1
                except ValueError:
                    # Fallback if format is somehow broken
                    new_seq = 1
            else:
                new_seq = 1

            return "{}-{:05d}".format(prefix_year, new_seq)
