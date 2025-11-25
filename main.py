import sys
import os
from PyQt6.QtWidgets import QApplication
from cbpos.ui.main_window import MainWindow


def main():
    # Ensure high DPI scaling
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

    app = QApplication(sys.argv)
    app.setApplicationName("CB POS")

    # Load Fonts
    from PyQt6.QtGui import QFontDatabase

    font_dir = os.path.join(os.path.dirname(__file__), "cbpos", "assets", "fonts")
    if os.path.exists(font_dir):
        for root, dirs, files in os.walk(font_dir):
            for filename in files:
                if filename.lower().endswith((".ttf", ".otf")):
                    QFontDatabase.addApplicationFont(os.path.join(root, filename))

    window = MainWindow()
    window.showMaximized()  # Industrial apps usually run full screen

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
