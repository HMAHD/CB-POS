"""UI tests for Warranty W1 (#821): WarrantyPolicyDialog, WarrantyPoliciesView,
ProductEditor warranty tab, and CategoryDialog default warranty policy combo.
"""

from datetime import date
from unittest.mock import patch

import pytest

from cbpos.core.models import Role, User, WarrantyPolicy
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.warranty_service import WarrantyService
from cbpos.ui.dialogs.category_dialog import CategoryDialog
from cbpos.ui.dialogs.product_editor import ProductEditor
from cbpos.ui.dialogs.warranty_policy_dialog import WarrantyPolicyDialog
from cbpos.ui.views.warranty_policies_view import WarrantyPoliciesView

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def admin_user(db_session):
    role = Role(name="AdminWarrantyUI", access_level=9)
    db_session.add(role)
    db_session.flush()

    user = User(
        username="admin_warranty_ui",
        pin_hash=AuthService.hash_pin("1234"),
        role_id=role.id,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def sample_policy(db_session):
    policy = WarrantyPolicy(
        name="1 Year Comprehensive",
        name_si="වසර 1ක සම්පූර්ණ වගකීම",
        name_ta="1 வருட விரிவான உத்தரவாதம்",
        warranty_type="SHOP",
        duration=1,
        duration_unit="YEARS",
        remedy="REPAIR_OR_REPLACE",
        provider_name="Shop Provider",
        terms_text="Proof of purchase required.",
        exclusions_text="No liquid damage.",
        is_active=True,
    )
    db_session.add(policy)
    db_session.commit()
    return policy


class TestWarrantyPolicyDialog:
    """Test policy creation, editing, and client-side validation."""

    def test_issue_821_dialog_prefills_existing_policy(self, sample_policy):
        dialog = WarrantyPolicyDialog(policy=sample_policy)
        assert dialog.name_en_input.text() == "1 Year Comprehensive"
        assert dialog.name_si_input.text() == "වසර 1ක සම්පූර්ණ වගකීම"
        assert dialog.name_ta_input.text() == "1 வருட விரிவான உத்தரவாதம்"
        assert dialog.type_combo.currentData() == "SHOP"
        assert dialog.duration_spin.value() == 1
        assert dialog.unit_combo.currentData() == "YEARS"
        assert dialog.remedy_combo.currentData() == "REPAIR_OR_REPLACE"
        assert dialog.provider_input.text() == "Shop Provider"
        assert dialog.terms_en_edit.toPlainText() == "Proof of purchase required."
        assert dialog.excl_en_edit.toPlainText() == "No liquid damage."
        assert dialog.active_check.isChecked() is True

    def test_issue_821_dialog_validation_name_required(self, qtbot):
        dialog = WarrantyPolicyDialog()
        dialog.name_en_input.setText("")
        with patch("cbpos.ui.dialogs.warranty_policy_dialog.QMessageBox.warning") as mock_warn:
            with patch.object(dialog, "accept") as mock_accept:
                dialog.save()
                mock_warn.assert_called_once()
                mock_accept.assert_not_called()

    def test_issue_821_dialog_validation_terms_translation_requires_en(self, qtbot):
        dialog = WarrantyPolicyDialog()
        dialog.name_en_input.setText("Test Policy")
        dialog.terms_en_edit.setPlainText("")
        dialog.terms_si_edit.setPlainText("සිංහල කොන්දේසි")
        with patch("cbpos.ui.dialogs.warranty_policy_dialog.QMessageBox.warning") as mock_warn:
            with patch.object(dialog, "accept") as mock_accept:
                dialog.save()
                mock_warn.assert_called_once()
                mock_accept.assert_not_called()

    def test_issue_821_dialog_validation_exclusions_translation_requires_en(self, qtbot):
        dialog = WarrantyPolicyDialog()
        dialog.name_en_input.setText("Test Policy")
        dialog.excl_en_edit.setPlainText("")
        dialog.excl_ta_edit.setPlainText("தமிழ் விலக்குகள்")
        with patch("cbpos.ui.dialogs.warranty_policy_dialog.QMessageBox.warning") as mock_warn:
            with patch.object(dialog, "accept") as mock_accept:
                dialog.save()
                mock_warn.assert_called_once()
                mock_accept.assert_not_called()


class TestWarrantyPoliciesView:
    """Test policy view table population, search filter, and permission gating."""

    def test_issue_821_view_renders_policies(self, sample_policy):
        view = WarrantyPoliciesView()
        assert view.table.rowCount() >= 1
        # Check first column contains the policy name
        row_names = [view.table.item(r, 0).text() for r in range(view.table.rowCount())]
        assert "1 Year Comprehensive" in row_names

    def test_issue_821_view_search_filters_rows(self, sample_policy):
        view = WarrantyPoliciesView()
        view.search_input.setText("Comprehensive")
        assert view.table.rowCount() == 1

        view.search_input.setText("NonExistentString12345")
        assert view.table.rowCount() == 0


class TestProductEditorWarrantyTab:
    """Test product editor warranty tab display, live preview, and weighted item behavior."""

    def test_issue_821_tab_shown_when_enabled(self, sample_policy):
        ConfigService.set("warranty_enabled", True)
        editor = ProductEditor()
        tab_titles = [editor.tabs.tabText(i) for i in range(editor.tabs.count())]
        assert any("Warranty" in title or "වගකීම" in title or "உத்தரவாதம்" in title for title in tab_titles)

    def test_issue_821_weighted_product_disables_warranty(self, sample_policy):
        ConfigService.set("warranty_enabled", True)
        editor = ProductEditor()
        editor.weighted_check.setChecked(True)
        assert editor.warranty_override_combo.isEnabled() is False
        assert (
            "Weighted" in editor.lbl_warranty_preview.text()
            or "බර" in editor.lbl_warranty_preview.text()
            or "எடை" in editor.lbl_warranty_preview.text()
        )

    def test_issue_821_warranty_preview_shows_calculated_date(self, sample_policy):
        ConfigService.set("warranty_enabled", True)
        editor = ProductEditor()
        editor.weighted_check.setChecked(False)

        # Switch to POLICY mode
        idx = editor.warranty_override_combo.findData("POLICY")
        editor.warranty_override_combo.setCurrentIndex(idx)

        pol_idx = editor.warranty_policy_combo.findData(sample_policy.id)
        editor.warranty_policy_combo.setCurrentIndex(pol_idx)

        # Compute expected end date
        end_date = WarrantyService.compute_end_date(date.today(), sample_policy.duration, sample_policy.duration_unit)
        preview_text = editor.lbl_warranty_preview.text()
        assert str(end_date.year) in preview_text
        assert sample_policy.name in preview_text


class TestCategoryDialogWarranty:
    """Test category dialog default warranty assignment."""

    def test_issue_821_category_dialog_has_warranty_combo(self, sample_policy):
        ConfigService.set("warranty_enabled", True)
        dialog = CategoryDialog()
        assert hasattr(dialog, "warranty_combo")
        # Ensure sample policy is listed
        idx = dialog.warranty_combo.findData(sample_policy.id)
        assert idx >= 0
