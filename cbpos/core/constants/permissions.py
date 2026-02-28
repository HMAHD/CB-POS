ADMIN_ROLE_NAME = "Admin"

CRITICAL_ADMIN_PERMISSIONS = ["manage_users", "manage_permissions"]


class Permissions:
    # Sales Group
    SALES_VIEW = "sales.view"
    SALES_ADD_ITEM = "sales.add_item"
    SALES_VOID = "sales.void_item"
    SALES_DISCOUNT = "sales.discount"
    SALES_CHANGE_PRICE = "sales.change_price"

    # Inventory Group
    INVENTORY_VIEW = "inventory.view"
    INVENTORY_EDIT = "inventory.edit"
    INVENTORY_STOCK_ADJUST = "inventory.stock_adjust"

    # Reports
    REPORTS_VIEW_SALES = "reports.view_sales"
    REPORTS_VIEW_PROFIT = "reports.view_profit"

    # Documents
    DOCUMENTS_VIEW = "documents.view"
    DOCUMENTS_CREATE_PROFORMA = "documents.create_proforma"
    DOCUMENTS_CONVERT_PROFORMA = "documents.convert_proforma"

    # Data Safety
    DATA_SAFETY_BACKUP = "data_safety.backup"
    DATA_SAFETY_RESTORE = "data_safety.restore"
    DATA_SAFETY_MAINTENANCE = "data_safety.maintenance"

    # Purchase
    PURCHASE_VIEW = "purchase.view"
    PURCHASE_CREATE_GRN = "purchase.create_grn"
    PURCHASE_MAKE_PAYMENT = "purchase.make_payment"

    # Stock Take
    STOCK_TAKE_VIEW = "stock_take.view"
    STOCK_TAKE_CREATE = "stock_take.create"
    STOCK_TAKE_APPROVE = "stock_take.approve"

    # Admin
    ADMIN_MANAGE_USERS = "admin.manage_users"
    ADMIN_MANAGE_ROLES = "admin.manage_roles"
    ADMIN_SETTINGS = "admin.settings"
    ADMIN_TOOLS = "admin.tools"

    @classmethod
    def get_all(cls):
        return [value for name, value in vars(cls).items() if name.isupper()]

    @classmethod
    def get_groups(cls):
        return {
            "Sales": [
                cls.SALES_VIEW,
                cls.SALES_ADD_ITEM,
                cls.SALES_VOID,
                cls.SALES_DISCOUNT,
                cls.SALES_CHANGE_PRICE,
            ],
            "Inventory": [
                cls.INVENTORY_VIEW,
                cls.INVENTORY_EDIT,
                cls.INVENTORY_STOCK_ADJUST,
            ],
            "Reports": [cls.REPORTS_VIEW_SALES, cls.REPORTS_VIEW_PROFIT],
            "Documents": [
                cls.DOCUMENTS_VIEW,
                cls.DOCUMENTS_CREATE_PROFORMA,
                cls.DOCUMENTS_CONVERT_PROFORMA,
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
            ],
            "Stock Take": [
                cls.STOCK_TAKE_VIEW,
                cls.STOCK_TAKE_CREATE,
                cls.STOCK_TAKE_APPROVE,
            ],
            "Admin": [
                cls.ADMIN_MANAGE_USERS,
                cls.ADMIN_MANAGE_ROLES,
                cls.ADMIN_SETTINGS,
                cls.ADMIN_TOOLS,
            ],
        }
