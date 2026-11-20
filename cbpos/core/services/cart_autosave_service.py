"""Cart autosave service for power-cut safety (Phase 10B.1 / #932)."""

import json
import logging
import threading
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, DecimalException

from sqlalchemy import update
from sqlalchemy.orm import Session

from cbpos.core.constants.features import Features
from cbpos.core.database import Database
from cbpos.core.models import SuspendedTransaction
from cbpos.core.services.feature_flags import feature_visible
from cbpos.core.services.suspended_transaction_service import (
    RecallResult,
    serialize_cart_v2,
)

logger = logging.getLogger(__name__)


class CartAutosaveService:
    """Manages background autosaving, isolation, and recovery of open carts.

    Guarantees thread-safety, generational write dropping, atomic deletion on sales,
    and fail-closed behavior on corrupted payloads.
    """

    _lock = threading.RLock()
    _issued_generations: dict[str, int] = {}

    @classmethod
    def reset_registry(cls) -> None:
        """Reset generation registry (useful for testing)."""
        with cls._lock:
            cls._issued_generations.clear()

    @classmethod
    def issue_generation(cls, terminal_id: str) -> int:
        """Return the next strictly increasing generation counter for a terminal purely in-memory.

        Guarantees zero database queries on the Qt UI thread.
        """
        if not terminal_id or not terminal_id.strip():
            return 1

        with cls._lock:
            curr = cls._issued_generations.get(terminal_id, 0)
            next_gen = curr + 1
            cls._issued_generations[terminal_id] = next_gen
            return next_gen

    @classmethod
    def get_issued_high_watermark(cls, terminal_id: str) -> int:
        """Return the highest generation counter issued in this process for a terminal."""
        with cls._lock:
            return cls._issued_generations.get(terminal_id, 0)

    @classmethod
    def sync_baseline_generation(cls, terminal_id: str, baseline_revision: int) -> None:
        """Ensure issued generation watermark is at least equal to persisted baseline revision."""
        if not terminal_id:
            return
        with cls._lock:
            curr = cls._issued_generations.get(terminal_id, 0)
            if baseline_revision > curr:
                cls._issued_generations[terminal_id] = baseline_revision

    @classmethod
    def get_active_generation(cls, terminal_id: str) -> int:
        """Return current active generation counter without incrementing."""
        with cls._lock:
            return cls._issued_generations.get(terminal_id, 0)

    @classmethod
    def advance_generation(cls, terminal_id: str) -> int:
        """Increment and return the new active generation counter for a terminal (zero DB queries)."""
        return cls.issue_generation(terminal_id)

    @classmethod
    def get_next_generation(cls, terminal_id: str) -> int:
        """Return the next strictly increasing generation counter for a terminal,
        guaranteeing it exceeds any persisted revision in the database.
        (Safe for startup/background initialization; UI thread should use issue_generation).
        """
        if not terminal_id or not terminal_id.strip():
            return 1

        persisted_revision = 0
        try:
            db = Database()
            with db.get_session() as session:
                row = (
                    session.query(SuspendedTransaction)
                    .filter(
                        SuspendedTransaction.is_autosave.is_(True),
                        SuspendedTransaction.terminal_id == terminal_id,
                    )
                    .first()
                )
                if row is not None:
                    persisted_revision = row.revision or 0
        except Exception as e:
            logger.debug("Failed to read persisted revision for %s: %s", terminal_id, e)

        with cls._lock:
            curr = cls._issued_generations.get(terminal_id, 0)
            next_gen = max(curr, persisted_revision) + 1
            cls._issued_generations[terminal_id] = next_gen
            return next_gen

    @classmethod
    def snapshot_cart(cls, cart_service) -> dict | None:
        """Capture a thread-safe snapshot of the cart on the UI thread."""
        try:
            json_data, customer_id = serialize_cart_v2(cart_service)
            return {
                "json_data": json_data,
                "customer_id": customer_id,
            }
        except Exception as e:
            logger.debug("Failed to snapshot cart: %s", e)
            return None

    @classmethod
    def save(cls, snapshot: dict, terminal_id: str, generation: int) -> bool:
        """Persist cart snapshot for terminal_id if generation is active and feature enabled.

        Does NOT hold a process lock across DB I/O. Uses database revision checks
        and atomic transactions to serialize persistence without thread deadlocks.
        """
        if not terminal_id or not terminal_id.strip():
            logger.warning("Autosave save rejected: terminal_id is required")
            return False

        # In-memory fast pre-check: drop if already superseded in this process
        with cls._lock:
            watermark = cls._issued_generations.get(terminal_id, 0)
            if generation < watermark:
                logger.debug(
                    "Dropping stale autosave for %s (write gen %s < in-memory watermark %s)",
                    terminal_id,
                    generation,
                    watermark,
                )
                return False

        # Database persistence without holding Python _lock
        db = Database()
        try:
            with db.get_session() as session:
                # 1. Check feature flag inside the DB transaction (Defect 6)
                if not feature_visible(Features.POWER_CUT_AUTOSAVE):
                    logger.debug("Autosave save rejected: feature flag POWER_CUT_AUTOSAVE is disabled")
                    return False

                row = (
                    session.query(SuspendedTransaction)
                    .filter(
                        SuspendedTransaction.is_autosave.is_(True),
                        SuspendedTransaction.terminal_id == terminal_id,
                    )
                    .first()
                )

                if row is not None:
                    # 2. Check monotonic revision (Defect 1)
                    if generation <= (row.revision or 0):
                        logger.debug(
                            "Dropping stale autosave for %s (write gen %s <= persisted revision %s)",
                            terminal_id,
                            generation,
                            row.revision,
                        )
                        return False

                    row.data = snapshot["json_data"]
                    row.customer_id = snapshot.get("customer_id")
                    row.timestamp = datetime.now()
                    row.revision = generation
                else:
                    row = SuspendedTransaction(
                        is_autosave=True,
                        terminal_id=terminal_id,
                        data=snapshot["json_data"],
                        customer_id=snapshot.get("customer_id"),
                        revision=generation,
                        timestamp=datetime.now(),
                    )
                    session.add(row)

                session.commit()

                # Update in-memory active generation tracking
                cls.sync_baseline_generation(terminal_id, generation)
                return True
        except Exception as e:
            logger.error("Failed to save autosave for terminal %s: %s", terminal_id, e)
            return False

    @classmethod
    def get_autosave_summary(cls, terminal_id: str) -> dict | None:
        """Retrieve and parse the autosaved cart summary for terminal_id.

        Fails safely on corrupted JSON by logging a warning, purging the bad row,
        and returning None. Returns None if row has no active data (tombstone).
        """
        if not terminal_id or not terminal_id.strip():
            return None

        db = Database()
        try:
            with db.get_session() as session:
                row = (
                    session.query(SuspendedTransaction)
                    .filter(
                        SuspendedTransaction.is_autosave.is_(True),
                        SuspendedTransaction.terminal_id == terminal_id,
                    )
                    .first()
                )

                if row is None or row.data is None or not row.data.strip():
                    if row is not None and row.revision:
                        cls.sync_baseline_generation(terminal_id, row.revision)
                    return None

                row_id = row.id
                raw_data = row.data
                row_timestamp = row.timestamp
                row_customer_id = row.customer_id
                row_revision = row.revision or 0

            cls.sync_baseline_generation(terminal_id, row_revision)

            payload = json.loads(raw_data)
            if not isinstance(payload, dict):
                raise ValueError("Autosave payload is not a valid JSON dictionary")

            lines = payload.get("lines")
            if not isinstance(lines, list):
                raise ValueError("Autosave payload 'lines' must be a list")

            for item in lines:
                if not isinstance(item, dict):
                    raise ValueError("Autosave line item must be a dictionary")

            item_count = len(lines)
            total_qty = sum(Decimal(str(item.get("qty", "0"))) for item in lines)

            total_dec = Decimal("0.00")
            if "totals" in payload:
                totals_dict = payload["totals"]
                if not isinstance(totals_dict, dict) or "final_total" not in totals_dict:
                    raise ValueError("Autosave totals must be a dictionary with 'final_total'")
                total_dec = Decimal(str(totals_dict["final_total"]))
            else:
                total_dec = sum(
                    Decimal(str(item.get("qty", "0"))) * Decimal(str(item.get("unit_price", "0"))) for item in lines
                )

            return {
                "id": row_id,
                "terminal_id": terminal_id,
                "customer_id": row_customer_id,
                "item_count": item_count,
                "total_qty": total_qty,
                "total": total_dec,
                "timestamp": row_timestamp,
                "raw_payload": payload,
            }
        except (json.JSONDecodeError, KeyError, TypeError, ValueError, DecimalException) as e:
            logger.warning("Corrupt autosave payload on terminal %s, purging: %s", terminal_id, e)
            cls.discard_autosave(terminal_id)
            return None
        except Exception as e:
            logger.error("Error retrieving autosave for terminal %s: %s", terminal_id, e)
            return None

    @classmethod
    def delete_autosave_in_session(cls, session: Session, terminal_id: str) -> None:
        """Atomically tombstone autosave for terminal_id within an existing DB transaction.

        Sets data=None and advances revision to exceed any issued in-memory watermark
        so in-flight writes cannot overwrite or resurrect it.
        Does NOT acquire Python _lock while holding DB transaction, avoiding lock inversion.
        """
        if not terminal_id or not terminal_id.strip():
            return

        row = (
            session.query(SuspendedTransaction)
            .filter(
                SuspendedTransaction.is_autosave.is_(True),
                SuspendedTransaction.terminal_id == terminal_id,
            )
            .first()
        )
        watermark = cls.get_issued_high_watermark(terminal_id)
        current_rev = (row.revision or 0) if row is not None else 0
        new_rev = max(current_rev, watermark) + 1

        if row is not None:
            row.data = None
            row.customer_id = None
            row.revision = new_rev
            row.timestamp = datetime.now()
        else:
            # Insert a tombstone row so any concurrent/subsequent in-flight worker with an older gen is dropped
            row = SuspendedTransaction(
                is_autosave=True,
                terminal_id=terminal_id,
                data=None,
                customer_id=None,
                revision=new_rev,
                timestamp=datetime.now(),
            )
            session.add(row)

        cls.sync_baseline_generation(terminal_id, new_rev)

    @classmethod
    def discard_autosave(cls, terminal_id: str) -> bool:
        """Purge the autosave row for terminal_id and advance its generation/tombstone."""
        if not terminal_id or not terminal_id.strip():
            return False

        db = Database()
        try:
            with db.get_session() as session:
                cls.delete_autosave_in_session(session, terminal_id)
                session.commit()
            return True
        except Exception as e:
            logger.error("Failed to discard autosave for terminal %s: %s", terminal_id, e)
            return False

    @classmethod
    def invalidate_and_delete(cls, terminal_id: str) -> None:
        """Advance generation and tombstone autosave row to invalidate in-flight saves."""
        cls.discard_autosave(terminal_id)

    @classmethod
    def restore_and_consume(cls, terminal_id: str, cart_service) -> RecallResult:
        """Atomically restore autosaved cart for terminal_id with full fidelity and tombstone row.

        Guarantees:
        - If replay succeeds: row is tombstoned, transaction committed, RecallResult(ok=True).
        - If replay fails: cart state is preserved/reverted, DB transaction rolled back,
          autosave row remains untouched and restorable, RecallResult(ok=False).
        """
        if not terminal_id or not terminal_id.strip():
            return RecallResult(ok=False)

        from cbpos.core.models import Product
        from cbpos.core.services.customer_service import CustomerService
        from cbpos.core.services.product_service import ProductService
        from cbpos.core.utils.formatters import format_currency
        from cbpos.i18n import _t

        cart_backup = {
            "items": [dict(it) for it in cart_service.items],
            "customer": cart_service.get_customer(),
            "cart_discount_type": getattr(cart_service, "cart_discount_type", "NONE"),
            "cart_discount_value": getattr(cart_service, "cart_discount_value", Decimal("0.00")),
        }

        db = Database()
        try:
            with db.get_session() as session:
                row = (
                    session.query(SuspendedTransaction)
                    .filter(
                        SuspendedTransaction.is_autosave.is_(True),
                        SuspendedTransaction.terminal_id == terminal_id,
                    )
                    .first()
                )
                if not row or not row.data or not row.data.strip():
                    return RecallResult(ok=False)

                raw_data = row.data
                customer_id = row.customer_id

                try:
                    payload = json.loads(raw_data)
                    if not isinstance(payload, dict):
                        raise ValueError("Payload not a dictionary")
                except Exception as parse_err:
                    logger.warning("Corrupt autosave payload during restore on %s, purging: %s", terminal_id, parse_err)
                    cls.delete_autosave_in_session(session, terminal_id)
                    session.commit()
                    return RecallResult(ok=False)

                notices: list[str] = []

                # Clear cart before restoration attempt
                cart_service.clear()

                customer = None
                if customer_id:
                    customer = CustomerService().get_customer(customer_id)
                    cart_service.set_customer(customer)

                if payload.get("v") == 2:
                    lines = payload.get("lines", [])
                    restored_line_ids: set[str] = set()
                    for line in lines:
                        product_id = line.get("product_id")
                        barcode = line.get("barcode")
                        product = None
                        if product_id:
                            product = session.get(Product, product_id)
                        if (not product or not product.is_active) and barcode:
                            product = ProductService.get_by_barcode(barcode)

                        if not product or not product.is_active:
                            name = (product.name_en if product else None) or barcode or f"Item #{product_id}"
                            notices.append(_t("orders.recall_item_missing", name=name))
                            continue

                        line_id = line.get("line_id")
                        covered_line_id = line.get("covered_line_id")
                        if covered_line_id and covered_line_id not in restored_line_ids:
                            notices.append(
                                _t(
                                    "orders.recall_plan_missing_covered_item",
                                    default=f"Extended warranty plan for missing item was removed: {product.name_en}",
                                    plan=product.name_en,
                                )
                            )
                            continue

                        qty = Decimal(str(line.get("qty", "1.000"))).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
                        cart_service.add_item(product, qty, covered_line_id=covered_line_id, line_id=line_id)
                        if line_id:
                            restored_line_ids.add(line_id)
                        line_idx = len(cart_service.items) - 1
                        if line.get("serials") is not None:
                            cart_service.items[line_idx]["serials"] = list(line.get("serials"))

                        held_unit = Decimal(str(line.get("unit_price", product.price)))
                        held_orig = Decimal(str(line.get("original_price", product.price)))
                        current_orig = product.price
                        if held_orig != current_orig and not line.get("is_manual_price"):
                            notices.append(
                                _t(
                                    "orders.recall_price_changed",
                                    name=product.name_en,
                                    new=format_currency(current_orig),
                                    old=format_currency(held_orig),
                                )
                            )

                        if line.get("is_manual_price"):
                            cart_service.restore_line_override(
                                line_idx, held_unit, approved_by=line.get("override_approved_by")
                            )
                        elif held_unit != cart_service.items[line_idx]["unit_price"]:
                            cart_service.items[line_idx]["unit_price"] = held_unit
                            cart_service.items[line_idx]["original_price"] = held_orig
                            cart_service._recalculate_line(cart_service.items[line_idx])

                        disc_type = line.get("discount_type", "NONE")
                        disc_val = Decimal(str(line.get("discount_value", "0.00")))
                        if disc_type != "NONE" and disc_val > Decimal("0.00"):
                            cart_service.restore_line_discount(line_idx, disc_type, disc_val)

                        note = line.get("notes") or line.get("note")
                        if note:
                            cart_service.set_line_note(line_idx, note)

                    cart_info = payload.get("cart", {})
                    cart_disc_type = cart_info.get("discount_type", "NONE")
                    cart_disc_val = Decimal(str(cart_info.get("discount_value", "0.00")))
                    if cart_disc_type != "NONE" and cart_disc_val > Decimal("0.00"):
                        cart_service.restore_cart_discount(cart_disc_type, cart_disc_val)
                else:
                    items_data = payload if isinstance(payload, list) else []
                    for item in items_data:
                        product = ProductService.get_by_barcode(item["barcode"])
                        if product and product.is_active:
                            cart_service.add_item(
                                product,
                                Decimal(str(item["qty"])).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
                            )
                        elif product and not product.is_active:
                            notices.append(_t("orders.recall_item_missing", name=product.name_en))
                        else:
                            notices.append(_t("orders.recall_item_missing", name=item.get("barcode", "Unknown")))

                # Replay succeeded! Tombstone autosave row in the SAME transaction
                cls.delete_autosave_in_session(session, terminal_id)
                session.commit()
                return RecallResult(ok=True, notices=notices)

        except Exception as e:
            logger.error("Failed to restore autosave for terminal %s: %s", terminal_id, e)
            # Rollback cart to clean pre-restore state
            cart_service.clear()
            for it in cart_backup["items"]:
                cart_service.items.append(dict(it))
            cart_service.set_customer(cart_backup["customer"])
            if hasattr(cart_service, "restore_cart_discount"):
                cart_service.restore_cart_discount(
                    cart_backup["cart_discount_type"], cart_backup["cart_discount_value"]
                )
            return RecallResult(ok=False)

    @classmethod
    def restore_autosave(cls, terminal_id: str, cart_service) -> RecallResult:
        """Alias delegating to restore_and_consume."""
        return cls.restore_and_consume(terminal_id, cart_service)

    @classmethod
    def has_autosave(cls, terminal_id: str) -> bool:
        """Return True if an autosaved cart exists for terminal_id."""
        return cls.get_autosave_summary(terminal_id) is not None

    @classmethod
    def delete_all_autosaves_in_session(cls, session: Session) -> int:
        """Tombstone all autosaved rows across all terminals inside an active session."""
        stmt = (
            update(SuspendedTransaction)
            .where(SuspendedTransaction.is_autosave.is_(True))
            .values(
                data=None,
                customer_id=None,
                revision=SuspendedTransaction.revision + 1,
                timestamp=datetime.now(),
            )
        )
        res = session.execute(stmt)
        with cls._lock:
            cls.reset_registry()
        return res.rowcount or 0

    @classmethod
    def delete_all_autosaves(cls) -> int:
        """Tombstone all autosaved rows across all terminals (e.g. when feature flag disabled)."""
        db = Database()
        with db.get_session() as session:
            count = cls.delete_all_autosaves_in_session(session)
            session.commit()
            return count
