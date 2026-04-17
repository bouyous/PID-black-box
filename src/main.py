import sys
from pathlib import Path

# Allow imports from src/ without package install
sys.path.insert(0, str(Path(__file__).parent))

from PyQt6.QtWidgets import QApplication

from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("BlackBox Analyzer")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
