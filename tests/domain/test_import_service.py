"""Tests for ImportService."""

from decimal import Decimal
from pathlib import Path

import pytest

from cbpos.core.models import Product, Role, User
from cbpos.core.services.import_service import ImportError_, ImportMappingError, ImportService

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


class TestImportServiceEncodingAndPaths:
    def test_issue_900_cp1252_file_imports_all_rows(self, db_session, test_user, tmp_path: Path):
        csv_file = tmp_path / "ansi_products.csv"
        # cp1252 encoded file with Café (0xE9 is é in cp1252, invalid in utf-8)
        content_bytes = (
            b"Barcode,Name,Selling Price,Cost Price\n"
            b"9001001,Caf\xe9 Latte,250.00,180.00\n"
            b"9001002,Croissant,150.00,90.00\n"
        )
        csv_file.write_bytes(content_bytes)

        service = ImportService()
        result = service.import_products_from_csv(str(csv_file))

        assert result["success"] == 2
        p1 = db_session.query(Product).filter_by(barcode="9001001").first()
        assert p1 is not None
        assert p1.name_en == "Café Latte"

        p2 = db_session.query(Product).filter_by(barcode="9001002").first()
        assert p2 is not None
        assert p2.name_en == "Croissant"

    def test_issue_900_path_outside_home_imports(self, db_session, test_user, tmp_path: Path):
        csv_file = tmp_path / "outside_home.csv"
        csv_file.write_text(
            "Barcode,Name,Price,Cost\n9002001,Outside Home Product,100.00,50.00\n",
            encoding="utf-8",
        )

        service = ImportService()
        result = service.import_products_from_csv(str(csv_file))
        assert result["success"] == 1

        p = db_session.query(Product).filter_by(barcode="9002001").first()
        assert p is not None
        assert p.name_en == "Outside Home Product"

    def test_issue_900_unreadable_file_raises_not_zero_success(self, tmp_path: Path):
        non_existent = tmp_path / "does_not_exist.csv"

        service = ImportService()
        with pytest.raises((ImportError_, FileNotFoundError)):
            service.import_products_from_csv(str(non_existent))

    def test_issue_900_failure_rolls_back_entire_batch(self, db_session, test_user, monkeypatch, tmp_path: Path):
        csv_file = tmp_path / "atomic.csv"
        csv_file.write_text(
            "Barcode,Name,Price,Cost\n9003001,Atomic Prod 1,100.00,50.00\n9003002,Atomic Prod 2,200.00,100.00\n",
            encoding="utf-8",
        )

        service = ImportService()
        orig_create = service.inventory_service.create_product
        calls = 0

        def failing_create(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("Simulated failure on 2nd product")
            return orig_create(*args, **kwargs)

        monkeypatch.setattr(service.inventory_service, "create_product", failing_create)

        with pytest.raises(RuntimeError):
            service.import_products_from_csv(str(csv_file))

        # Because of atomic transaction, product 1 should NOT be in DB
        db_session.expire_all()
        p1 = db_session.query(Product).filter_by(barcode="9003001").first()
        assert p1 is None
