ADMIN_ROLE_NAME = "Admin"


class Permissions:
    """Permission code constants, checked via `check_permission_with_override()`.

    Each value is a `"group.action"` string stored on `Role`/`User` permission
    grants. Grouped below by feature area; `get_groups()` mirrors this grouping
    for UI display (e.g. the Role Manager dialog's permission checklist).
    """

    # Sales Group
    SALES_VIEW = "sales.view"
    SALES_ADD_ITEM = "sales.add_item"
    SALES_VOID = "sales.void_item"
    SALES_DISCOUNT = "sales.discount"
    SALES_CHANGE_PRICE = "sales.change_price"
    SALES_REFUND = "sales.refund"

    # Inventory Group
    INVENTORY_VIEW = "inventory.view"
    INVENTORY_EDIT = "inventory.edit"
    INVENTORY_DELETE = "inventory.delete"
    INVENTORY_STOCK_ADJUST = "inventory.stock_adjust"

    # Reports
    REPORTS_VIEW_SALES = "reports.view_sales"
    REPORTS_VIEW_PROFIT = "reports.view_profit"
    REPORTS_EXPORT = "reports.export"

    # Documents
    DOCUMENTS_VIEW = "documents.view"
    DOCUMENTS_CREATE_PROFORMA = "documents.create_proforma"
    DOCUMENTS_CONVERT_PROFORMA = "documents.convert_proforma"
    DOCUMENTS_VOID = "documents.void"
    DOCUMENTS_TRANSFER = "documents.transfer"

    # Credit
    CREDIT_RECEIVE_PAYMENT = "credit.receive_payment"
    CREDIT_ADJUST_BALANCE = "credit.adjust_balance"

    # Data Safety
    DATA_SAFETY_BACKUP = "data_safety.backup"
    DATA_SAFETY_RESTORE = "data_safety.restore"
    DATA_SAFETY_MAINTENANCE = "data_safety.maintenance"

    # Purchase
    PURCHASE_VIEW = "purchase.view"
    PURCHASE_CREATE_GRN = "purchase.create_grn"
    PURCHASE_MAKE_PAYMENT = "purchase.make_payment"
    PURCHASE_ADJUST_PAYABLE = "purchase.adjust_payable"

    # Stock Take
    STOCK_TAKE_VIEW = "stock_take.view"
    STOCK_TAKE_CREATE = "stock_take.create"
    STOCK_TAKE_APPROVE = "stock_take.approve"

    # Cash
    CASH_OPEN_DRAWER = "cash.open_drawer"

    # Screens: who sees Management / Settings in the side menu (#549)
    MANAGEMENT_VIEW = "management.view"
    SETTINGS_VIEW = "settings.view"

    # Admin
    ADMIN_MANAGE_USERS = "admin.manage_users"
    ADMIN_MANAGE_ROLES = "admin.manage_roles"
    ADMIN_SETTINGS = "admin.settings"
    ADMIN_TOOLS = "admin.tools"

    @classmethod
    def get_all(cls):
        """Return every permission code as a flat list (for "grant all" / validation)."""
        return [value for name, value in vars(cls).items() if name.isupper()]

    @classmethod
    def get_groups(cls):
        """Return permission codes grouped by feature area, keyed by display label."""
        return {
            "Sales": [
                cls.SALES_VIEW,
                cls.SALES_ADD_ITEM,
                cls.SALES_VOID,
                cls.SALES_DISCOUNT,
                cls.SALES_CHANGE_PRICE,
                cls.SALES_REFUND,
            ],
            "Inventory": [
                cls.INVENTORY_VIEW,
                cls.INVENTORY_EDIT,
                cls.INVENTORY_DELETE,
                cls.INVENTORY_STOCK_ADJUST,
            ],
            "Reports": [cls.REPORTS_VIEW_SALES, cls.REPORTS_VIEW_PROFIT, cls.REPORTS_EXPORT],
            "Documents": [
                cls.DOCUMENTS_VIEW,
                cls.DOCUMENTS_CREATE_PROFORMA,
                cls.DOCUMENTS_CONVERT_PROFORMA,
                cls.DOCUMENTS_VOID,
                cls.DOCUMENTS_TRANSFER,
            ],
            "Credit": [
                cls.CREDIT_RECEIVE_PAYMENT,
                cls.CREDIT_ADJUST_BALANCE,
            ],
            "Data Safety": [
                cls.DATA_SAFETY_BACKUP,
                cls.DATA_SAFETY_RESTORE,
                cls.DATA_SAFETY_MAINTENANCE,
            ],
            "Purchase": [
                cls.PURCHASE_VIEW,
                cls.PURCHASE_CREATE_GRN,
                cls.PURCHASE_MAKE_PAYMENT,
                cls.PURCHASE_ADJUST_PAYABLE,
            ],
            "Stock Take": [
                cls.STOCK_TAKE_VIEW,
                cls.STOCK_TAKE_CREATE,
                cls.STOCK_TAKE_APPROVE,
            ],
            "Cash": [
                cls.CASH_OPEN_DRAWER,
            ],
            "Screens": [
                cls.MANAGEMENT_VIEW,
                cls.SETTINGS_VIEW,
            ],
            "Admin": [
                cls.ADMIN_MANAGE_USERS,
                cls.ADMIN_MANAGE_ROLES,
                cls.ADMIN_SETTINGS,
                cls.ADMIN_TOOLS,
            ],
        }


# Which permissions show each sidebar tab of Management and Settings -- the one definition of
# screen access (#728). A user sees a tab if they hold any of its permissions, and the side menu
# offers a screen exactly when the user would see at least one of its tabs, so the menu can never
# open a screen with nothing usable inside (#549 opened Management for admin.manage_roles while
# Users was gated on admin.manage_users only).
#
# General tabs are open to everyone the screen lets in: its own "open" permission, or an admin
# permission that is used inside it.
_EVERYONE_IN_MANAGEMENT = (
    Permissions.MANAGEMENT_VIEW,
    Permissions.ADMIN_MANAGE_USERS,
    Permissions.ADMIN_MANAGE_ROLES,
)
MANAGEMENT_TAB_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "dashboard": _EVERYONE_IN_MANAGEMENT,
    "inventory": _EVERYONE_IN_MANAGEMENT,
    "purchasing": _EVERYONE_IN_MANAGEMENT,
    "credit_book": _EVERYONE_IN_MANAGEMENT,
    "reports": _EVERYONE_IN_MANAGEMENT,
    "documents": _EVERYONE_IN_MANAGEMENT,
    "users": (Permissions.ADMIN_MANAGE_USERS, Permissions.ADMIN_MANAGE_ROLES),
    "pricelists": (Permissions.ADMIN_MANAGE_USERS,),
    "promotions": (Permissions.ADMIN_MANAGE_USERS,),
    "stock_take": (Permissions.ADMIN_MANAGE_USERS,),
    "reorder": _EVERYONE_IN_MANAGEMENT,
}

_EVERYONE_IN_SETTINGS = (Permissions.SETTINGS_VIEW, Permissions.ADMIN_SETTINGS, Permissions.ADMIN_TOOLS)
SETTINGS_PAGE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "shop_info": _EVERYONE_IN_SETTINGS,
    "sales_tax": _EVERYONE_IN_SETTINGS,
    "documents": _EVERYONE_IN_SETTINGS,
    "hardware": _EVERYONE_IN_SETTINGS,
    "receipt": _EVERYONE_IN_SETTINGS,
    "system": _EVERYONE_IN_SETTINGS,
    "network": _EVERYONE_IN_SETTINGS,
    "payment_methods": _EVERYONE_IN_SETTINGS,
    "data_safety": (Permissions.ADMIN_SETTINGS,),
    "admin_tools": (Permissions.ADMIN_SETTINGS, Permissions.ADMIN_TOOLS),
}

# Never revocable from the Admin role -- PermissionService re-adds them on save (lockout guard).
CRITICAL_ADMIN_PERMISSIONS = [Permissions.ADMIN_MANAGE_USERS, Permissions.ADMIN_MANAGE_ROLES]
