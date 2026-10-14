"""
#642: price lists, list prices, promotions and item prices changed with no Activity Log row,
so nobody could see who changed a price or when. The services now write one row per change,
with old and new values, shown readably (and translated) in the Activity Log.
"""

import json
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from cbpos.core.models import AuditLog, Category, Product, Role, User
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.inventory_service import InventoryService
from cbpos.core.services.price_list_service import PriceListService
from cbpos.core.services.promotion_service import PromotionService
from cbpos.core.utils.audit_format import format_audit_action, format_audit_details
from cbpos.i18n import get_language, set_language

_counter = 0


def _suffix() -> str:
    global _counter
    _counter += 1
    return str(_counter)


@pytest.fixture
def lang():
    original = get_language()
    yield set_language
    set_language(original)


@pytest.fixture
def user(db_session, monkeypatch):
    role = Role(name=f"AuditRole642_{_suffix()}")
    db_session.add(role)
    db_session.flush()
    user = User(username=f"audit642_{_suffix()}", pin_hash="hash", role_id=role.id)
    db_session.add(user)
    db_session.flush()
    monkeypatch.setattr(AuthService, "get_current_user", staticmethod(lambda: SimpleNamespace(id=user.id)))
    monkeypatch.setattr(
        "cbpos.core.services.config_service.ConfigService.get", lambda key: {"terminal_id": "T-9"}.get(key)
    )
    return user


@pytest.fixture
def product(db_session):
    p = Product(barcode=f"AUD642-{_suffix()}", name_en="Sugar 1kg", price=Decimal("300.00"), cost=Decimal("250.00"))
    db_session.add(p)
    db_session.flush()
    return p


def _rows(session, action: str) -> list[AuditLog]:
    return session.query(AuditLog).filter_by(action=action).order_by(AuditLog.id).all()


def _text(row: AuditLog) -> str:
    return format_audit_details(row.action, row.details)


class TestPriceLists:
    def test_create_writes_one_row_with_user_and_terminal(self, db_session, user, lang):
        lang("en")
        PriceListService().create_price_list("Wholesale", end_date=datetime(2026, 12, 31))
        [row] = _rows(db_session, "PRICE_LIST_CREATE")
        assert row.user_id == user.id and row.terminal_id == "T-9" and row.event_type == "PRICING"
        assert row.timestamp is not None
        assert _text(row) == "Wholesale: End date: 2026-12-31"

    def test_update_logs_old_and_new(self, db_session, user, lang):
        lang("en")
        service = PriceListService()
        pl = service.create_price_list("Retail", start_date=datetime(2026, 10, 1))
        service.update_price_list(pl.id, name="Retail VIP", start_date=datetime(2026, 11, 1, 9, 30))
        [row] = _rows(db_session, "PRICE_LIST_UPDATE")
        assert json.loads(row.details)["changes"]["name"] == {"old": "Retail", "new": "Retail VIP"}
        assert _text(row) == (
            "Retail: Name changed from Retail to Retail VIP; Start date changed from 2026-10-01 to 2026-11-01 09:30"
        )

    def test_no_change_writes_nothing(self, db_session, user):
        service = PriceListService()
        pl = service.create_price_list("Same")
        service.update_price_list(pl.id, name="Same", is_active=True)
        assert _rows(db_session, "PRICE_LIST_UPDATE") == [] and _rows(db_session, "PRICE_LIST_TOGGLE") == []

    def test_toggle_is_its_own_action(self, db_session, user, lang):
        lang("en")
        service = PriceListService()
        pl = service.create_price_list("Happy Hour")
        service.update_price_list(pl.id, is_active=False)
        [row] = _rows(db_session, "PRICE_LIST_TOGGLE")
        assert _text(row) == "Happy Hour: Switched off"
        assert format_audit_action(row.action) == "Price list switched on/off"

    def test_clearing_a_date(self, db_session, user, lang):
        lang("en")
        service = PriceListService()
        pl = service.create_price_list("Season", end_date=datetime(2026, 12, 31))
        service.update_price_list(pl.id, end_date=None)
        [row] = _rows(db_session, "PRICE_LIST_UPDATE")
        assert _text(row) == "Season: End date removed (was 2026-12-31)"

    def test_delete_logs_what_went(self, db_session, user, product, lang):
        lang("en")
        service = PriceListService()
        pl = service.create_price_list("Old List")
        service.set_item_price(pl.id, product.id, Decimal("280.00"))
        service.delete_price_list(pl.id)
        [row] = _rows(db_session, "PRICE_LIST_DELETE")
        assert _text(row) == "Old List: 1 list price(s) removed with it"


class TestListPrices:
    def test_new_changed_and_removed_price(self, db_session, user, product, lang):
        lang("en")
        service = PriceListService()
        pl = service.create_price_list("Wholesale")
        service.set_item_price(pl.id, product.id, Decimal("280.00"))
        service.set_item_price(pl.id, product.id, Decimal("275.50"))
        service.set_item_price(pl.id, product.id, Decimal("275.5"))  # same price: no row
        service.delete_item_price(pl.id, product.id)

        set_rows = _rows(db_session, "PRICE_LIST_PRICE_SET")
        assert [_text(r) for r in set_rows] == [
            "Wholesale / Sugar 1kg: Price set to Rs. 280.00",
            "Wholesale / Sugar 1kg: Price changed from Rs. 280.00 to Rs. 275.50",
        ]
        [removed] = _rows(db_session, "PRICE_LIST_PRICE_REMOVE")
        assert _text(removed) == "Wholesale / Sugar 1kg: Price removed (was Rs. 275.50)"


class TestPromotions:
    def _create(self, service, **kw):
        data = {
            "name": "Weekend Deal",
            "type": "PERCENTAGE",
            "value": Decimal("10"),
            "start_time": datetime(2026, 10, 1),
            "end_time": datetime(2026, 12, 31, 18, 0),
            "days_of_week": "5,6",
        }
        data.update(kw)
        return service.create_promotion(**data)

    def test_create(self, db_session, user, lang):
        lang("en")
        self._create(PromotionService())
        [row] = _rows(db_session, "PROMOTION_CREATE")
        assert row.user_id == user.id
        assert _text(row) == (
            "Weekend Deal: Type: Percentage; Discount: 10%; Start time: 2026-10-01; "
            "End time: 2026-12-31 18:00; Days: Sat, Sun; Applies to: All Products"
        )

    def test_update_value_days_and_scope(self, db_session, user, lang):
        lang("en")
        cat = Category(name=f"Bakery642_{_suffix()}")
        db_session.add(cat)
        db_session.flush()
        service = PromotionService()
        promo = self._create(service)
        service.update_promotion(promo.id, value=Decimal("15"), days_of_week=None, category_id=cat.id)
        [row] = _rows(db_session, "PROMOTION_UPDATE")
        assert _text(row) == (
            "Weekend Deal: Discount changed from 10% to 15%; Days changed from Sat, Sun to All Days; "
            f"Applies to changed from All Products to {cat.name}"
        )

    def test_toggle_and_delete(self, db_session, user, lang):
        lang("en")
        service = PromotionService()
        promo = self._create(service, type="FIXED_AMOUNT", value=Decimal("5"))
        service.update_promotion(promo.id, is_active=False)
        service.delete_promotion(promo.id)
        [toggle] = _rows(db_session, "PROMOTION_TOGGLE")
        assert _text(toggle) == "Weekend Deal: Switched off"
        [deleted] = _rows(db_session, "PROMOTION_DELETE")
        assert _text(deleted).startswith("Weekend Deal: Type: Fixed Amount; Discount: Rs. 5.00;")

    def test_unchanged_save_writes_nothing(self, db_session, user):
        service = PromotionService()
        promo = self._create(service)
        service.update_promotion(promo.id, name="Weekend Deal", value=Decimal("10.00"), is_active=True)
        assert _rows(db_session, "PROMOTION_UPDATE") == [] and _rows(db_session, "PROMOTION_TOGGLE") == []


class TestItemPrice:
    def test_product_price_change_is_logged(self, db_session, user, product, lang):
        lang("en")
        service = InventoryService()
        service.update_product(product.id, {"price": Decimal("320.00")})
        service.update_product(product.id, {"price": Decimal("320"), "name_en": "Sugar 1kg"})  # no price change
        [row] = _rows(db_session, "PRODUCT_PRICE_CHANGE")
        assert row.event_type == "INVENTORY"
        assert _text(row) == "Sugar 1kg: Price changed from Rs. 300.00 to Rs. 320.00"


class TestWithoutUserAndTranslations:
    def test_no_signed_in_user_still_saves_without_a_row(self, db_session, monkeypatch):
        monkeypatch.setattr(AuthService, "get_current_user", staticmethod(lambda: None))
        pl = PriceListService().create_price_list(f"NoUser_{_suffix()}")
        assert pl.id is not None
        assert _rows(db_session, "PRICE_LIST_CREATE") == []

    @pytest.mark.parametrize("language", ["si", "ta"])
    def test_translated(self, db_session, user, product, lang, language):
        service = PriceListService()
        pl = service.create_price_list("Wholesale")
        service.set_item_price(pl.id, product.id, Decimal("280.00"))
        service.set_item_price(pl.id, product.id, Decimal("275.00"))
        service.update_price_list(pl.id, is_active=False)
        lang(language)
        for action in ("PRICE_LIST_CREATE", "PRICE_LIST_PRICE_SET", "PRICE_LIST_TOGGLE"):
            for row in _rows(db_session, action):
                label, text = format_audit_action(row.action), _text(row)
                assert label != row.action and "_" not in label
                assert "{" not in text and "changed" not in text and "Switched" not in text
                assert "Wholesale" in text
