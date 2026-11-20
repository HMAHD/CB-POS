"""Cart autosave service for power-cut safety (Phase 10B.1 / #932)."""

import json
import logging
import threading
from datetime import datetime
from decimal import Decimal

from sqlalchemy import delete
from sqlalchemy.orm import Session

from cbpos.core.database import Database
from cbpos.core.models import SuspendedTransaction
from cbpos.core.services.suspended_transaction_service import (
    RecallResult,
    SuspendedTransactionService,
    serialize_cart_v2,
)

logger = logging.getLogger(__name__)


class CartAutosaveService:
    """Manages background autosaving, isolation, and recovery of open carts.

    Guarantees thread-safety, generational write dropping, atomic deletion on sales,
    and fail-closed behavior on corrupted payloads.
    """

    _lock = threading.RLock()
    _active_generations: dict[str, int] = {}

    @classmethod
    def reset_registry(cls) -> None:
        """Reset generation registry (useful for testing)."""
        with cls._lock:
            cls._active_generations.clear()

    @classmethod
    def get_active_generation(cls, terminal_id: str) -> int:
        """Return the current active generation counter for a terminal."""
        with cls._lock:
            return cls._active_generations.setdefault(terminal_id, 1)

    @classmethod
    def advance_generation(cls, terminal_id: str) -> int:
        """Increment and return the new active generation counter for a terminal."""
        with cls._lock:
            current = cls._active_generations.get(terminal_id, 0)
            cls._active_generations[terminal_id] = current + 1
            return cls._active_generations[terminal_id]

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
        """Persist cart snapshot for terminal_id if generation is active.

        Executes under _lock to guarantee that stale or superseded writes cannot
        overwrite newer state or resurrect a cleared/completed cart.
        """
        if not terminal_id or not terminal_id.strip():
            logger.warning("Autosave save rejected: terminal_id is required")
            return False

        with cls._lock:
            active_gen = cls.get_active_generation(terminal_id)
            if generation < active_gen:
                logger.debug(
                    "Dropping stale autosave for %s (write gen %s < active gen %s)",
                    terminal_id,
                    generation,
                    active_gen,
                )
                return False

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

                    if row is not None:
                        row.data = snapshot["json_data"]
                        row.customer_id = snapshot.get("customer_id")
                        row.timestamp = datetime.now()
                    else:
                        row = SuspendedTransaction(
                            is_autosave=True,
                            terminal_id=terminal_id,
                            data=snapshot["json_data"],
                            customer_id=snapshot.get("customer_id"),
                        )
                        session.add(row)

                    session.commit()
                    return True
            except Exception as e:
                logger.error("Failed to save autosave for terminal %s: %s", terminal_id, e)
                return False

    @classmethod
    def get_autosave_summary(cls, terminal_id: str) -> dict | None:
        """Retrieve and parse the autosaved cart summary for terminal_id.

        Fails safely on corrupted JSON by logging a warning, purging the bad row,
        and returning None.
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

                if row is None:
                    return None

                row_id = row.id
                raw_data = row.data
                row_timestamp = row.timestamp

            payload = json.loads(raw_data)
            if not isinstance(payload, dict):
                raise ValueError("Autosave payload is not a valid JSON dictionary")

            lines = payload.get("lines", [])
            item_count = len(lines)
            total_qty = sum(Decimal(str(item.get("qty", "0"))) for item in lines)

            total_dec = Decimal("0.00")
            if "totals" in payload and "final_total" in payload["totals"]:
                total_dec = Decimal(str(payload["totals"]["final_total"]))
            else:
                total_dec = sum(
                    Decimal(str(item.get("qty", "0"))) * Decimal(str(item.get("unit_price", "0"))) for item in lines
                )

            return {
                "id": row_id,
                "terminal_id": terminal_id,
                "item_count": item_count,
                "total_qty": total_qty,
                "total": total_dec,
                "timestamp": row_timestamp,
                "raw_payload": payload,
            }
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            logger.warning("Corrupt autosave payload on terminal %s, purging: %s", terminal_id, e)
            cls.discard_autosave(terminal_id)
            return None
        except Exception as e:
            logger.error("Error retrieving autosave for terminal %s: %s", terminal_id, e)
            return None

    @classmethod
    def discard_autosave(cls, terminal_id: str) -> bool:
        """Purge the autosave row for terminal_id and advance its generation."""
        if not terminal_id or not terminal_id.strip():
            return False

        with cls._lock:
            cls.advance_generation(terminal_id)
            db = Database()
            try:
                with db.get_session() as session:
                    stmt = delete(SuspendedTransaction).where(
                        SuspendedTransaction.is_autosave.is_(True),
                        SuspendedTransaction.terminal_id == terminal_id,
                    )
                    session.execute(stmt)
                    session.commit()
                return True
            except Exception as e:
                logger.error("Failed to discard autosave for terminal %s: %s", terminal_id, e)
                return False

    @classmethod
    def invalidate_and_delete(cls, terminal_id: str) -> None:
        """Advance generation and delete autosave row to invalidate in-flight saves."""
        cls.discard_autosave(terminal_id)

    @classmethod
    def delete_autosave_in_session(cls, session: Session, terminal_id: str) -> None:
        """Atomically delete autosave for terminal_id within an existing DB transaction."""
        if not terminal_id or not terminal_id.strip():
            return

        with cls._lock:
            cls.advance_generation(terminal_id)
            stmt = delete(SuspendedTransaction).where(
                SuspendedTransaction.is_autosave.is_(True),
                SuspendedTransaction.terminal_id == terminal_id,
            )
            session.execute(stmt)

    @classmethod
    def restore_autosave(cls, terminal_id: str, cart_service) -> RecallResult:
        """Restore autosaved cart for terminal_id with full fidelity and delete row."""
        if not terminal_id or not terminal_id.strip():
            return RecallResult(ok=False)

        with cls._lock:
            cls.advance_generation(terminal_id)
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
                    if not row:
                        return RecallResult(ok=False)
                    row_id = row.id

                # Delegate to SuspendedTransactionService.recall_bill for full-fidelity restoration
                return SuspendedTransactionService.recall_bill(row_id, cart_service)
            except Exception as e:
                logger.error("Failed to restore autosave for terminal %s: %s", terminal_id, e)
                return RecallResult(ok=False)

    @classmethod
    def has_autosave(cls, terminal_id: str) -> bool:
        """Return True if an autosaved cart exists for terminal_id."""
        return cls.get_autosave_summary(terminal_id) is not None

    @classmethod
    def delete_all_autosaves_in_session(cls, session: Session) -> int:
        """Delete all autosaved rows across all terminals inside an active session."""
        with cls._lock:
            cls.reset_registry()
            stmt = delete(SuspendedTransaction).where(SuspendedTransaction.is_autosave.is_(True))
            res = session.execute(stmt)
            return res.rowcount or 0

    @classmethod
    def delete_all_autosaves(cls) -> int:
        """Delete all autosaved rows across all terminals (e.g. when feature flag disabled)."""
        db = Database()
        with db.get_session() as session:
            count = cls.delete_all_autosaves_in_session(session)
            session.commit()
            return count
