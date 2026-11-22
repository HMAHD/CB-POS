# Phase U.0 — UI Surface and Navigation Inventory

> **Status:** provisional mechanical baseline for #1041 against product code `69fd64a` and record baseline `504df7f`.
> **Rule:** file length is a responsibility signal only. Runtime claims require the separate measured performance baseline.

## Method

- AST-scanned every Python file under `cbpos/ui/` for top-level classes and service/database imports.
- Classified files by their current package ownership; this does not endorse the current directory structure.
- The inventory is complete mechanically. Shell reachability, permission ownership, lifecycle, Help/About, update, and hardware paths are traced in `UI_ARCHITECTURE_MAP.md`; feature journeys, dialog reachability, state coverage, and Windows verification remain pending.

## Navigation roots

- `main.py` creates `MainWindow`; `MainWindow` owns the top-level stacked navigation and global scanner/session behavior.
- `LoginView` enters `SalesView`; the side menu reaches management, settings, documents, history, refunds, reprints, and contextual support surfaces.
- `ManagementView` owns the management tab stack and permission-gated business screens.
- `SettingsView` owns settings-page navigation, including hardware and system/update entry points.
- Modal workflows are primarily under `cbpos/ui/dialogs/`; reusable controls are under `widgets/` and `components/`.

## Mechanical counts

| Role | Files with classes |
|---|---:|
| Shell | 1 |
| View | 29 |
| Settings page | 10 |
| Dialog | 74 |
| Reusable widget | 25 |
| Shared component | 1 |
| UI infrastructure | 3 |
| **Total** | **143** |

## Class-bearing UI files

| Role | File | Top-level classes | Lines | Core service imports | Verification flags |
|---|---|---|---:|---|---|
| Shared component | `cbpos/ui/components/activation.py` | `Activatable` | 32 | `—` | — |
| Dialog | `cbpos/ui/dialogs/about_dialog.py` | `AboutDialog` | 319 | `theme_service` | — |
| Dialog | `cbpos/ui/dialogs/adjust_balance_dialog.py` | `AdjustBalanceDialog` | 295 | `auth_service, customer_credit_service` | — |
| Dialog | `cbpos/ui/dialogs/adjust_points_dialog.py` | `AdjustPointsDialog` | 311 | `auth_service, loyalty_service` | — |
| Dialog | `cbpos/ui/dialogs/admin_pin_dialog.py` | `AdminPinDialog` | 124 | `—` | — |
| Dialog | `cbpos/ui/dialogs/advanced_search_dialog.py` | `AdvancedSearchDialog` | 286 | `category_service, product_service, supplier_service, theme_service` | — |
| Dialog | `cbpos/ui/dialogs/autosave_recovery_dialog.py` | `AutosaveAction, AutosaveRecoveryDialog` | 148 | `cart_autosave_service` | — |
| Dialog | `cbpos/ui/dialogs/backup_password_dialog.py` | `BackupPasswordDialog` | 152 | `config_service` | — |
| Dialog | `cbpos/ui/dialogs/bill_discount_dialog.py` | `BillDiscountDialog` | 250 | `—` | — |
| Dialog | `cbpos/ui/dialogs/bulk_price_adjust_dialog.py` | `BulkPriceAdjustDialog` | 481 | `price_list_service, product_service` | — |
| Dialog | `cbpos/ui/dialogs/buyer_details_dialog.py` | `BuyerDetailsDialog` | 145 | `—` | — |
| Dialog | `cbpos/ui/dialogs/cash_movement_dialog.py` | `CashMovementDialog` | 101 | `—` | — |
| Dialog | `cbpos/ui/dialogs/category_dialog.py` | `CategoryDialog` | 162 | `category_service, warranty_service` | — |
| Dialog | `cbpos/ui/dialogs/category_manager.py` | `CategoryManagerDialog` | 394 | `category_service, config_service, warranty_service` | — |
| Dialog | `cbpos/ui/dialogs/category_tree_dialog.py` | `CategoryTreeDialog` | 239 | `category_service` | — |
| Dialog | `cbpos/ui/dialogs/csv_import_dialog.py` | `CsvImportDialog` | 408 | `import_service` | — |
| Dialog | `cbpos/ui/dialogs/customer_editor.py` | `CustomerEditor` | 756 | `config_service, customer_service, loyalty_service, price_list_service, tax_service` | — |
| Dialog | `cbpos/ui/dialogs/customer_quick_add.py` | `CustomerQuickAddDialog` | 73 | `customer_service` | — |
| Dialog | `cbpos/ui/dialogs/customer_selection_dialog.py` | `CustomerSelectionDialog` | 194 | `customer_service` | — |
| Dialog | `cbpos/ui/dialogs/customer_statement_dialog.py` | `CustomerStatementDialog` | 411 | `customer_credit_service, receipt_builder, statement_service` | — |
| Dialog | `cbpos/ui/dialogs/data_export_dialog.py` | `DataExportDialog` | 231 | `data_export_service, export_service` | — |
| Dialog | `cbpos/ui/dialogs/database_setup_dialog.py` | `DatabaseSetupDialog` | 143 | `—` | — |
| Dialog | `cbpos/ui/dialogs/discount_dialog.py` | `DiscountDialog` | 243 | `—` | — |
| Dialog | `cbpos/ui/dialogs/force_close_shift_dialog.py` | `ForceCloseShiftDialog` | 166 | `auth_service, shift_service` | — |
| Dialog | `cbpos/ui/dialogs/grn_detail_dialog.py` | `GRNDetailDialog` | 145 | `purchase_service` | — |
| Dialog | `cbpos/ui/dialogs/guide_dialog.py` | `GuideDialog` | 215 | `—` | — |
| Dialog | `cbpos/ui/dialogs/label_preview_dialog.py` | `LabelCard, LabelPreviewDialog` | 200 | `label_service` | — |
| Dialog | `cbpos/ui/dialogs/label_print_dialog.py` | `_QtyDelegate, LabelPrintDialog` | 765 | `config_service, label_service, product_service` | — |
| Dialog | `cbpos/ui/dialogs/log_detail_dialog.py` | `LogDetailDialog` | 164 | `—` | — |
| Dialog | `cbpos/ui/dialogs/manager_override_dialog.py` | `ManagerOverrideDialog` | 125 | `auth_service, permission_service` | — |
| Dialog | `cbpos/ui/dialogs/payment_dialog.py` | `PaymentDialog` | 996 | `config_service, customer_service, loyalty_service, payment_service, tax_invoice_service` | — |
| Dialog | `cbpos/ui/dialogs/payment_method_dialog.py` | `PaymentMethodDialog` | 260 | `payment_service` | — |
| Dialog | `cbpos/ui/dialogs/permission_dialog.py` | `_RoleCheckDelegate, PermissionDialog` | 309 | `auth_service, permission_service, user_service` | — |
| Dialog | `cbpos/ui/dialogs/plan_covered_item_chooser_dialog.py` | `PlanCoveredItemChooserDialog` | 112 | `—` | — |
| Dialog | `cbpos/ui/dialogs/price_board_dialog.py` | `PriceBoardLoaderWorker, PriceBoardSaveWorker, PriceBoardItemDelegate, PriceBoardDialog` | 590 | `price_board_service, theme_service` | worker lifecycle |
| Dialog | `cbpos/ui/dialogs/price_list_dialog.py` | `PriceListDialog` | 122 | `—` | — |
| Dialog | `cbpos/ui/dialogs/product_editor.py` | `ProductEditor` | 1287 | `auth_service, category_service, config_service, feature_flags, inventory_service, permission_service, supplier_service, unit_service, warranty_service` | responsibility review (≥1,000 lines) |
| Dialog | `cbpos/ui/dialogs/profile_dialog.py` | `ProfileDialog` | 165 | `auth_service, user_service` | — |
| Dialog | `cbpos/ui/dialogs/proforma_dialog.py` | `ProformaDialog` | 366 | `customer_service, product_service, proforma_service` | — |
| Dialog | `cbpos/ui/dialogs/promotion_dialog.py` | `PromotionDialog` | 335 | `category_service, config_service, promotion_service` | — |
| Dialog | `cbpos/ui/dialogs/quantity_dialog.py` | `QuantityDialog` | 124 | `—` | — |
| Dialog | `cbpos/ui/dialogs/receipt_options_dialog.py` | `ReceiptOptionsDialog` | 406 | `email_service, invoice_service, printer_service, receipt_builder, theme_service` | — |
| Dialog | `cbpos/ui/dialogs/receipt_preview_dialog.py` | `ReceiptPreviewDialog` | 51 | `—` | — |
| Dialog | `cbpos/ui/dialogs/receipt_reprint_dialog.py` | `ReceiptReprintDialog` | 641 | `auth_service, config_service, receipt_builder, receipt_reprint_service, sale_query_service` | — |
| Dialog | `cbpos/ui/dialogs/receive_payment_dialog.py` | `ReceivePaymentDialog` | 273 | `auth_service, customer_credit_service, customer_service, payment_service` | — |
| Dialog | `cbpos/ui/dialogs/refund_dialog.py` | `RefundTenderOverrideDialog, RefundDialog` | 707 | `product_service, refund_breakdown, refund_service, sale_query_service, transaction_service, warranty_service` | — |
| Dialog | `cbpos/ui/dialogs/role_manager.py` | `RoleManagerDialog` | 263 | `role_service, user_service` | — |
| Dialog | `cbpos/ui/dialogs/sale_history_dialog.py` | `SaleHistoryDialog` | 968 | `auth_service, receipt_builder, receipt_reprint_service, refund_service, sale_query_service, transaction_service` | — |
| Dialog | `cbpos/ui/dialogs/serial_entry_dialog.py` | `SerialEntryDialog` | 337 | `product_service, warranty_service` | — |
| Dialog | `cbpos/ui/dialogs/serial_refund_selection_dialog.py` | `SerialRefundSelectionDialog` | 129 | `—` | — |
| Dialog | `cbpos/ui/dialogs/set_item_price_dialog.py` | `SetItemPriceDialog` | 92 | `—` | — |
| Dialog | `cbpos/ui/dialogs/setup_wizard.py` | `SetupWizard` | 473 | `config_service` | — |
| Dialog | `cbpos/ui/dialogs/shift_closing_dialog.py` | `ShiftClosingDialog` | 301 | `backup_service, printer_service, shift_service` | — |
| Dialog | `cbpos/ui/dialogs/shift_management_dialog.py` | `ShiftManagementDialog` | 350 | `auth_service, config_service, permission_service, printer_service, shift_service` | — |
| Dialog | `cbpos/ui/dialogs/shortcuts_help_dialog.py` | `ShortcutsHelpDialog` | 110 | `feature_flags` | — |
| Dialog | `cbpos/ui/dialogs/stale_shifts_dialog.py` | `StaleShiftsDialog` | 126 | `shift_service` | — |
| Dialog | `cbpos/ui/dialogs/start_shift_dialog.py` | `StartShiftDialog` | 76 | `shift_service` | — |
| Dialog | `cbpos/ui/dialogs/stock_adjustment_dialog.py` | `StockAdjustmentDialog` | 222 | `config_service, inventory_service` | — |
| Dialog | `cbpos/ui/dialogs/stock_count_report_dialog.py` | `StockCountReportDialog` | 222 | `stock_count_service` | — |
| Dialog | `cbpos/ui/dialogs/stock_history_dialog.py` | `StockHistoryDialog` | 148 | `stock_service` | — |
| Dialog | `cbpos/ui/dialogs/supplier_dialog.py` | `SupplierDialog` | 138 | `—` | — |
| Dialog | `cbpos/ui/dialogs/supplier_payment_dialog.py` | `SupplierPaymentDialog` | 205 | `auth_service, payment_service, supplier_payable_service, supplier_service` | — |
| Dialog | `cbpos/ui/dialogs/sync_pairing_dialog.py` | `FetchCertWorker, SyncPairingDialog` | 269 | `auth_service, config_service, logging_service` | worker lifecycle |
| Dialog | `cbpos/ui/dialogs/text_viewer_dialog.py` | `TextViewerDialog` | 103 | `—` | — |
| Dialog | `cbpos/ui/dialogs/unit_manager.py` | `UnitManagerDialog` | 266 | `unit_service` | — |
| Dialog | `cbpos/ui/dialogs/update_dialog.py` | `_DownloadThread, _CheckThread, UpdateDialog` | 339 | `update_service` | worker lifecycle |
| Dialog | `cbpos/ui/dialogs/user_dialog.py` | `UserDialog` | 191 | `auth_service, user_service` | — |
| Dialog | `cbpos/ui/dialogs/valuation_dialog.py` | `ValuationDialog` | 203 | `report_service` | — |
| Dialog | `cbpos/ui/dialogs/void_reason_dialog.py` | `VoidReasonDialog` | 100 | `—` | — |
| Dialog | `cbpos/ui/dialogs/warranty_claim_intake_dialog.py` | `WarrantyClaimIntakeDialog` | 209 | `auth_service, warranty_claim_receipt_builder, warranty_claim_service, warranty_dto` | — |
| Dialog | `cbpos/ui/dialogs/warranty_claim_resolve_dialog.py` | `WarrantyClaimResolveDialog` | 258 | `auth_service, product_service, warranty_claim_service, warranty_dto` | — |
| Dialog | `cbpos/ui/dialogs/warranty_correction_dialog.py` | `WarrantyCorrectionDialog` | 155 | `auth_service, warranty_dto, warranty_service` | — |
| Dialog | `cbpos/ui/dialogs/warranty_lookup_dialog.py` | `WarrantyLookupDialog` | 547 | `auth_service, permission_service, warranty_dto, warranty_service` | — |
| Dialog | `cbpos/ui/dialogs/warranty_policy_dialog.py` | `WarrantyPolicyDialog` | 247 | `warranty_service` | — |
| Dialog | `cbpos/ui/dialogs/warranty_supplier_dialogs.py` | `WarrantySupplierDispatchDialog, WarrantySupplierReceiveDialog, WarrantySupplierOutcomeDialog` | 485 | `auth_service, supplier_service, warranty_claim_receipt_builder, warranty_claim_service, warranty_dto` | — |
| Shell | `cbpos/ui/main_window.py` | `MainWindow` | 477 | `auth_service, backup_service, config_service, customer_service, shift_service` | — |
| UI infrastructure | `cbpos/ui/network_schema_gate.py` | `GateAction, UpgradeWorker, NetworkSchemaGate` | 232 | `auth_service, config_service, schema_migration_service` | worker lifecycle |
| UI infrastructure | `cbpos/ui/resources/icons.py` | `Icons` | 91 | `—` | — |
| View | `cbpos/ui/views/admin_tools_view.py` | `AdminToolsView` | 1116 | `config_service, error_log_service, hardware_test_service, maintenance_service` | responsibility review (≥1,000 lines) |
| View | `cbpos/ui/views/credit_book_view.py` | `CreditBookView` | 1187 | `config_service, customer_credit_service, customer_service` | responsibility review (≥1,000 lines) |
| View | `cbpos/ui/views/dashboard_view.py` | `_DashboardWheelForwarder, _YearlyWorker, _PeriodicWorker, _WarrantyTileWorker, DashboardView` | 877 | `config_service, dashboard_service, tax_service, warranty_claim_service` | worker lifecycle |
| View | `cbpos/ui/views/data_safety/backup_tab.py` | `BackupTabWidget` | 463 | `backup_service, config_service` | — |
| View | `cbpos/ui/views/data_safety/export_tab.py` | `ExportContext, ExportTabWidget` | 221 | `export_service` | — |
| View | `cbpos/ui/views/data_safety/export_types.py` | `ExportType, ExportFormat` | 77 | `data_export_service` | — |
| View | `cbpos/ui/views/data_safety/maintenance_tab.py` | `MaintenanceTabWidget` | 282 | `backup_service, maintenance_service` | — |
| View | `cbpos/ui/views/data_safety/network_notice.py` | `NetworkModeNoticeCard` | 58 | `backup_service, theme_service` | — |
| View | `cbpos/ui/views/data_safety/restore_tab.py` | `RestoreTabWidget` | 328 | `backup_service, config_service` | — |
| View | `cbpos/ui/views/data_safety_view.py` | `DataSafetyView` | 91 | `—` | — |
| View | `cbpos/ui/views/document_view.py` | `DocumentBrowserView` | 1215 | `auth_service, config_service, document_browser_service, proforma_service, receipt_builder, receipt_reprint_service, refund_service, sale_query_service, tax_service, transaction_service, user_service` | responsibility review (≥1,000 lines) |
| View | `cbpos/ui/views/history_view.py` | `HistoryView` | 658 | `auth_service, printer_service, refund_service, sale_query_service, tax_invoice_service, transaction_service` | — |
| View | `cbpos/ui/views/inventory_view.py` | `InventoryModel, InventoryView` | 453 | `import_service, inventory_service, theme_service` | — |
| View | `cbpos/ui/views/login_view.py` | `_PinPanel, LoginView` | 514 | `auth_service, theme_service` | — |
| View | `cbpos/ui/views/management_view.py` | `ManagementView` | 429 | `config_service, permission_service, theme_service` | — |
| View | `cbpos/ui/views/payment_methods_view.py` | `_MethodCard, PaymentMethodsView` | 393 | `payment_service` | — |
| View | `cbpos/ui/views/pricelist_view.py` | `PriceListView` | 722 | `price_list_service, product_service` | — |
| View | `cbpos/ui/views/promotion_view.py` | `PromotionView` | 327 | `category_service, promotion_service` | — |
| View | `cbpos/ui/views/purchase_view.py` | `SupplierTableModel, PurchaseHistoryModel, GrnNumericDelegate, PurchaseView` | 2038 | `auth_service, feature_flags, inventory_service, product_service, purchase_order_service, purchase_service, supplier_payable_service, supplier_service` | responsibility clusters mapped; synchronous loads/GRN commit on UI thread confirmed (`U0-PURCHASE-001`) |
| View | `cbpos/ui/views/reorder_view.py` | `ReorderView` | 300 | `purchase_order_service, stock_service` | — |
| View | `cbpos/ui/views/reports/filter_widget.py` | `FilterWidget` | 275 | `—` | — |
| View | `cbpos/ui/views/reports/pandas_model.py` | `PandasModel` | 189 | `theme_service` | — |
| View | `cbpos/ui/views/reports/report_viewer.py` | `ReportWorker, ReportViewer` | 822 | `auth_service, config_service, export_service, report_service, tax_service` | worker lifecycle |
| View | `cbpos/ui/views/sales_view.py` | `SalesView` | 2530 | `auth_service, cart_audit_service, cart_autosave_service, cart_service, cash_drawer_service, config_service, customer_service, feature_flags, logging_service, payment_service, printer_service, product_service, proforma_service, sales_receipt_builder, scale_service, shift_service, sound_service, suspended_transaction_service, tax_invoice_service, tax_service, theme_service, transaction_service` | responsibility clusters mapped; synchronous sale commit on UI thread confirmed (`U0-SALES-001`) |
| Settings page | `cbpos/ui/views/settings_pages/__init__.py` | `_SettingsPagesPackage` | 63 | `—` | — |
| Settings page | `cbpos/ui/views/settings_pages/base.py` | `SettingsPage` | 268 | `config_service` | — |
| Settings page | `cbpos/ui/views/settings_pages/document.py` | `DocumentPage` | 178 | `document_service` | — |
| Settings page | `cbpos/ui/views/settings_pages/features.py` | `FeaturesPage` | 171 | `auth_service, feature_flags` | — |
| Settings page | `cbpos/ui/views/settings_pages/hardware.py` | `HardwarePage` | 481 | `hardware_test_service` | — |
| Settings page | `cbpos/ui/views/settings_pages/network.py` | `NetworkPage` | 1579 | `auth_service, config_service, database_setup_service, migration_service, schema_migration_service, sync_terminal_service, theme_service` | responsibility review (≥1,000 lines); blocking DB/network orchestration on UI thread confirmed (`U0-SETTINGS-002`) |
| Settings page | `cbpos/ui/views/settings_pages/receipt.py` | `ReceiptPage` | 834 | `config_service, receipt_builder, receipt_font_service, receipt_logo_service, warranty_service` | — |
| Settings page | `cbpos/ui/views/settings_pages/sales_tax.py` | `SalesTaxPage` | 466 | `config_service, tax_service` | — |
| Settings page | `cbpos/ui/views/settings_pages/shop_info.py` | `ShopInfoPage` | 311 | `language_service` | — |
| Settings page | `cbpos/ui/views/settings_pages/system.py` | `SystemPage` | 281 | `—` | — |
| View | `cbpos/ui/views/settings_view.py` | `SettingsView` | 640 | `config_service, permission_service, scheduler_service, settings_audit_service, theme_service` | — |
| View | `cbpos/ui/views/stock_take_view.py` | `StockCountItemModel, CountedDelegate, StockTakeView` | 1219 | `category_service, product_service, stock_count_service, theme_service` | responsibility review (≥1,000 lines) |
| View | `cbpos/ui/views/user_view.py` | `UserView` | 489 | `user_service` | — |
| View | `cbpos/ui/views/warranty_claims_board_view.py` | `WarrantyClaimsBoardView, WarrantyClaimsBoardDialog` | 1001 | `auth_service, warranty_claim_receipt_builder, warranty_claim_service, warranty_dto` | responsibility review (≥1,000 lines) |
| View | `cbpos/ui/views/warranty_policies_view.py` | `WarrantyPoliciesView` | 351 | `auth_service, permission_service, warranty_service` | — |
| Reusable widget | `cbpos/ui/widgets/action_panel.py` | `ActionBtn, SectionLabel, ActionPanel` | 462 | `theme_service` | — |
| Reusable widget | `cbpos/ui/widgets/charts.py` | `VerticalBarChart, DonutChart, HorizontalBarChart` | 478 | `theme_service` | — |
| Reusable widget | `cbpos/ui/widgets/collapsible_sidebar.py` | `CollapsibleSidebar` | 387 | `config_service, theme_service` | — |
| Reusable widget | `cbpos/ui/widgets/custom_widgets.py` | `SidebarButton` | 124 | `theme_service` | — |
| Reusable widget | `cbpos/ui/widgets/date_range_picker.py` | `DateRangePicker` | 264 | `—` | — |
| Reusable widget | `cbpos/ui/widgets/decimal_line_edit.py` | `DecimalLineEdit` | 56 | `—` | — |
| Reusable widget | `cbpos/ui/widgets/denomination_widget.py` | `DenominationWidget` | 119 | `config_service` | — |
| Reusable widget | `cbpos/ui/widgets/elided_label.py` | `ElidedLabel` | 49 | `—` | — |
| Reusable widget | `cbpos/ui/widgets/empty_state_widget.py` | `EmptyStateWidget` | 98 | `theme_service` | — |
| Reusable widget | `cbpos/ui/widgets/flow_layout.py` | `FlowLayout` | 117 | `—` | — |
| Reusable widget | `cbpos/ui/widgets/form_card.py` | `FormCard` | 56 | `—` | — |
| Reusable widget | `cbpos/ui/widgets/help_icon_button.py` | `HelpIconButton` | 57 | `—` | — |
| Reusable widget | `cbpos/ui/widgets/info_card.py` | `InfoCard` | 84 | `—` | — |
| Reusable widget | `cbpos/ui/widgets/loading_overlay.py` | `LoadingOverlay` | 109 | `—` | — |
| Reusable widget | `cbpos/ui/widgets/modal_dimmer.py` | `ModalDimmer, _IdKeyedDict, ModalDimmerManager` | 285 | `theme_service` | — |
| Reusable widget | `cbpos/ui/widgets/order_bar.py` | `OrderBar` | 135 | `suspended_transaction_service` | — |
| Reusable widget | `cbpos/ui/widgets/page_header.py` | `PageHeader` | 68 | `theme_service` | — |
| Reusable widget | `cbpos/ui/widgets/pagination_widget.py` | `PaginationWidget` | 175 | `—` | — |
| Reusable widget | `cbpos/ui/widgets/read_only_banner.py` | `ReadOnlyBanner` | 44 | `—` | — |
| Reusable widget | `cbpos/ui/widgets/receipt_preview_widget.py` | `ReceiptPreviewWidget` | 426 | `receipt_font_service` | — |
| Reusable widget | `cbpos/ui/widgets/side_menu.py` | `NavTile, IconButton, SideMenu` | 514 | `permission_service, theme_service, warranty_service` | — |
| Reusable widget | `cbpos/ui/widgets/status_pill_delegate.py` | `StatusPillDelegate` | 94 | `—` | — |
| Reusable widget | `cbpos/ui/widgets/sync_status_widget.py` | `SyncDetailsDialog, SyncStatusWidget` | 395 | `config_service, sync_terminal_service` | — |
| Reusable widget | `cbpos/ui/widgets/table_helpers.py` | `_ColumnModeKeeper, RelativeTimeTableWidgetItem` | 304 | `—` | — |
| Reusable widget | `cbpos/ui/widgets/wheel_guard.py` | `_WheelGuard` | 65 | `—` | — |
| UI infrastructure | `cbpos/ui/workers.py` | `_BackgroundJobs, CsvImportWorker, BackupWorker, BackupListWorker, RestoreWorker, VerifyBackupWorker, VacuumWorker, PrinterTestWorker, DrawerTestWorker, IntegrityCheckWorker, ExportWorker, AutocompleteLoadWorker, LabelProductLoaderWorker, ReportPrintWorker, ReportEmailWorker, SyncTestWorker, ReloadCatalogWorker, PinCheckWorker, TaxInvoiceArtifactWorker, WarrantyCardPdfWorker, WarrantyReprintWorker, WarrantyExportPdfWorker, CartAutosaveWorker` | 1084 | `auth_service, backup_service, cart_autosave_service, config_service, email_service, export_service, hardware_test_service, maintenance_service, receipt_reprint_service, tax_invoice_service, warranty_card_builder, warranty_service` | responsibility review (≥1,000 lines); worker lifecycle |

## Helper-only UI modules

These modules have no top-level class but can still own styling, formatting, navigation, or lifecycle behavior:

- `cbpos/ui/app_restart.py`
- `cbpos/ui/constants.py`
- `cbpos/ui/hardware_test_feedback.py`
- `cbpos/ui/refund_messages.py`
- `cbpos/ui/resources/status_colors.py`
- `cbpos/ui/startup_splash.py`
- `cbpos/ui/styles/style_helpers.py`
- `cbpos/ui/styles/tokens.py`
- `cbpos/ui/utils/layout_helpers.py`
- `cbpos/ui/utils/style_helpers.py`
- `cbpos/ui/utils/table_helpers.py`
- `cbpos/ui/widgets/dialog_footer.py`

## Verification backlog

- Trace actual reachability and permission gates from `MainWindow`, `SideMenu`, `ManagementView`, and `SettingsView`.
- Mark every class as user-visible surface, nested surface, reusable control, worker/adapter, or dead/unreachable.
- Add loading, empty, validation, error, permission-denied, cancellation, success, and re-entry states per reachable surface.
- Record dark/light and EN/SI/TA evidence at 1366×768 in the per-screen audit files.
- Convert direct-DB and worker-lifecycle flags into findings only after tracing current callers and execution paths.
