"""Cart autosave service for power-cut safety (Phase 10B.1 / #932)."""

import json
import logging
import threading
from datetime import datetime
from decimal import Decimal

from sqlalchemy import update
from sqlalchemy.orm import Session

from cbpos.core.constants.features import Features
from cbpos.core.database import Database
from cbpos.core.models import SuspendedTransaction
from cbpos.core.services.feature_flags import feature_visible
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
    def get_next_generation(cls, terminal_id: str) -> int:
        """Return the next strictly increasing generation counter for a terminal,
        guaranteeing it exceeds any persisted revision in the database.
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
            curr = cls._active_generations.get(terminal_id, 0)
            next_gen = max(curr, persisted_revision) + 1
            cls._active_generations[terminal_id] = next_gen
            return next_gen

    @classmethod
    def get_active_generation(cls, terminal_id: str) -> int:
        """Return current active generation counter or initialize from persisted revision."""
        with cls._lock:
            if terminal_id in cls._active_generations:
                return cls._active_generations[terminal_id]
        return cls.get_next_generation(terminal_id)

    @classmethod
    def advance_generation(cls, terminal_id: str) -> int:
        """Increment and return the new active generation counter for a terminal."""
        return cls.get_next_generation(terminal_id)

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
            active_gen = cls._active_generations.get(terminal_id, 0)
            if generation < active_gen:
                logger.debug(
                    "Dropping stale autosave for %s (write gen %s < in-memory gen %s)",
                    terminal_id,
                    generation,
                    active_gen,
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
                with cls._lock:
                    cls._active_generations[terminal_id] = max(cls._active_generations.get(terminal_id, 0), generation)
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
                    return None

                row_id = row.id
                raw_data = row.data
                row_timestamp = row.timestamp
                row_customer_id = row.customer_id

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
                "customer_id": row_customer_id,
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
    def delete_autosave_in_session(cls, session: Session, terminal_id: str) -> None:
        """Atomically tombstone autosave for terminal_id within an existing DB transaction.

        Sets data=None and advances revision so in-flight writes cannot overwrite or resurrect it.
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
        new_rev = 1
        if row is not None:
            new_rev = (row.revision or 0) + 1
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
                revision=1,
                timestamp=datetime.now(),
            )
            session.add(row)

        with cls._lock:
            cls._active_generations[terminal_id] = max(cls._active_generations.get(terminal_id, 0), new_rev)

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
    def restore_autosave(cls, terminal_id: str, cart_service) -> RecallResult:
        """Restore autosaved cart for terminal_id with full fidelity and tombstone row."""
        if not terminal_id or not terminal_id.strip():
            return RecallResult(ok=False)

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
                row_id = row.id

            # Delegate to SuspendedTransactionService.recall_bill for full-fidelity restoration
            res = SuspendedTransactionService.recall_bill(row_id, cart_service)
            # Tombstone the autosave record now that it is recalled
            cls.discard_autosave(terminal_id)
            return res
        except Exception as e:
            logger.error("Failed to restore autosave for terminal %s: %s", terminal_id, e)
            return RecallResult(ok=False)

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
