from pathlib import Path


class Config:
    APP_NAME = "CB POS"
    VERSION = "1.0.0"
    BASE_DIR = Path(__file__).parent.parent
    DB_URI = f"sqlite:///{BASE_DIR / 'cbpos.db'}"  # noqa: E231
    # Theme Colors
    COLOR_NAVY = "#001F3F"
    COLOR_CYAN = "#00BCEB"
