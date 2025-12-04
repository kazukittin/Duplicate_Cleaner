from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                               QCheckBox, QComboBox, QGroupBox, QPushButton)
from PySide6.QtCore import Signal

class FilterWidget(QWidget):
    """Widget for filtering groups"""
    filter_changed = Signal(dict)  # Emits filter criteria
    
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5)
        
        # Title
        title = QLabel("フィルタ")
        title.setStyleSheet("font-weight: bold; font-size: 12pt;")
        self.layout.addWidget(title)
        
        # Group Type Filter
        type_group = QGroupBox("グループタイプ")
        type_layout = QVBoxLayout()
        
        self.show_blur_cb = QCheckBox("ブレ画像")
        self.show_blur_cb.setChecked(True)
        self.show_blur_cb.toggled.connect(self.emit_filter)
        type_layout.addWidget(self.show_blur_cb)
        
        self.show_duplicate_cb = QCheckBox("重複・類似")
        self.show_duplicate_cb.setChecked(True)
        self.show_duplicate_cb.toggled.connect(self.emit_filter)
        type_layout.addWidget(self.show_duplicate_cb)
        
        type_group.setLayout(type_layout)
        self.layout.addWidget(type_group)
        
        # Status Filter
        status_group = QGroupBox("状態")
        status_layout = QVBoxLayout()
        
        self.show_with_delete_cb = QCheckBox("削除候補あり")
        self.show_with_delete_cb.setChecked(True)
        self.show_with_delete_cb.toggled.connect(self.emit_filter)
        status_layout.addWidget(self.show_with_delete_cb)
        
        self.show_unprocessed_cb = QCheckBox("未処理")
        self.show_unprocessed_cb.setChecked(True)
        self.show_unprocessed_cb.toggled.connect(self.emit_filter)
        status_layout.addWidget(self.show_unprocessed_cb)
        
        status_group.setLayout(status_layout)
        self.layout.addWidget(status_group)
        
        # Reset button
        self.reset_btn = QPushButton("フィルタをリセット")
        self.reset_btn.clicked.connect(self.reset_filters)
        self.layout.addWidget(self.reset_btn)
        
        self.layout.addStretch()
    
    def emit_filter(self):
        """Emit current filter criteria"""
        criteria = {
            'show_blur': self.show_blur_cb.isChecked(),
            'show_duplicate': self.show_duplicate_cb.isChecked(),
            'show_with_delete': self.show_with_delete_cb.isChecked(),
            'show_unprocessed': self.show_unprocessed_cb.isChecked(),
        }
        self.filter_changed.emit(criteria)
    
    def reset_filters(self):
        """Reset all filters to show everything"""
        self.show_blur_cb.setChecked(True)
        self.show_duplicate_cb.setChecked(True)
        self.show_with_delete_cb.setChecked(True)
        self.show_unprocessed_cb.setChecked(True)
