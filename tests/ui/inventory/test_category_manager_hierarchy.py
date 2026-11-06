from cbpos.core.services.category_service import CategoryService
from cbpos.ui.dialogs.category_manager import CategoryManagerDialog

_counter = 0


def _uid() -> str:
    global _counter
    _counter += 1
    return str(_counter)


def test_issue_921_parent_combo_offers_only_top_level_categories(qapp, db_session):
    """Parent category combo offers only top-level categories, never subcategories (#921)."""
    uid = _uid()
    root1 = CategoryService.create(name=f"Beverages_{uid}", parent_id=None)
    sub1 = CategoryService.create(name=f"Soft Drinks_{uid}", parent_id=root1.id)
    root2 = CategoryService.create(name=f"Snacks_{uid}", parent_id=None)

    dialog = CategoryManagerDialog()
    try:
        combo = dialog.combo_parent
        combo_ids = [combo.itemData(i) for i in range(combo.count())]

        # Must include None (Top Level) and root categories, but MUST NOT include sub1
        assert None in combo_ids
        assert root1.id in combo_ids
        assert root2.id in combo_ids
        assert sub1.id not in combo_ids

        # UI/UX: Tooltip or hint on combo
        assert "one level" in combo.toolTip().lower() or "one level" in dialog.lbl_parent_hint.text().lower()
    finally:
        dialog.deleteLater()
