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

    # Admin
    ADMIN_MANAGE_USERS = "admin.manage_users"
    ADMIN_MANAGE_ROLES = "admin.manage_roles"
    ADMIN_SETTINGS = "admin.settings"

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
            "Admin": [
                cls.ADMIN_MANAGE_USERS,
                cls.ADMIN_MANAGE_ROLES,
                cls.ADMIN_SETTINGS,
            ],
        }
