"""Tests for ImportService."""

from decimal import Decimal
from pathlib import Path

import pytest

from cbpos.core.models import Product, Role, User
from cbpos.core.services.import_service import ImportMappingError, ImportService

_counter = 0


@pytest.fixture
def test_user(db_session):
    global _counter
    _counter += 1
    role = Role(name=f"ImportRole_{_counter}", access_level=9)
    user = User(username=f"import_user_{_counter}", pin_hash="hash", role=role)
    db_session.add_all([role, user])
    db_session.flush()
    return user


class TestImportServiceColumnMapping:
    def test_issue_865_selling_and_cost_price_map_correctly(self, db_session, test_user, tmp_path: Path):
        csv_file = tmp_path / "products.csv"
        csv_file.write_text(
            "Barcode,Name,Selling Price,Cost Price,Stock\n8901001,Bread,120.00,85.00,10\n",
            encoding="utf-8",
        )

        service = ImportService()
        result = service.import_products_from_csv(str(csv_file))
        assert result["success"] == 1

        product = db_session.query(Product).filter_by(barcode="8901001").first()
        assert product is not None
        assert product.name_en == "Bread"
        assert product.price == Decimal("120.00")
        assert product.cost == Decimal("85.00")

    def test_issue_865_name_sinhala_does_not_replace_english(self, db_session, tmp_path: Path):
        csv_file = tmp_path / "products.csv"
        csv_file.write_text(
            "Barcode,Name,Name (Sinhala),Selling Price,Cost Price\n8901002,Milk,කිරි,250.00,200.00\n",
            encoding="utf-8",
        )

        service = ImportService()
        result = service.import_products_from_csv(str(csv_file))
        assert result["success"] == 1

        product = db_session.query(Product).filter_by(barcode="8901002").first()
        assert product is not None
        assert product.name_en == "Milk"
        assert product.name_si == "කිරි"

    def test_issue_865_duplicate_mapping_rejected(self, tmp_path: Path):
        csv_file = tmp_path / "products.csv"
        csv_file.write_text(
            "Barcode,Name,Price,Selling Price\n8901003,Tea,100.00,100.00\n",
            encoding="utf-8",
        )

        service = ImportService()
        with pytest.raises(ImportMappingError) as exc_info:
            service.import_products_from_csv(str(csv_file))

        assert exc_info.value.code == "duplicate_column"
        assert exc_info.value.field == "price"

    def test_issue_865_explicit_mapping_honoured(self, db_session, tmp_path: Path):
        csv_file = tmp_path / "products.csv"
        csv_file.write_text(
            "ItemCode,ItemDesc,Retail,BuyRate\n8901004,Sugar,180.00,150.00\n",
            encoding="utf-8",
        )

        service = ImportService()
        mapping = {
            "ItemCode": "barcode",
            "ItemDesc": "name_en",
            "Retail": "price",
            "BuyRate": "cost",
        }
        result = service.import_products_from_csv(str(csv_file), mapping=mapping)
        assert result["success"] == 1

        product = db_session.query(Product).filter_by(barcode="8901004").first()
        assert product is not None
        assert product.barcode == "8901004"
        assert product.name_en == "Sugar"
        assert product.price == Decimal("180.00")
        assert product.cost == Decimal("150.00")
