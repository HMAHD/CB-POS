"""Receipt reprint service — handles authorization, document truth, builder dispatch, and audit logging for receipt reprints (#911)."""

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import joinedload

from cbpos.core.constants.permissions import Permissions
from cbpos.core.database import Database
from cbpos.core.models import AuditLog, Sale, SaleItem, User
from cbpos.core.services.permission_service import PermissionService
from cbpos.core.services.receipt_builder import ReceiptBuilder
from cbpos.core.services.refund_service import RefundService
from cbpos.i18n import _t

logger = logging.getLogger(__name__)


@dataclass
class ReprintJob:
    """Represents a validated receipt reprint job ready for spooling."""

    commands: list[dict[str, Any]]
    document_number: str
    is_refund: bool = False
    sale_id: int | None = None

    def __iter__(self):
        return iter(self.commands)

    def __len__(self) -> int:
        return len(self.commands)


class ReceiptReprintService:
    """Service governing receipt reprints with permission checks and document truth (#911)."""

    @classmethod
    def reprint(
        cls,
        sale_id: int,
        user_id: int,
        approver_id: int | None = None,
        config_override: dict[str, Any] | None = None,
    ) -> ReprintJob:
        """Reprint a receipt for the specified sale.

        Enforces:
        - Permission check: effective authorizer (approver or actor) must have sales.reprint.
        - Refuses VOID sales: raises ValueError("reprint_void").
        - Dispatches: refund sales use RefundReceiptBuilder; regular sales use SalesReceiptBuilder with DUPLICATE.
        - Partially refunded sales list their credit note references.
        - Writes exactly one REPRINT_RECEIPT AuditLog row.
        """
        db = Database()
        with db.get_session() as session:
            # 1. Authorisation check
            actor = session.get(User, user_id)
            approver = session.get(User, approver_id) if approver_id else None
            authorizing_user = approver or actor

            if not authorizing_user or not PermissionService.user_has_permission(
                authorizing_user, Permissions.SALES_REPRINT
            ):
                raise PermissionError("permission_denied")

            # 2. Fetch sale with relationships
            sale = (
                session.query(Sale)
                .options(
                    joinedload(Sale.items).joinedload(SaleItem.product),
                    joinedload(Sale.items).joinedload(SaleItem.warranties),
                    joinedload(Sale.warranties),
                    joinedload(Sale.payments),
                    joinedload(Sale.customer),
                    joinedload(Sale.user),
                )
                .filter(Sale.id == sale_id)
                .first()
            )
            if not sale:
                raise ValueError("sale_not_found")

            # 3. Refuse VOID
            if sale.status == "VOID":
                raise ValueError("reprint_void")

            doc_number = sale.document_number or str(sale.id)

            # 4. Check if refund document
            is_refund = bool(
                sale.refund_of_sale_id is not None
                or getattr(sale, "payment_method", "") == "REFUND"
                or doc_number.startswith("CN-")
            )

            if is_refund:
                # Credit note reprint
                commands = ReceiptBuilder.build_refund_receipt(
                    sale=sale,
                    refund_amount=abs(sale.total_amount),
                    authorized_by=sale.user.username if sale.user else "",
                    config_override=config_override,
                    refund_timestamp=sale.date,
                    is_reprint=True,
                )
            else:
                # Regular sale reprint: check partial refund status
                rstate = RefundService.refund_state(sale.id, session=session)
                part_refunded_note = None
                if rstate == "PARTIAL":
                    cn_rows = (
                        session.query(Sale.document_number)
                        .filter(Sale.refund_of_sale_id == sale.id, Sale.status != "VOID")
                        .order_by(Sale.id)
                        .all()
                    )
                    cn_numbers = [r[0] for r in cn_rows if r[0]]
                    if cn_numbers:
                        part_refunded_note = _t("receipt.part_refunded_note", numbers=", ".join(cn_numbers))

                commands = ReceiptBuilder.build_receipt(
                    sale=sale,
                    config_override=config_override,
                    is_reprint=True,
                    part_refunded_note=part_refunded_note,
                )

            # 5. Write AuditLog row
            actor_name = actor.username if actor else str(user_id)
            if approver:
                details = f"Reprinted receipt {doc_number} (Actor: {actor_name}, Approver: {approver.username})"
            else:
                details = f"Reprinted receipt {doc_number} (User: {actor_name})"

            audit = AuditLog(
                user_id=authorizing_user.id,
                action="REPRINT_RECEIPT",
                event_type="TRANSACTION",
                details=details,
            )
            session.add(audit)
            session.commit()

            return ReprintJob(
                commands=commands,
                document_number=doc_number,
                is_refund=is_refund,
                sale_id=sale.id,
            )

    @classmethod
    def reprint_warranty_cards(
        cls,
        sale_id: int,
        user_id: int,
        approver_id: int | None = None,
        config_override: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Reprint warranty cards for the specified sale (#824).

        Enforces:
        - Permission check: authorizer has Permissions.SALES_REPRINT or Permissions.WARRANTY_VIEW.
        - Refuses VOID sales: raises ValueError("reprint_void").
        - Requires warranties on sale: raises ValueError("no_warranties").
        - Builds thermal command list via WarrantyCardBuilder with is_reprint=True.
        - Writes exactly one REPRINT_WARRANTY_CARD AuditLog row.
        """
        db = Database()
        with db.get_session() as session:
            actor = session.get(User, user_id)
            approver = session.get(User, approver_id) if approver_id else None
            authorizing_user = approver or actor

            can_reprint = authorizing_user and (
                PermissionService.user_has_permission(authorizing_user, Permissions.SALES_REPRINT)
                or PermissionService.user_has_permission(authorizing_user, Permissions.WARRANTY_VIEW)
            )
            if not can_reprint:
                raise PermissionError("permission_denied")

            sale = (
                session.query(Sale)
                .options(
                    joinedload(Sale.warranties),
                    joinedload(Sale.customer),
                    joinedload(Sale.user),
                )
                .filter(Sale.id == sale_id)
                .first()
            )
            if not sale:
                raise ValueError("sale_not_found")

            if sale.status == "VOID":
                raise ValueError("reprint_void")

            if not getattr(sale, "warranties", None):
                raise ValueError("no_warranties")

            from cbpos.core.constants.audit import REPRINT_WARRANTY_CARD, WARRANTY_EVENT
            from cbpos.core.services.warranty_card_builder import WarrantyCardBuilder

            commands = WarrantyCardBuilder.build_escpos(
                sale.warranties,
                config_override=config_override,
                is_reprint=True,
            )

            doc_number = sale.document_number or str(sale.id)
            actor_name = actor.username if actor else str(user_id)
            if approver:
                details = f"Reprinted warranty cards for sale {doc_number} ({len(sale.warranties)} units) (Actor: {actor_name}, Approver: {approver.username})"
            else:
                details = f"Reprinted warranty cards for sale {doc_number} ({len(sale.warranties)} units) (User: {actor_name})"

            audit = AuditLog(
                user_id=authorizing_user.id,
                action=REPRINT_WARRANTY_CARD,
                event_type=WARRANTY_EVENT,
                details=details,
            )
            session.add(audit)
            session.commit()

            return commands
