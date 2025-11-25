import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel
from PyQt6.QtCore import Qt

def main():
    app = QApplication(sys.argv)

    window = QMainWindow()
    window.setWindowTitle("CB POS - Industrial Python")
    window.setGeometry(100, 100, 800, 600)

    # Placeholder dark theme (Navy Blue)
    window.setStyleSheet("background-color: #000080; color: white;")

    label = QLabel("Hello World - Industrial Python", window)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    window.setCentralWidget(label)

    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
