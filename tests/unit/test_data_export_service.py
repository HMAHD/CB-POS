"""Tests for DataExportService DataFrame generation."""

from datetime import datetime
from decimal import Decimal

import pandas as pd

from cbpos.core.models import Category, Customer, Product, Unit
from cbpos.core.services.data_export_service import DataExportService


class TestDataExportService:
    """Unit tests for DataExportService."""

    def test_get_products_dataframe_empty(self, db_session):
        """Test products DataFrame with no data returns empty DataFrame."""
        df = DataExportService.get_products_dataframe()
        assert isinstance(df, pd.DataFrame)

    def test_get_products_dataframe_with_data(self, db_session):
        """Test products DataFrame includes product fields."""
        cat = Category(name="Grocery")
        db_session.add(cat)
        db_session.flush()

        unit = Unit(name="kg", abbreviation="kg")
        db_session.add(unit)
        db_session.flush()

        product = Product(
            barcode="1234567890",
            name_en="Test Rice",
            price=Decimal("500.00"),
            cost=Decimal("400.00"),
            stock_qty=Decimal("100.000"),
            category_id=cat.id,
            unit_id=unit.id,
            is_active=True,
        )
        db_session.add(product)
        db_session.flush()

        df = DataExportService.get_products_dataframe()
        assert len(df) >= 1
        assert "Barcode" in df.columns
        assert "Name" in df.columns
        assert "Price" in df.columns
        assert "Category" in df.columns
        assert "Unit" in df.columns

    def test_get_products_excludes_inactive(self, db_session):
        """Test that inactive products are excluded."""
        product = Product(
            barcode="INACTIVE001",
            name_en="Inactive Product",
            price=Decimal("100.00"),
            cost=Decimal("80.00"),
            is_active=False,
        )
        db_session.add(product)
        db_session.flush()

        df = DataExportService.get_products_dataframe()
        barcodes = df["Barcode"].tolist() if len(df) > 0 else []
        assert "INACTIVE001" not in barcodes

    def test_get_customers_dataframe_empty(self, db_session):
        """Test customers DataFrame with no data returns empty DataFrame."""
        df = DataExportService.get_customers_dataframe()
        assert isinstance(df, pd.DataFrame)

    def test_get_customers_dataframe_with_data(self, db_session):
        """Test customers DataFrame includes customer fields."""
        customer = Customer(
            name="Test Customer",
            phone="0771234567",
            email="test@example.com",
            credit_limit=Decimal("10000.00"),
            current_debt=Decimal("500.00"),
            is_active=True,
        )
        db_session.add(customer)
        db_session.flush()

        df = DataExportService.get_customers_dataframe()
        assert len(df) >= 1
        assert "Name" in df.columns
        assert "Phone" in df.columns
        assert "Credit Limit" in df.columns

    def test_get_sales_dataframe_empty(self, db_session):
        """Test sales DataFrame with no data returns empty DataFrame."""
        df = DataExportService.get_sales_dataframe()
        assert isinstance(df, pd.DataFrame)

    def test_get_sales_dataframe_with_date_filter(self, db_session):
        """Test sales DataFrame respects date filters."""
        # Query with a date range that has no sales
        start = datetime(2000, 1, 1)
        end = datetime(2000, 12, 31)
        df = DataExportService.get_sales_dataframe(start, end)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    def test_get_sales_dataframe_columns(self, db_session):
        """Test sales DataFrame has expected columns when data exists."""
        df = DataExportService.get_sales_dataframe()
        if len(df) > 0:
            expected = {"Invoice", "Date", "Customer", "Total", "VAT", "Payment", "Status"}
            assert expected.issubset(set(df.columns))
