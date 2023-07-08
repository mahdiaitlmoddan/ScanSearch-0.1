from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QPushButton, QLabel, QCheckBox, QLineEdit, QProgressBar, QStatusBar, QFileDialog, QHeaderView
from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem
from PyQt6.QtGui import QAction
from PyQt6.QtCore import QThread, pyqtSignal
import sys
import os
import string
from pathlib import Path
import sqlite3


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db_manager = None

        # Create the central widget and layout
        self.central_widget = QWidget()
        self.layout = QVBoxLayout(self.central_widget)

        # Create the GUI elements
        self.search_box = QLineEdit()
        self.scan_button = QPushButton("Scan")
        self.checkbox_system_files = QCheckBox("Include system files")
        self.checkbox_hidden_files = QCheckBox("Include hidden files")
        self.result_box = QTableWidget()
        self.result_box.setColumnCount(5)  # Adjust this to fit your data
        self.result_box.setHorizontalHeaderLabels(['nbr', 'Name', 'Path', 'Size', 'Type'])
        self.result_box.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.result_box.setSortingEnabled(True)

        # Add the elements to the layout
        self.layout.addWidget(self.search_box)
        self.layout.addWidget(self.scan_button)
        self.layout.addWidget(self.checkbox_system_files)
        self.layout.addWidget(self.checkbox_hidden_files)
        self.layout.addWidget(self.result_box)

        # Add central widget to main window
        self.setCentralWidget(self.central_widget)

        # Create a status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # Create actions for the file menu
        self.new_db_action = QAction("New Database", self)
        self.open_db_action = QAction("Open Database", self)
        self.save_db_action = QAction("Save Database", self)

        # Create the file menu and add actions
        self.file_menu = self.menuBar().addMenu("File")
        self.file_menu.addAction(self.new_db_action)
        self.file_menu.addAction(self.open_db_action)
        self.file_menu.addAction(self.save_db_action)

        # Connect the buttons and actions to methods
        self.scan_button.clicked.connect(self.scan_drives)
        self.new_db_action.triggered.connect(self.new_database)
        self.open_db_action.triggered.connect(self.open_database)
        self.save_db_action.triggered.connect(self.save_database)

        self.search_box.returnPressed.connect(self.search_files)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)

        self.layout.addWidget(self.progress_bar)


    def get_drive_paths(self):
        drive_paths = [f"{d}:\\" for d in string.ascii_uppercase if Path(f"{d}:\\").exists()]
        return drive_paths

    def new_database(self):
        db_path, _ = QFileDialog.getSaveFileName(self, "New Database")
        if db_path:  # Ensure a file was selected
            self.db_manager = DatabaseManager(db_path)
            self.db_manager.create_table()
            self.status_bar.showMessage(f"Created new database: {db_path}")


    def open_database(self):
        db_path, _ = QFileDialog.getOpenFileName(self, "Open Database")
        if db_path:  # Ensure a file was selected
            self.db_manager = DatabaseManager(db_path)
            self.status_bar.showMessage(f"Opened database: {db_path}")

    def save_database(self):
        if self.db_manager is None:
            self.status_bar.showMessage("No database selected!")
            return

        self.db_manager.conn.commit()
        self.status_bar.showMessage("Database saved!")

    def scan_drives(self):
        if self.db_manager is None:
            self.status_bar.showMessage("No database selected!")
            return

        # Get the paths of the drives to scan
        drive_paths = self.get_drive_paths()

        # Create and start the worker thread
        self.scan_worker = ScanWorker(drive_paths, self.db_manager)

        self.scan_worker.file_scanned.connect(self.on_file_scanned)
        self.scan_worker.scan_completed.connect(self.on_scan_completed)
        self.scan_worker.start()

    def on_file_scanned(self, file_info):
        self.progress_bar.setValue(self.progress_bar.value() + 1)
        self.db_manager.insert_file(*file_info)

        total_files = self.progress_bar.maximum()
        if total_files != 0:
            percentage = int((self.progress_bar.value() / total_files) * 100)
            self.progress_bar.setFormat(f"{percentage}%")


    def on_scan_completed(self):
        self.status_bar.showMessage("Scan completed!")
        self.search_files()
        self.progress_bar.setFormat("%p%")

    def search_files(self):
        if self.db_manager is None:
            self.status_bar.showMessage("No database selected!")
            return

        query = self.search_box.text()
        results = self.db_manager.query_files(query)
        self.result_box.setRowCount(0)  # Clear the table
        for row_number, result in enumerate(results):
            self.result_box.insertRow(row_number)  # Insert a new row
            for column_number, data in enumerate(result):
                if column_number == 3:  # If this is the size column
                    data = round(data / 1024 / 1024, 2)  # Convert to MB
                item = QTableWidgetItem(str(data))
                self.result_box.setItem(row_number, column_number, item)  # Add data to the row

    def closeEvent(self, event):
        if self.db_manager is not None:
            self.db_manager.close()


class ScanWorker(QThread):
    file_scanned = pyqtSignal(tuple)
    scan_completed = pyqtSignal()

    def __init__(self, paths, db_manager):
        super().__init__()
        self.paths = paths
        self.db_manager = db_manager

    def run(self):
        total_files = 0
        for path in self.paths:
            total_files += self.scan_dir(path)
        self.db_manager.commit()  # Commit the changes after scanning
        self.scan_completed.emit()
        self.file_scanned.emit(("Total Files Scanned:", total_files))

    def scan_dir(self, path):
        file_count = 0
        for dirpath, _, filenames in os.walk(path):
            for filename in filenames:
                try:
                    file_path = os.path.join(dirpath, filename)
                    file_size = os.path.getsize(file_path)
                    _, file_type = os.path.splitext(filename)

                    # Emit the signal with a tuple containing information about the scanned file
                    self.file_scanned.emit((filename, file_path, file_size, file_type))
                    file_count += 1

                except (OSError, PermissionError):
                    pass

        return file_count


class DatabaseManager:
    def __init__(self, db_path):
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()

    def create_table(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                path TEXT NOT NULL,
                size INTEGER NOT NULL,
                type TEXT NOT NULL
            )
        ''')
        self.conn.commit()

    def insert_file(self, name, path, size, file_type):
        self.cursor.execute('''
            INSERT INTO files (name, path, size, type) VALUES (?, ?, ?, ?)
        ''', (name, path, size, file_type))

    def commit(self):
        self.conn.commit()

    def query_files(self, query, order_by='name'):
        # Validate the 'order_by' parameter
        allowed_order_by = ['name', 'path', 'size', 'type']
        if order_by not in allowed_order_by:
            raise ValueError(f"Invalid order_by value: {order_by}")

        # Perform the SQL query
        self.cursor.execute(f'''
            SELECT * FROM files WHERE name LIKE ? ORDER BY {order_by}
        ''', (f"%{query}%",))
        return self.cursor.fetchall()

    def close(self):
        self.conn.close()
        print("Database closed")


# Create a Qt application
app = QApplication(sys.argv)

# Create the main window and show it
window = MainWindow()
window.show()

# Run the Qt application
sys.exit(app.exec())
