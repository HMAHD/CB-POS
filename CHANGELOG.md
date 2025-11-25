# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0] - 2025-11-25
### Added
- Initial project structure scaffolding.
- Configuration files (.gitignore, requirements.txt).
- Database layer (`core/database.py`) with Singleton pattern and SQLAlchemy 2.0.
- Domain models (`core/models/__init__.py`) for User, Category, Product, Sale, SaleItem.
- Seeding script (`scripts/seed.py`) with Sri Lankan retail data.
- Authentication Service (`core/services/auth_service.py`) with PIN hashing.
- Global Theme (`ui/styles/theme.qss`) implementing "Ceylon Byte" industrial design.
- Login UI (`ui/views/login_view.py`) with custom Numpad and Split Screen layout.
- Main Window (`ui/main_window.py`) with StackedWidget for view management.
- Font Integration: Added support for "Noto Sans", "Noto Sans Sinhala", and "Noto Sans Tamil" loaded from `cbpos/assets/fonts`.
- Sales Terminal (`ui/views/sales_view.py`) with Cart Table, Barcode Input, and Totals.
- Product Service (`core/services/product_service.py`) for inventory lookup.
- Cart Service (`core/services/cart_service.py`) for managing sale state.
- Checkout Engine:
    -   Tax Service (`core/services/tax_service.py`) for backward tax calculation.
    -   Payment Dialog (`ui/dialogs/payment_dialog.py`) for processing payments.
    -   Transaction Service (`core/services/transaction_service.py`) for atomic sales persistence.
