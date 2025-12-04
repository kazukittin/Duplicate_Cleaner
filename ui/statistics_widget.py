from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                               QDialog, QDialogButtonBox, QGridLayout)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QPen
import os

class StatisticsWidget(QWidget):
    """Widget to display scan statistics"""
    
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        
        # Title
        title = QLabel("スキャン統計")
        title.setStyleSheet("font-weight: bold; font-size: 14pt;")
        title.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(title)
        
        # Stats grid
        self.stats_grid = QGridLayout()
        self.layout.addLayout(self.stats_grid)
        
        self.layout.addStretch()
    
    def set_statistics(self, stats):
        """Set and display statistics
        
        Args:
            stats: dict with keys:
                - total_groups: int
                - blur_groups: int
                - duplicate_groups: int
                - total_delete_candidates: int
                - total_delete_size: int (bytes)
                - total_files_scanned: int
        """
        # Clear existing
        for i in reversed(range(self.stats_grid.count())):
            self.stats_grid.itemAt(i).widget().setParent(None)
        
        row = 0
        
        # Total files scanned
        self.add_stat_row(row, "スキャンしたファイル:", 
                         f"{stats.get('total_files_scanned', 0):,} ファイル")
        row += 1
        
        # Total groups
        self.add_stat_row(row, "検出されたグループ:", 
                         f"{stats.get('total_groups', 0)} グループ")
        row += 1
        
        # Blur groups
        self.add_stat_row(row, "  - ブレ画像:", 
                         f"{stats.get('blur_groups', 0)} グループ",
                         indent=True)
        row += 1
        
        # Duplicate groups
        self.add_stat_row(row, "  - 重複・類似:", 
                         f"{stats.get('duplicate_groups', 0)} グループ",
                         indent=True)
        row += 1
        
        # Separator
        separator = QLabel("─" * 40)
        separator.setStyleSheet("color: #ccc;")
        self.stats_grid.addWidget(separator, row, 0, 1, 2)
        row += 1
        
        # Delete candidates
        self.add_stat_row(row, "削除候補ファイル:", 
                         f"{stats.get('total_delete_candidates', 0):,} ファイル",
                         highlight=True)
        row += 1
        
        # Size savings
        size_mb = stats.get('total_delete_size', 0) / (1024 * 1024)
        size_gb = size_mb / 1024
        
        if size_gb >= 1:
            size_str = f"{size_gb:.2f} GB"
        else:
            size_str = f"{size_mb:.2f} MB"
        
        self.add_stat_row(row, "節約可能な容量:", size_str, highlight=True)
        row += 1
    
    def add_stat_row(self, row, label_text, value_text, indent=False, highlight=False):
        """Add a statistics row"""
        label = QLabel(label_text)
        if indent:
            label.setStyleSheet("margin-left: 20px; color: #666;")
        elif highlight:
            label.setStyleSheet("font-weight: bold; color: #d32f2f;")
        
        value = QLabel(value_text)
        value.setAlignment(Qt.AlignRight)
        if highlight:
            value.setStyleSheet("font-weight: bold; font-size: 12pt; color: #d32f2f;")
        
        self.stats_grid.addWidget(label, row, 0)
        self.stats_grid.addWidget(value, row, 1)


class StatisticsDialog(QDialog):
    """Dialog to show statistics"""
    
    def __init__(self, stats, parent=None):
        super().__init__(parent)
        self.setWindowTitle("スキャン統計")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout(self)
        
        self.stats_widget = StatisticsWidget()
        self.stats_widget.set_statistics(stats)
        layout.addWidget(self.stats_widget)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
