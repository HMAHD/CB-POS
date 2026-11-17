"""add claim resolution and supplier RMA fields (Issues #827, #828, #820)

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-11-17 17:00:00.000000
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4c5d6e7f8a9"
down_revision: Union[str, None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_tables = set(insp.get_table_names())

    if "warranty_claims" in existing_tables:
        existing_cols = {c["name"] for c in insp.get_columns("warranty_claims")}

        with op.batch_alter_table("warranty_claims", reflect_kwargs={"resolve_fks": False}) as batch_op:
            if "defective_unit_status" not in existing_cols:
                batch_op.add_column(
                    sa.Column(
                        "defective_unit_status",
                        sa.String(length=30),
                        server_default="HELD",
                        nullable=False,
                    )
                )
                batch_op.create_index(
                    "ix_warranty_claims_defective_unit_status",
                    ["defective_unit_status"],
                )
            if "refund_sale_id" not in existing_cols:
                batch_op.add_column(
                    sa.Column(
                        "refund_sale_id",
                        sa.Integer(),
                        nullable=True,
                    )
                )
                batch_op.create_foreign_key(
                    "fk_warranty_claims_refund_sale_id",
                    "sales",
                    ["refund_sale_id"],
                    ["id"],
                    ondelete="SET NULL",
                )
                batch_op.create_index(
                    "ix_warranty_claims_refund_sale_id",
                    ["refund_sale_id"],
                )
            if "supplier_id" not in existing_cols:
                batch_op.add_column(
                    sa.Column(
                        "supplier_id",
                        sa.Integer(),
                        nullable=True,
                    )
                )
                batch_op.create_foreign_key(
                    "fk_warranty_claims_supplier_id",
                    "suppliers",
                    ["supplier_id"],
                    ["id"],
                    ondelete="RESTRICT",
                )
                batch_op.create_index(
                    "ix_warranty_claims_supplier_id",
                    ["supplier_id"],
                )
            if "supplier_rma_ref" not in existing_cols:
                batch_op.add_column(
                    sa.Column(
                        "supplier_rma_ref",
                        sa.String(length=100),
                        nullable=True,
                    )
                )
            if "sent_to_supplier_at" not in existing_cols:
                batch_op.add_column(
                    sa.Column(
                        "sent_to_supplier_at",
                        sa.DateTime(),
                        nullable=True,
                    )
                )
                batch_op.create_index(
                    "ix_warranty_claims_sent_to_supplier_at",
                    ["sent_to_supplier_at"],
                )
            if "returned_from_supplier_at" not in existing_cols:
                batch_op.add_column(
                    sa.Column(
                        "returned_from_supplier_at",
                        sa.DateTime(),
                        nullable=True,
                    )
                )
            if "supplier_outcome" not in existing_cols:
                batch_op.add_column(
                    sa.Column(
                        "supplier_outcome",
                        sa.String(length=30),
                        nullable=True,
                    )
                )
            if "supplier_credit_amount" not in existing_cols:
                batch_op.add_column(
                    sa.Column(
                        "supplier_credit_amount",
                        sa.Numeric(precision=12, scale=2),
                        server_default="0",
                        nullable=False,
                    )
                )

            # Check constraints
            batch_op.create_check_constraint(
                "ck_warranty_claims_defective_status",
                "defective_unit_status IN ('HELD', 'SENT_TO_SUPPLIER', 'RETURNED_FROM_SUPPLIER', 'SCRAPPED', 'RETURNED_TO_CUSTOMER')",
            )
            batch_op.create_check_constraint(
                "ck_warranty_claims_supplier_outcome",
                "supplier_outcome IS NULL OR supplier_outcome IN ('REPAIRED', 'REPLACED', 'CREDIT_NOTE', 'REJECTED')",
            )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_tables = set(insp.get_table_names())

    if "warranty_claims" in existing_tables:
        existing_cols = {c["name"] for c in insp.get_columns("warranty_claims")}
        existing_checks = {c["name"] for c in insp.get_check_constraints("warranty_claims")}
        existing_indexes = {c["name"] for c in insp.get_indexes("warranty_claims")}

        with op.batch_alter_table("warranty_claims", reflect_kwargs={"resolve_fks": False}) as batch_op:
            if "ck_warranty_claims_supplier_outcome" in existing_checks or conn.dialect.name != "sqlite":
                batch_op.drop_constraint("ck_warranty_claims_supplier_outcome", type_="check")
            if "ck_warranty_claims_defective_status" in existing_checks or conn.dialect.name != "sqlite":
                batch_op.drop_constraint("ck_warranty_claims_defective_status", type_="check")

            if "ix_warranty_claims_sent_to_supplier_at" in existing_indexes:
                batch_op.drop_index("ix_warranty_claims_sent_to_supplier_at")
            if "sent_to_supplier_at" in existing_cols:
                batch_op.drop_column("sent_to_supplier_at")

            if "ix_warranty_claims_supplier_id" in existing_indexes:
                batch_op.drop_index("ix_warranty_claims_supplier_id")
            if "supplier_id" in existing_cols:
                if conn.dialect.name != "sqlite":
                    batch_op.drop_constraint("fk_warranty_claims_supplier_id", type_="foreignkey")
                batch_op.drop_column("supplier_id")

            if "ix_warranty_claims_refund_sale_id" in existing_indexes:
                batch_op.drop_index("ix_warranty_claims_refund_sale_id")
            if "refund_sale_id" in existing_cols:
                if conn.dialect.name != "sqlite":
                    batch_op.drop_constraint("fk_warranty_claims_refund_sale_id", type_="foreignkey")
                batch_op.drop_column("refund_sale_id")

            if "supplier_credit_amount" in existing_cols:
                batch_op.drop_column("supplier_credit_amount")
            if "supplier_outcome" in existing_cols:
                batch_op.drop_column("supplier_outcome")
            if "returned_from_supplier_at" in existing_cols:
                batch_op.drop_column("returned_from_supplier_at")
            if "supplier_rma_ref" in existing_cols:
                batch_op.drop_column("supplier_rma_ref")

            if "ix_warranty_claims_defective_unit_status" in existing_indexes:
                batch_op.drop_index("ix_warranty_claims_defective_unit_status")
            if "defective_unit_status" in existing_cols:
                batch_op.drop_column("defective_unit_status")
