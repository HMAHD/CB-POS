"""
New GRN's "Add Product" search built an empty QCompleter() and never gave it
a model, so it could never suggest anything no matter what was typed. On
Enter, add_product_to_grid() then called ProductService.search(query) and
silently took products[0] -- the first fuzzy match, not necessarily the one
the user meant, with no way to disambiguate among multiple matches.
"""

from decimal import Decimal

import pytest

from cbpos.core.models import Product
from cbpos.ui.views.purchase_view import PurchaseView

pytestmark = pytest.mark.usefixtures("qapp")

_counter = 0


def _next_suffix() -> str:
    global _counter
    _counter += 1
    return str(_counter)


def _make_product(db_session, name, barcode, cost="10.00"):
    p = Product(barcode=barcode, name_en=name, price=Decimal("20.00"), cost=Decimal(cost))
    db_session.add(p)
    db_session.flush()
    return p


class TestProductCompleter:
    def test_completer_model_is_populated_with_real_products(self, db_session):
        suffix = _next_suffix()
        product = _make_product(db_session, f"Rice 5kg {suffix}", f"BC-RICE-{suffix}")

        view = PurchaseView()

        model = view.completer.model()
        assert model is not None
        names = [model.data(model.index(i, 0)) for i in range(model.rowCount())]
        assert f"{product.name_en} [{product.barcode}]" in names


class TestAddProductToGrid:
    def test_adds_the_exact_product_matching_the_typed_text_not_the_first_fuzzy_match(self, db_session):
        suffix = _next_suffix()
        # Two products share a substring ("Soap") -- a fuzzy first-match would
        # be ambiguous between them; the fix must resolve the exact one typed.
        _make_product(db_session, f"Sunlight Soap 100g {suffix}", f"BC-SOAP-A-{suffix}", cost="50.00")
        soap_b = _make_product(db_session, f"Lifebuoy Soap 100g {suffix}", f"BC-SOAP-B-{suffix}", cost="60.00")

        view = PurchaseView()
        view.load_products_for_completer()

        view.product_search.setText(f"{soap_b.name_en} [{soap_b.barcode}]")
        view.add_product_to_grid()

        assert len(view.grn_items) == 1
        assert view.grn_items[0]["product"].id == soap_b.id
        assert view.grn_items[0]["cost"] == Decimal("60.00")

    def test_unknown_text_shows_not_found_instead_of_guessing(self, db_session, monkeypatch):
        view = PurchaseView()
        warned = {}
        monkeypatch.setattr(
            "cbpos.ui.views.purchase_view.QMessageBox.warning",
            lambda *a, **k: warned.setdefault("called", True),
        )

        view.product_search.setText("Something that was never typed correctly")
        view.add_product_to_grid()

        assert warned.get("called") is True
        assert view.grn_items == []
