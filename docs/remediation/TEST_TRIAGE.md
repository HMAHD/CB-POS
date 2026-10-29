# Test Triage (owner review)

**Generated:** 2026-10-29 from a full run with per-test coverage contexts (`pytest --cov=cbpos --cov-context=test`). **"Unique lines"** = lines of `cbpos/` that no other test file executes.

**Nothing is deleted until the owner approves this list.** Tick a row to override it.

## Rules used

| Decision | Rule |
|---|---|
| Keep | Domain, integration and guardrail layers are always kept (each test asserts a distinct business rule, even over shared lines). UI files are kept if they cover unique lines or guard si/ta clipping |
| Merge | A UI file with 0 unique lines but behaviour assertions. Fold its tests into the existing file for the same screen; the test count stays, the file count drops |
| Convert | Reads source code as text, or encodes a codebase-wide style rule. Becomes one parametrised AST rule in `tests/guardrails/` |
| Delete | 0 unique lines **and** assertions are mostly colours/QSS/sizes **and** not a clipping guard. Covered by the §0.7 screenshot gate instead |

## Totals

| Decision | Files | Tests |
|---|---|---|
| Keep | 279 | 1930 |
| Merge | 61 | 237 |
| Convert | 13 | 109 |
| Delete | 4 | 15 |

**Finding:** the suite is mostly legitimate. Only about 14 tests are pure cosmetics. The cost comes from **file sprawl** (one file per UI fix) and from UI tests that could be domain tests (see the architecture review, card 1). It does not come from useless tests. The real reductions are Merge (≈60 files fewer) and moving screen logic into workflow modules (card 1, done screen by screen in the remediation batches).

## Delete

| ✓ | File | Tests | Unique lines | Why |
|---|---|---|---|---|
| [ ] | `tests/ui/test_stock_take_button_colors.py` | 7 | 0 | 0 unique lines, 100% style asserts |
| [ ] | `tests/ui/test_settings_section_header_divider.py` | 3 | 0 | 0 unique lines, 50% style asserts |
| [ ] | `tests/ui/test_spacing_and_bars.py` | 3 | 0 | 0 unique lines, 85% style asserts |
| [ ] | `tests/ui/test_label_preview_dialog_theme.py` | 2 | 0 | 0 unique lines, 100% style asserts |

## Convert

| ✓ | File | Tests | Unique lines | Why |
|---|---|---|---|---|
| [ ] | `tests/ui/test_payment_method_shortcut_collisions.py` | 17 | 88 | reads source text → guardrail |
| [ ] | `tests/ui/test_activity_log_readable.py` | 16 | 6 | reads source text → guardrail |
| [ ] | `tests/ui/test_loyalty_adjustment.py` | 15 | 71 | reads source text → guardrail |
| [ ] | `tests/ui/test_screen_access_by_permission.py` | 10 | 0 | reads source text → guardrail |
| [ ] | `tests/ui/test_dialog_button_class_consistency.py` | 8 | 0 | one guardrail: dismiss buttons are never class=danger |
| [ ] | `tests/ui/test_credit_book_ui_improvements.py` | 7 | 4 | reads source text → guardrail |
| [ ] | `tests/ui/test_qss_syntax.py` | 7 | 0 | QSS must parse: move to guardrails as-is |
| [ ] | `tests/ui/test_ui_attribute_initialization.py` | 7 | 0 | reads source text → guardrail |
| [ ] | `tests/ui/test_product_editor_inventory_responsive.py` | 6 | 0 | reads source text → guardrail |
| [ ] | `tests/ui/test_pricelist_sidebar_visual_hierarchy.py` | 5 | 0 | reads source text → guardrail |
| [ ] | `tests/ui/test_payment_method_shortcut_hint_and_default_seed.py` | 4 | 0 | reads source text → guardrail |
| [ ] | `tests/ui/test_permission_dialog_sizing_and_checkboxes.py` | 4 | 0 | reads source text → guardrail |
| [ ] | `tests/ui/test_undo_toast_theming.py` | 3 | 0 | reads source text → guardrail |

## Merge

| ✓ | File | Tests | Unique lines | Why |
|---|---|---|---|---|
| [ ] | `tests/ui/test_qss_shared_component_states.py` | 13 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_action_panel_customer_card_redesign.py` | 10 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_number_formatters.py` | 10 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_guiding_empty_states.py` | 9 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_settings_form_standardization_issue_573.py` | 8 | 0 | barcode-prefix validator is behaviour |
| [ ] | `tests/ui/test_print_worker.py` | 7 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_supplier_dialog_styling.py` | 7 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_typed_numeric_fields_issue_599.py` | 7 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_cart_empty_state_overlay.py` | 6 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_customer_selection_dialog_table_conventions.py` | 6 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_style_helpers.py` | 6 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_action_panel_customer_points_card.py` | 5 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_customer_card_and_dialog_buttons_redesign.py` | 5 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_display_scaling.py` | 5 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_empty_state_widget.py` | 5 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_pricelist_price_formatting.py` | 5 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_print_worker_job_types.py` | 5 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_purchase_view_supplier_combo_searchable.py` | 5 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_table_column_alignment_fixes.py` | 5 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_checkbox_labelling_issue_576.py` | 4 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_customer_statement_dialog_spacing.py` | 4 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_destroy_hooks_gc_safety.py` | 4 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_dialog_footer.py` | 4 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_menu_matches_screen_tabs.py` | 4 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_permission_dialog.py` | 4 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_proforma_dialog_validity_field.py` | 4 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_receipt_page_cross_reference_hint.py` | 4 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_sales_light_theme_action_panel_and_header.py` | 4 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_settings_pages_package.py` | 4 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_stock_take_table_columns.py` | 4 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_cart_empty_state_has_an_icon.py` | 3 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_cart_totals_row_height.py` | 3 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_customer_selection_dialog_keyboard_confirm.py` | 3 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_hardware_auto_cut_wording.py` | 3 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_main_window_shift_dialog_ordering.py` | 3 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_pagination_widget_hides_when_one_page.py` | 3 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_report_viewer_uses_shared_empty_state.py` | 3 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_sales_shortcut_badges.py` | 3 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_sales_totals_block_grouping.py` | 3 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_admin_tools_hardware_config_hint.py` | 2 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_cart_discount_row_tint.py` | 2 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_category_manager_tree_columns.py` | 2 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_customer_statement_summary_shows_values.py` | 2 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_grn_history_status_filter_label.py` | 2 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_icons_customer_points_constants.py` | 2 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_loyalty_tab_redesign.py` | 2 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_management_screens_page_header.py` | 2 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_management_view_default_tab.py` | 2 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_pricelist_view_no_redundant_status_column.py` | 2 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_proforma_dialog_empty_state.py` | 2 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_receipt_logo_guidance.py` | 2 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_report_and_document_table_columns.py` | 2 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_report_column_headers_translated.py` | 2 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_sales_view_loyalty_card_scan.py` | 2 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_credit_book_shows_loyalty_points.py` | 1 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_denomination_widget.py` | 1 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_document_browser_subtitle.py` | 1 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_report_filter_widget.py` | 1 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_user_table_no_duplicate_id.py` | 1 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_user_view_activity_log_filters.py` | 1 | 0 | 0 unique lines, behaviour asserts |
| [ ] | `tests/ui/test_view_lifecycle_no_gc_cycle.py` | 1 | 0 | 0 unique lines, behaviour asserts |

## Keep

279 files. Not listed individually; see the layer folders.
