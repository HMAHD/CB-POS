"""Terminal role guards protecting shared catalog from till mutation (#869)."""

from cbpos.core.services.config_service import ConfigService


class CatalogReadOnlyError(ValueError):
    """Raised when an attempt is made to mutate catalog entities on a till terminal."""

    code = "catalog_read_only"

    def __init__(self, message: str | None = None):
        super().__init__(
            message
            or "Cannot modify catalog on a till. Add or change products, prices, suppliers and users on the Main PC."
        )


def catalog_is_read_only() -> bool:
    """Return True if the local machine is running in 'terminal' mode (till)."""
    return ConfigService.get("terminal_mode") == "terminal"


def require_catalog_writable() -> None:
    """Raise CatalogReadOnlyError if the local machine is running as a till ('terminal' mode)."""
    if catalog_is_read_only():
        raise CatalogReadOnlyError()
