import sys
from PySide6.QtWidgets import QApplication
from app.ui import MainWindow

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("DupSnap")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
