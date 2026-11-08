"""sale_tax_snapshot: store tax facts and category exemptions (Phase 6 #810, #797, #831)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-11-08 12:10:00.000000

Adds stored tax facts to sales and sale_items for historical document truth,
and adds sscl_exempt to categories for independent SSCL exemption tracking (D9).
Historical cost and rates are approximated by current values at upgrade time.
Never recomputes stored tax_vat, tax_sscl, or net_revenue.
"""

import json
import logging
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op
from cbpos.config import Config

logger = logging.getLogger(__name__)

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _load_settings_snapshot() -> dict:
    """Read tax rates and registration from settings.json directly without ConfigService."""
    settings_file = Config.DATA_DIR / "settings.json"
    if settings_file.exists():
        try:
            with open(settings_file, encoding="utf-8") as f:
                content = json.load(f)
            if isinstance(content, dict):
                return content
        except Exception as e:
            logger.warning("Could not read settings.json during migration: %s", e)
    return {}


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    # 1. Update categories: add sscl_exempt
    if "categories" in existing_tables:
        existing_cols = {col["name"] for col in insp.get_columns("categories")}
        with op.batch_alter_table("categories", schema=None) as batch_op:
            if "sscl_exempt" not in existing_cols:
                batch_op.add_column(
                    sa.Column(
                        "sscl_exempt",
                        sa.Boolean(),
                        nullable=False,
                        server_default=sa.false(),
                    )
                )

    # 2. Update sale_items: add vat_exempt, sscl_exempt, unit_cost
    if "sale_items" in existing_tables:
        existing_cols = {col["name"] for col in insp.get_columns("sale_items")}
        with op.batch_alter_table("sale_items", schema=None) as batch_op:
            if "vat_exempt" not in existing_cols:
                batch_op.add_column(sa.Column("vat_exempt", sa.Boolean(), nullable=True))
            if "sscl_exempt" not in existing_cols:
                batch_op.add_column(sa.Column("sscl_exempt", sa.Boolean(), nullable=True))
            if "unit_cost" not in existing_cols:
                batch_op.add_column(sa.Column("unit_cost", sa.Numeric(precision=12, scale=2), nullable=True))

    # 3. Update sales: add rates, registration flags, and tax amounts
    if "sales" in existing_tables:
        existing_cols = {col["name"] for col in insp.get_columns("sales")}
        with op.batch_alter_table("sales", schema=None) as batch_op:
            if "vat_rate" not in existing_cols:
                batch_op.add_column(sa.Column("vat_rate", sa.Numeric(precision=5, scale=2), nullable=True))
            if "sscl_rate" not in existing_cols:
                batch_op.add_column(sa.Column("sscl_rate", sa.Numeric(precision=5, scale=2), nullable=True))
            if "sscl_turnover_pct" not in existing_cols:
                batch_op.add_column(sa.Column("sscl_turnover_pct", sa.Numeric(precision=5, scale=2), nullable=True))
            if "vat_registered" not in existing_cols:
                batch_op.add_column(sa.Column("vat_registered", sa.Boolean(), nullable=True))
            if "sscl_registered" not in existing_cols:
                batch_op.add_column(sa.Column("sscl_registered", sa.Boolean(), nullable=True))
            if "taxable_amount" not in existing_cols:
                batch_op.add_column(sa.Column("taxable_amount", sa.Numeric(precision=12, scale=2), nullable=True))
            if "vat_exempt_amount" not in existing_cols:
                batch_op.add_column(sa.Column("vat_exempt_amount", sa.Numeric(precision=12, scale=2), nullable=True))
            if "sscl_base" not in existing_cols:
                batch_op.add_column(sa.Column("sscl_base", sa.Numeric(precision=12, scale=2), nullable=True))

    # 4. Backfill historical data from settings.json and product costs
    settings = _load_settings_snapshot()
    vat_rate = float(settings.get("tax_vat_rate", 18.0))
    sscl_rate = float(settings.get("tax_sscl_rate", 2.5))
    sscl_turnover_pct = float(settings.get("tax_sscl_turnover_pct", 50.0))
    vat_registered = bool(settings.get("vat_registered", False))
    sscl_registered = bool(settings.get("sscl_registered", vat_registered))

    if "sales" in existing_tables:
        bind.execute(
            sa.text(
                """
                UPDATE sales
                SET vat_rate = :vat_rate,
                    sscl_rate = :sscl_rate,
                    sscl_turnover_pct = :sscl_turnover_pct,
                    vat_registered = :vat_registered,
                    sscl_registered = :sscl_registered,
                    vat_exempt_amount = 0.00,
                    taxable_amount = CASE
                        WHEN tax_vat IS NOT NULL AND tax_vat != 0 THEN total_amount
                        ELSE 0.00
                    END,
                    sscl_base = CASE
                        WHEN tax_sscl IS NOT NULL AND tax_sscl != 0 THEN
                            CASE
                                WHEN tax_vat IS NOT NULL AND tax_vat != 0 THEN
                                    ROUND(total_amount / (1.0 + (:vat_rate / 100.0)), 2)
                                ELSE total_amount
                            END
                        ELSE 0.00
                    END
                WHERE vat_rate IS NULL
                """
            ),
            {
                "vat_rate": vat_rate,
                "sscl_rate": sscl_rate,
                "sscl_turnover_pct": sscl_turnover_pct,
                "vat_registered": vat_registered,
                "sscl_registered": sscl_registered,
            },
        )

    if "sale_items" in existing_tables and "products" in existing_tables:
        bind.execute(
            sa.text(
                """
                UPDATE sale_items
                SET unit_cost = (
                    SELECT COALESCE(products.cost, 0.00)
                    FROM products
                    WHERE products.id = sale_items.product_id
                )
                WHERE unit_cost IS NULL
                """
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    if "sales" in existing_tables:
        existing_cols = {col["name"] for col in insp.get_columns("sales")}
        with op.batch_alter_table("sales", schema=None) as batch_op:
            for col_name in [
                "sscl_base",
                "vat_exempt_amount",
                "taxable_amount",
                "sscl_registered",
                "vat_registered",
                "sscl_turnover_pct",
                "sscl_rate",
                "vat_rate",
            ]:
                if col_name in existing_cols:
                    batch_op.drop_column(col_name)

    if "sale_items" in existing_tables:
        existing_cols = {col["name"] for col in insp.get_columns("sale_items")}
        with op.batch_alter_table("sale_items", schema=None) as batch_op:
            for col_name in ["unit_cost", "sscl_exempt", "vat_exempt"]:
                if col_name in existing_cols:
                    batch_op.drop_column(col_name)

    if "categories" in existing_tables:
        existing_cols = {col["name"] for col in insp.get_columns("categories")}
        with op.batch_alter_table("categories", schema=None) as batch_op:
            if "sscl_exempt" in existing_cols:
                batch_op.drop_column("sscl_exempt")
