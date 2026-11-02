"""Tests for terminal catalog read-only guards (#869)."""

from datetime import datetime
from decimal import Decimal

import pytest

from cbpos.core.services.category_service import CategoryService
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.customer_service import CustomerService
from cbpos.core.services.import_service import ImportService
from cbpos.core.services.inventory_service import InventoryService
from cbpos.core.services.payment_service import PaymentService
from cbpos.core.services.permission_service import PermissionService
from cbpos.core.services.price_list_service import PriceListService
from cbpos.core.services.promotion_service import PromotionService
from cbpos.core.services.role_service import RoleService
from cbpos.core.services.supplier_service import SupplierService
from cbpos.core.services.unit_service import UnitService
from cbpos.core.services.user_service import UserService
from cbpos.core.utils.terminal_guard import CatalogReadOnlyError, catalog_is_read_only, require_catalog_writable


@pytest.fixture(autouse=True)
def clean_terminal_mode(monkeypatch):
    """Ensure terminal_mode is reset after each test."""
    original_mode = ConfigService.get("terminal_mode")
    yield
    if original_mode is not None:
        ConfigService.set("terminal_mode", original_mode)
    else:
        # Clear or reset
        ConfigService.set("terminal_mode", "standalone")


def test_issue_869_guard_functions(monkeypatch):
    """catalog_is_read_only and require_catalog_writable respond correctly to terminal_mode."""
    # Standalone
    monkeypatch.setattr(ConfigService, "get", lambda k: "standalone" if k == "terminal_mode" else None)
    assert catalog_is_read_only() is False
    require_catalog_writable()  # Should not raise

    # Main
    monkeypatch.setattr(ConfigService, "get", lambda k: "main" if k == "terminal_mode" else None)
    assert catalog_is_read_only() is False
    require_catalog_writable()  # Should not raise

    # Terminal (till)
    monkeypatch.setattr(ConfigService, "get", lambda k: "terminal" if k == "terminal_mode" else None)
    assert catalog_is_read_only() is True
    with pytest.raises(CatalogReadOnlyError) as exc_info:
        require_catalog_writable()
    assert exc_info.value.code == "catalog_read_only"


@pytest.mark.parametrize(
    "call_fn",
    [
        lambda: InventoryService().create_product({"name_en": "P", "price": Decimal("10")}),
        lambda: InventoryService().update_product(1, {"name_en": "P"}),
        lambda: InventoryService().delete_product(1),
        lambda: CategoryService.create("Beverages"),
        lambda: CategoryService.update(1, "Beverages 2"),
        lambda: CategoryService.delete(1),
        lambda: CategoryService.delete_with_descendants(1),
        lambda: CategoryService.reparent(1, 2),
        lambda: UnitService.create("Kg", "kg"),
        lambda: UnitService.update(1, "Kg", "kg", 3),
        lambda: UnitService.delete(1),
        lambda: SupplierService.create_supplier("Supplier A"),
        lambda: SupplierService.update_supplier(1, company_name="Supplier B"),
        lambda: UserService.create_user("cashier2", "1234", 1),
        lambda: UserService.update_user(1, "cashier2", "1234", 1, True),
        lambda: UserService.update_user_profile(1, "Cashier Two", "1234"),
        lambda: UserService.update_admin_pin("4321"),
        lambda: RoleService.create("Cashier Role"),
        lambda: RoleService.update(1, "Manager Role"),
        lambda: RoleService.delete(1),
        lambda: PermissionService.update_role_permissions(1, [1, 2]),
        lambda: PaymentService.create_method("New Pay", False, False, "F12"),
        lambda: PaymentService.update_method(1, name="New Pay 2"),
        lambda: PaymentService.delete_method(1),
        lambda: PromotionService().create_promotion(
            "Promo", "PERCENTAGE", Decimal("10"), datetime.now(), datetime.now()
        ),
        lambda: PromotionService().update_promotion(1, {"name": "Promo 2"}),
        lambda: PromotionService().delete_promotion(1),
        lambda: PriceListService().create_price_list("VIP List"),
        lambda: PriceListService().update_price_list(1, name="VIP List 2"),
        lambda: PriceListService().set_item_price(1, 1, Decimal("90")),
        lambda: PriceListService().delete_item_price(1, 1),
        lambda: PriceListService().delete_price_list(1),
        lambda: PriceListService().apply_bulk_adjust(1, [], "summary"),
        lambda: ImportService().import_products_from_csv("/tmp/test.csv"),
    ],
)
def test_issue_869_service_methods_raise_in_terminal_mode(monkeypatch, call_fn):
    """Every mutating catalog service method raises CatalogReadOnlyError in terminal mode."""
    monkeypatch.setattr(ConfigService, "get", lambda k: "terminal" if k == "terminal_mode" else None)
    with pytest.raises(CatalogReadOnlyError) as exc_info:
        call_fn()
    assert exc_info.value.code == "catalog_read_only"


def test_issue_869_customer_create_allowed_in_terminal_mode(monkeypatch):
    """Customers are transactional, not catalog, and must remain writable on a till (#680)."""
    monkeypatch.setattr(ConfigService, "get", lambda k: "terminal" if k == "terminal_mode" else None)
    # create_customer must not raise CatalogReadOnlyError
    # (it may raise ValueError or DB error if data is empty, but NOT CatalogReadOnlyError)
    try:
        CustomerService().create_customer({})
    except CatalogReadOnlyError:
        pytest.fail("CustomerService.create_customer raised CatalogReadOnlyError in terminal mode!")
    except Exception:
        # Validation error is fine; point is CatalogReadOnlyError was NOT raised
        pass
