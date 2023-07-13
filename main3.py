from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QWidget,
    QLabel, QPushButton, QCheckBox, QLineEdit,
    QProgressBar, QStatusBar, QFileDialog,
    QHeaderView, QTableWidget, QTableWidgetItem,
)
from PyQt6.QtCore import QThread, QSettings, Qt

from PyQt6.QtCore import pyqtSignal, QThreadPool
from PyQt6.QtGui import QAction

import os
import string
import sqlite3
import ctypes
import time
import re


# Thread for scanning
class ScannerThread(QThread):
    fileFound = pyqtSignal(str, str, int, str, str, str)
    progress = pyqtSignal(int, int)
    scanComplete = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.stopped = False

    def run(self):
        files = []
        total = 0
        for drive in string.ascii_uppercase:
            drive = drive + ":"
            for root, dirs, files in os.walk(drive):
                if self.stopped:
                    return
                for name in files:
                    path = os.path.join(str(root), str(name))
                    if not os.path.isfile(path):
                        continue
                    total += 1
                    size = os.path.getsize(path)
                    type_ = os.path.splitext(name)[1]
                    created = time.ctime(os.path.getctime(path))
                    modified = time.ctime(os.path.getmtime(path))
                    files.append((name, path, size, type_, created, modified))
                    self.fileFound.emit(name, path, size, type_, created, modified)
                    self.progress.emit(total, 10000)  # example max
        self.progress.emit(10000, 10000)  # scan complete
        self.scanComplete.emit()

    def stop(self):
        self.stopped = True


# Main window
class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.scanner = None  # Scanner thread

        # Settings
        self.settings = QSettings("MyApp", "ScanSearch")

        # Sort order dictionary
        self.sortOrder = {}

        # Setup UI
        self.setupUI()

        # Connect signals/slots
        self.connectSignalsSlots()

        # Init database
        self.initDb()

    def initDb(self):
        dbPath = self.settings.value("dbPath")
        if dbPath:
            self.db = DatabaseManager(dbPath)
        else:
            self.db = None

    def createDb(self):
        path, _ = QFileDialog.getSaveFileName(self, "Create Database", "", "SQLite Database (*.db *.sqlite)")
        if path:
            self.settings.setValue("dbPath", path)
            self.db = DatabaseManager(path)
            self.db.createTable()
            self.statusBar.showMessage("Created new database at " + path)

    def searchDatabase(self, query):
        # Get search text
        query = self.searchInput.text()

        # Search database
        if self.db:
            results = self.db.search(query)
        else:
            results = []

        # Update table
        self.updateTable(results)

    def updateTable(self, results):
        # Clear table
        self.table.setRowCount(0)

        # Add results
        for row in results:
            # Add row to table
            self.table.insertRow(self.table.rowCount())
            for i, item in enumerate(row):
                self.table.setItem(self.table.rowCount() - 1, i, QTableWidgetItem(str(item)))

    def saveDb(self):
        dbPath = self.settings.value("dbPath")

        if self.db and dbPath:
            self.db.conn.commit()
            self.statusBar.showMessage("Changes saved to database at " + dbPath)

        else:
            self.statusBar.showMessage("No database opened to save changes")

    def openDbDialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Database", "", "SQLite Database (*.db *.sqlite)")
        if path:
            self.settings.setValue("dbPath", path)
            self.db = DatabaseManager(path)
            self.statusBar.showMessage("Opened database at " + path)

    def setupUI(self):
        self.centralWidget = QWidget()
        self.layout = QVBoxLayout()

        # Buttons
        self.scanButton = QPushButton("Start Scan")
        self.stopButton = QPushButton("Stop Scan")

        # Progress bar
        self.progressBar = QProgressBar()

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        headers = ["Number", "Name", "Path", "Size", "Type", "Created", "Modified"]
        self.table.setHorizontalHeaderLabels(headers)

        # Search
        self.searchInput = QLineEdit()

        # Filters
        self.sysFilesCheckbox = QCheckBox("Include system files")
        self.hiddenFilesCheckbox = QCheckBox("Include hidden files")

        # Layout
        self.layout.addWidget(self.scanButton)
        self.layout.addWidget(self.stopButton)
        self.layout.addWidget(self.progressBar)
        self.layout.addWidget(self.sysFilesCheckbox)
        self.layout.addWidget(self.hiddenFilesCheckbox)
        self.layout.addWidget(self.table)
        self.layout.addWidget(QLabel("Search:"))
        self.layout.addWidget(self.searchInput)

        self.centralWidget.setLayout(self.layout)
        self.setCentralWidget(self.centralWidget)

        # Status bar
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)

        # Menu
        menu = self.menuBar()
        fileMenu = menu.addMenu("File")
        fileMenu.addAction("New Database", self.createDb)
        fileMenu.addAction("Open Database", self.openDbDialog)
        fileMenu.addAction("Save Database", self.saveDb)

    def connectSignalsSlots(self):
        self.scanButton.clicked.connect(self.startScan)
        self.stopButton.clicked.connect(self.stopScan)
        self.searchInput.textChanged.connect(self.searchDatabase)
        self.table.horizontalHeader().sectionClicked.connect(self.sortTable)

    def startScan(self):
        self.scanner = ScannerThread()
        self.scanner.fileFound.connect(self.fileFoundHandler)
        self.scanner.progress.connect(self.updateProgress)
        self.scanner.scanComplete.connect(self.saveScanResults)
        self.scanner.start()

    def stopScan(self):
        if self.scanner:
            self.scanner.stop()

    def fileFoundHandler(self, name, path, size, type_, created, modified):
        self.statusBar.showMessage(f"Found file {name}", 5000)

    def updateProgress(self, value, maximum):
        self.progressBar.setMaximum(maximum)
        self.progressBar.setValue(value)
        if value == maximum:
            self.statusBar.showMessage("Scan complete!", 5000)

    def sortTable(self, index):
        # Get sort column
        sortCol = self.table.horizontalHeaderItem(index).text()

        # Check if the column is already sorted
        if sortCol in self.sortOrder:
            # Reverse the sort order
            self.sortOrder[sortCol] = not self.sortOrder[sortCol]
        else:
            # Set the initial sort order
            self.sortOrder[sortCol] = False

        # Sort results
        if self.db:
            results = self.db.sort(sortCol, self.sortOrder[sortCol])
            self.updateTable(results)

    def saveScanResults(self):
        if not self.db:
            return

        # Clear existing data
        self.db.clearData()

        # Save scan results to the database
        for drive in string.ascii_uppercase:
            drive = drive + ":"
            for root, dirs, files in os.walk(drive):
                for name in files:
                    path = os.path.join(str(root), str(name))
                    if not os.path.isfile(path):
                        continue
                    size = os.path.getsize(path)
                    type_ = os.path.splitext(name)[1]
                    created = time.ctime(os.path.getctime(path))
                    modified = time.ctime(os.path.getmtime(path))
                    self.db.insertFile(name, path, size, type_, created, modified)

        self.statusBar.showMessage("Scan results saved to the database")

    def closeEvent(self, event):
        if self.db:
            self.db.close()

        event.accept()


class DatabaseManager:
    def __init__(self, dbPath):
        self.conn = sqlite3.connect(dbPath)
        self.cursor = self.conn.cursor()
        self.createTable()

    def createTable(self):
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS files (
          id INTEGER PRIMARY KEY,  
          name TEXT,
          path TEXT,
          size INT, 
          type TEXT,
          created TEXT,
          modified TEXT
        )
      """)

    def search(self, query):
        # Execute search query
        self.cursor.execute("SELECT * FROM files WHERE name LIKE ?", ('%' + query + '%',))

        # Fetch and return results
        return self.cursor.fetchall()

    def insertFile(self, name, path, size, type_, created, modified):
        # Insert file record
        self.cursor.execute("INSERT INTO files (name, path, size, type, created, modified) VALUES (?, ?, ?, ?, ?, ?)",
                            (name, path, size, type_, created, modified))
        self.conn.commit()

    def sort(self, column, reverse=False):
        # Sort the files based on the given column
        sort_order = "DESC" if reverse else "ASC"
        self.cursor.execute(f"SELECT * FROM files ORDER BY {column} {sort_order}")
        return self.cursor.fetchall()

    def clearData(self):
        # Clear existing data in the table
        self.cursor.execute("DELETE FROM files")
        self.conn.commit()

    def close(self):
        self.conn.close()


if __name__ == "__main__":
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec()