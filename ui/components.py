from PySide6.QtWidgets import (QWidget, QVBoxLayout, QListWidget, QListWidgetItem, 
                               QLabel, QScrollArea, QGridLayout, QCheckBox, QFrame,
                               QHBoxLayout, QPushButton, QSizePolicy, QSplitter)
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPixmap, QImage, QPainter, QColor, QIcon, QAction
import os

class GroupListWidget(QWidget):
    group_selected = Signal(int) # Emits group index

    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self.group_selected.emit)
        self.layout.addWidget(self.list_widget)

    def set_groups(self, groups, group_types=None):
        self.list_widget.clear()
        for i, group in enumerate(groups):
            # Determine type
            g_type = "重複" # Default
            if group_types and i < len(group_types):
                g_type = group_types[i]
                
            item = QListWidgetItem(f"グループ #{i+1} ({len(group)}枚)\n[{g_type}]")
            self.list_widget.addItem(item)

class ThumbnailWidget(QFrame):
    clicked = Signal(str) # Emits path
    toggled = Signal(str, bool) # Emits path, is_checked

    def __init__(self, path, is_checked=False, blur_score=None):
        super().__init__()
        self.path = path
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        self.setLineWidth(2)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5)
        
        # Image
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setFixedSize(120, 120)
        self.image_label.setStyleSheet("background-color: #eee;")
        self.layout.addWidget(self.image_label)
        
        # Load thumbnail
        self.load_thumbnail()
        
        # Info
        info_layout = QHBoxLayout()
        
        # Checkbox
        self.checkbox = QCheckBox("削除候補")
        self.checkbox.setChecked(is_checked)
        self.checkbox.toggled.connect(lambda c: self.toggled.emit(self.path, c))
        info_layout.addWidget(self.checkbox)
        
        # Blur Icon/Text
        if blur_score is not None:
            blur_label = QLabel("⚠️" if blur_score < 100 else "✅")
            blur_label.setToolTip(f"スコア: {blur_score:.1f}")
            info_layout.addWidget(blur_label)
            
        self.layout.addLayout(info_layout)
        
        self.update_style()

    def load_thumbnail(self):
        pixmap = QPixmap(self.path)
        if not pixmap.isNull():
            self.image_label.setPixmap(pixmap.scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def mousePressEvent(self, event):
        self.clicked.emit(self.path)
        super().mousePressEvent(event)

    def set_selected(self, selected):
        if selected:
            self.setStyleSheet("ThumbnailWidget { border: 2px solid blue; background-color: #eef; }")
        else:
            self.update_style()
            
    def update_style(self):
        if self.checkbox.isChecked():
            self.setStyleSheet("ThumbnailWidget { background-color: #ffe0e0; border: 1px solid red; }")
        else:
            self.setStyleSheet("ThumbnailWidget { background-color: white; }")
            
    def set_checked(self, checked):
        self.checkbox.setChecked(checked)
        self.update_style()

class ThumbnailGridWidget(QWidget):
    selection_changed = Signal(list) # Emits list of selected paths
    delete_toggled = Signal(str, bool)

    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.container = QWidget()
        self.grid = QGridLayout(self.container)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.scroll.setWidget(self.container)
        
        self.layout.addWidget(self.scroll)
        self.widgets = {}
        self.selected_paths = [] # List of selected paths (max 2)

    def set_images(self, images, actions, blur_scores=None):
        # Clear existing
        for i in reversed(range(self.grid.count())): 
            self.grid.itemAt(i).widget().setParent(None)
        self.widgets = {}
        self.selected_paths = []
        
        row = 0
        col = 0
        max_cols = 3
        
        for path in images:
            is_checked = actions.get(path) == 'delete'
            score = blur_scores.get(path) if blur_scores else None
            
            w = ThumbnailWidget(path, is_checked, score)
            w.clicked.connect(self.handle_click)
            w.toggled.connect(self.delete_toggled.emit)
            w.toggled.connect(w.update_style)
            
            self.grid.addWidget(w, row, col)
            self.widgets[path] = w
            
            col += 1
            if col >= max_cols:
                col = 0
                row += 1
                
    def handle_click(self, path):
        modifiers = QApplication.keyboardModifiers()
        
        if modifiers & Qt.ControlModifier:
            # Toggle selection
            if path in self.selected_paths:
                self.selected_paths.remove(path)
            else:
                if len(self.selected_paths) < 2:
                    self.selected_paths.append(path)
                else:
                    # Replace the second one? Or ignore?
                    # Let's replace the older one (FIFO) or just replace the second one
                    self.selected_paths.pop(0)
                    self.selected_paths.append(path)
        else:
            # Single selection
            self.selected_paths = [path]
            
        self.update_selection_visuals()
        self.selection_changed.emit(self.selected_paths)
        
    def update_selection_visuals(self):
        for p, w in self.widgets.items():
            w.set_selected(p in self.selected_paths)

    def select_path(self, path):
        self.selected_paths = [path]
        self.update_selection_visuals()
        self.selection_changed.emit(self.selected_paths)

class DetailWidget(QWidget):
    toggle_delete = Signal(str, bool)

    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.info_frame = QFrame()
        self.info_layout = QVBoxLayout(self.info_frame)
        
        self.filename_label = QLabel("ファイル名: -")
        self.path_label = QLabel("パス: -")
        self.path_label.setWordWrap(True)
        self.res_label = QLabel("解像度: -")
        self.size_label = QLabel("サイズ: -")
        self.date_label = QLabel("撮影日時: -")
        self.blur_label = QLabel("ブレスコア: -")
        
        self.info_layout.addWidget(self.filename_label)
        self.info_layout.addWidget(self.path_label)
        self.info_layout.addWidget(self.res_label)
        self.info_layout.addWidget(self.size_label)
        self.info_layout.addWidget(self.date_label)
        self.info_layout.addWidget(self.blur_label)
        
        # Controls
        self.controls_layout = QHBoxLayout()
        self.delete_btn = QPushButton("削除候補にする")
        self.delete_btn.setCheckable(True)
        self.delete_btn.clicked.connect(self.on_delete_clicked)
        self.controls_layout.addWidget(self.delete_btn)
        
        self.info_layout.addLayout(self.controls_layout)
        self.info_layout.addStretch()
        
        self.layout.addWidget(self.info_frame)
        self.current_path = None

    def set_info(self, path, info=None, is_checked=False):
        self.current_path = path
        if not path:
            self.filename_label.setText("ファイル名: -")
            self.path_label.setText("パス: -")
            self.res_label.setText("解像度: -")
            self.size_label.setText("サイズ: -")
            self.date_label.setText("撮影日時: -")
            self.blur_label.setText("ブレスコア: -")
            self.delete_btn.setEnabled(False)
            return

        self.delete_btn.setEnabled(True)
        self.filename_label.setText(f"ファイル名: {os.path.basename(path)}")
        self.path_label.setText(f"パス: {path}")
        
        if info:
            self.res_label.setText(f"解像度: {info.get('resolution', '-')}")
            self.size_label.setText(f"サイズ: {info.get('size', '-')}")
            self.date_label.setText(f"撮影日時: {info.get('date', '-')}")
            self.blur_label.setText(f"ブレスコア: {info.get('blur_score', '-')}")
            
        self.delete_btn.setChecked(is_checked)
        self.update_btn_style(is_checked)

    def on_delete_clicked(self, checked):
        if self.current_path:
            self.toggle_delete.emit(self.current_path, checked)
            self.update_btn_style(checked)

    def update_btn_style(self, checked):
        if checked:
            self.delete_btn.setText("残す (Keep)")
            self.delete_btn.setStyleSheet("background-color: #ffcccc;")
        else:
            self.delete_btn.setText("削除候補にする")
            self.delete_btn.setStyleSheet("")

class SinglePreview(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.scroll = QScrollArea()
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.scroll.setWidget(self.image_label)
        self.scroll.setWidgetResizable(True)
        self.layout.addWidget(self.scroll)
        
    def set_image(self, path):
        if not path:
            self.image_label.clear()
            return
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            self.image_label.setPixmap(pixmap.scaled(self.scroll.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

class PreviewWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.left_view = SinglePreview()
        self.right_view = SinglePreview()
        
        self.layout.addWidget(self.left_view)
        self.layout.addWidget(self.right_view)
        
        self.right_view.setVisible(False)
        
        # Sync scrolling (Simple implementation)
        self.left_view.scroll.verticalScrollBar().valueChanged.connect(
            self.right_view.scroll.verticalScrollBar().setValue)
        self.right_view.scroll.verticalScrollBar().valueChanged.connect(
            self.left_view.scroll.verticalScrollBar().setValue)
            
        self.left_view.scroll.horizontalScrollBar().valueChanged.connect(
            self.right_view.scroll.horizontalScrollBar().setValue)
        self.right_view.scroll.horizontalScrollBar().valueChanged.connect(
            self.left_view.scroll.horizontalScrollBar().setValue)

    def set_images(self, path1, path2=None):
        self.left_view.set_image(path1)
        if path2:
            self.right_view.set_image(path2)
            self.right_view.setVisible(True)
        else:
            self.right_view.setVisible(False)

