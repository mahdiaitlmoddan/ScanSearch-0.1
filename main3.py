from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget,QComboBox,QLabel, QPushButton, QCheckBox, QLineEdit, QProgressBar, QStatusBar, QFileDialog, QHeaderView, QTableWidget, QTableWidgetItem
from PyQt6.QtCore import QRunnable, QObject, pyqtSignal, QThreadPool, Qt
from PyQt6.QtGui import QAction
import os
import string
import sqlite3
import ctypes
import time


FILE_ATTRIBUTE_HIDDEN = 0x2
FILE_ATTRIBUTE_SYSTEM = 0x4


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.scan_task = None

        self.central_widget = QWidget()
        self.layout = QVBoxLayout(self.central_widget)

        self.scan_button = QPushButton("Start Scan")
        self.scan_button.clicked.connect(self.start_scan)

        self.progress_bar = QProgressBar()

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Filename", "Filepath", "Size", "Type", "Date Created", "Date Modified"])

        self.search_box = QLineEdit()
        self.search_box.returnPressed.connect(self.search_files)

        self.system_files_checkbox = QCheckBox("Include system files")
        self.hidden_files_checkbox = QCheckBox("Include hidden files")

        self.layout.addWidget(self.scan_button)
        self.stop_scan_button = QPushButton("Stop Scan")
        self.stop_scan_button.clicked.connect(self.stop_scan)
        self.layout.addWidget(self.stop_scan_button)
        self.layout.addWidget(self.progress_bar)
        self.layout.addWidget(self.system_files_checkbox)
        self.layout.addWidget(self.hidden_files_checkbox)
        self.layout.addWidget(self.table)
        self.layout.addWidget(QLabel("Search:"))
        self.layout.addWidget(self.search_box)


        self.setCentralWidget(self.central_widget)

        self.db_conn = sqlite3.connect(":memory:")
        self.db_cursor = self.db_conn.cursor()
        self.db_cursor.execute("CREATE TABLE files (filename text, filepath text, size int, type text, date_created text, date_modified text)")

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.new_db_action = QAction("New Database", self)
        self.new_db_action.triggered.connect(self.new_database)

        self.open_db_action = QAction("Open Database", self)
        self.open_db_action.triggered.connect(self.open_database)

        self.save_db_action = QAction("Save Database", self)
        self.save_db_action.triggered.connect(self.save_database)

        self.file_menu = self.menuBar().addMenu("File")
        self.file_menu.addAction(self.new_db_action)
        self.file_menu.addAction(self.open_db_action)
        self.file_menu.addAction(self.save_db_action)



        self.sort_by_combo = QComboBox()
        self.sort_by_combo.addItem("Filename", "filename")
        self.sort_by_combo.addItem("Filepath", "filepath")
        self.sort_by_combo.addItem("Size", "size")
        self.sort_by_combo.addItem("Type", "type")
        self.sort_by_combo.addItem("Date Created", "date_created")
        self.sort_by_combo.addItem("Date Modified", "date_modified")
        self.sort_by_combo.currentIndexChanged.connect(self.sort_files)
        self.layout.addWidget(self.sort_by_combo)

        self.table.cellDoubleClicked.connect(self.open_file)

    def stop_scan(self):
        if self.scan_task is not None:
            self.scan_task.stop()
            self.scan_task = None

    def start_scan(self):
        if self.db_conn is None:
            self.status_bar.showMessage("No database selected!")
            return

        include_system_files = self.system_files_checkbox.isChecked()
        include_hidden_files = self.hidden_files_checkbox.isChecked()

        self.scan_task = ScanTask(include_system_files, include_hidden_files, size_min=1000, excluded_extensions=[".dat",".dll"])


        self.scan_task.signals.file_found.connect(self.on_file_found)
        self.scan_task.signals.progress.connect(self.on_progress)

        thread_pool = QThreadPool.globalInstance()
        thread_pool.start(self.scan_task)

    def on_file_found(self, filename, filepath, size, type_, date_created, date_modified):
        self.db_cursor.execute("INSERT INTO files VALUES (?, ?, ?, ?, ?, ?)", (filename, filepath, size, type_, date_created, date_modified))
        self.db_conn.commit()



    def on_progress(self, value, maximum):
        self.progress_bar.setMaximum(maximum)
        self.progress_bar.setValue(value)

    def search_files(self):
        query = self.search_box.text()
        self.db_cursor.execute("SELECT * FROM files WHERE filename LIKE ?", (f"%{query}%",))
        results = self.db_cursor.fetchall()

        self.update_table(results)

    def sort_files(self):
        sort_by = self.sort_by_combo.currentData()
        self.db_cursor.execute(f"SELECT * FROM files ORDER BY {sort_by}")
        results = self.db_cursor.fetchall()
        self.update_table(results)

    def update_table(self, data):
        self.table.setRowCount(0)
        for filename, filepath, size, type_, date_created, date_modified in data:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(filename))
            self.table.setItem(row, 1, QTableWidgetItem(filepath))
            self.table.setItem(row, 2, QTableWidgetItem(str(size)))
            self.table.setItem(row, 3, QTableWidgetItem(type_))
            self.table.setItem(row, 4, QTableWidgetItem(date_created))
            self.table.setItem(row, 5, QTableWidgetItem(date_modified))

    def new_database(self):
        db_path, _ = QFileDialog.getSaveFileName(self, "New Database")
        if db_path:  # Ensure a file was selected
            self.db_conn = sqlite3.connect(db_path)
            self.db_cursor = self.db_conn.cursor()
            self.db_cursor.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    filename text,
                    filepath text,
                    size int,
                    type text,
                    date_created text,
                    date_modified text
                )
            """)

            self.status_bar.showMessage(f"Created new database: {db_path}")

    def open_database(self):
        db_path, _ = QFileDialog.getOpenFileName(self, "Open Database")
        if db_path:  # Ensure a file was selected
            self.db_conn = sqlite3.connect(db_path)
            self.db_cursor = self.db_conn.cursor()
            self.status_bar.showMessage(f"Opened database: {db_path}")

    def save_database(self):
        if self.db_conn is None:
            self.status_bar.showMessage("No database selected!")
            return

        self.db_conn.commit()
        self.status_bar.showMessage("Database saved!")

    def open_file(self, row):
        filepath = self.table.item(row, 1).text()  # Column 1 is the filepath
        os.startfile(filepath)


class ScanTaskSignals(QObject):
    file_found = pyqtSignal(str, str, int, str, str, str)
    progress = pyqtSignal(int, int)


class ScanTask(QRunnable):
    def __init__(self, include_system_files, include_hidden_files, size_min=None, excluded_extensions=None):
        super().__init__()
        self.include_system_files = include_system_files
        self.include_hidden_files = include_hidden_files
        self.size_min = size_min
        self.excluded_extensions = excluded_extensions
        self.signals = ScanTaskSignals()
        self._stop = False

    def run(self):
        count = 0
        for drive_letter in string.ascii_uppercase:
            if os.path.exists(drive_letter + ":/"):
                for dirpath, dirnames, filenames in os.walk(drive_letter + ":/"):
                    if self._stop:  # Stop if the stop flag is set
                        return
                    for filename in filenames:
                        if self._stop:  # Stop if the stop flag is set
                            return
                        try:
                            filepath = os.path.join(dirpath, filename)

                            if (os.path.isfile(filepath) and
                                    (self.include_system_files or not self.is_system_file(filepath)) and
                                    (self.include_hidden_files or not self.is_hidden_file(filepath))):
                                size = os.path.getsize(filepath)
                                type_ = os.path.splitext(filename)[1]
                                date_created = time.ctime(os.path.getctime(filepath))
                                date_modified = time.ctime(os.path.getmtime(filepath))

                                self.signals.file_found.emit(filename, filepath, size, type_, date_created,
                                                             date_modified)
                                count += 1
                                self.signals.progress.emit(count,
                                                           1000000)  # Update progress. Total number is a placeholder.
                        except Exception as e:
                            pass
                    self.scan_dir(dirpath)  # Call self.scan_dir with dirpath, not self and path
                    if self._stop:  # Stop if the stop flag is set
                        return

    def stop(self):
        self._stop = True

    def scan_dir(self, path):
        for dirpath, _, filenames in os.walk(path):
            if self._stop:
                return

            for filename in filenames:
                if self._stop:
                    return

                try:
                    filepath = os.path.join(dirpath, filename)
                    size = os.path.getsize(filepath)
                    type_ = os.path.splitext(filename)[1]
                    date_created = time.ctime(os.path.getctime(filepath))
                    date_modified = time.ctime(os.path.getmtime(filepath))

                    if not self.include_system_files and self.is_system_file(filepath):
                        continue

                    if not self.include_hidden_files and self.is_hidden_file(filepath):
                        continue

                    if self.excluded_extensions and type_ in self.excluded_extensions:
                        continue

                    if self.size_min is not None and size < self.size_min:
                        continue

                    self.signals.file_found.emit(filename, filepath, size, type_, date_created, date_modified)

                except (OSError, PermissionError):
                    pass

    @staticmethod
    def is_system_file(filepath):
        return os.path.isfile(filepath) and (os.stat(filepath).st_file_attributes & FILE_ATTRIBUTE_SYSTEM)

    @staticmethod
    def is_hidden_file(filepath):
        return os.path.isfile(filepath) and (os.stat(filepath).st_file_attributes & FILE_ATTRIBUTE_HIDDEN)


class DatabaseManager:
    def __init__(self, db_path):
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                path TEXT NOT NULL,
                size INTEGER NOT NULL,
                type TEXT NOT NULL,
                date_created TEXT NOT NULL,
                date_modified TEXT NOT NULL
            )
        ''')
        self.conn.commit()


    def insert_file(self, name, path, size, type_, date_created, date_modified):
        self.cursor.execute('''
            INSERT INTO files (name, path, size, type, date_created, date_modified) VALUES (?, ?, ?, ?, ?, ?)
        ''', (name, path, size, type_, date_created, date_modified))
        self.conn.commit()

    def close(self):
        self.conn.close()

app = QApplication([])
window = MainWindow()
window.show()
app.exec()