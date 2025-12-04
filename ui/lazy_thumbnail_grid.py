"""Lazy loading thumbnail grid for better performance with large datasets"""
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QScrollArea, QGridLayout, 
                               QHBoxLayout, QPushButton, QLabel)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QPixmap
from ui.components import ThumbnailWidget

class LazyThumbnailGridWidget(QWidget):
    """Optimized thumbnail grid with lazy loading"""
    selection_changed = Signal(list)
    delete_toggled = Signal(str, bool)
    batch_select_all = Signal()
    batch_deselect_all = Signal()

    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # Toolbar
        self.toolbar = QHBoxLayout()
        self.select_all_btn = QPushButton("全選択 (削除候補)")
        self.select_all_btn.clicked.connect(self.batch_select_all.emit)
        self.deselect_all_btn = QPushButton("全解除 (保持)")
        self.deselect_all_btn.clicked.connect(self.batch_deselect_all.emit)
        
        # Info label
        self.info_label = QLabel("")
        
        self.toolbar.addWidget(self.select_all_btn)
        self.toolbar.addWidget(self.deselect_all_btn)
        self.toolbar.addWidget(self.info_label)
        self.toolbar.addStretch()
        
        self.layout.addLayout(self.toolbar)
        
        # Scroll area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.verticalScrollBar().valueChanged.connect(self.on_scroll)
        
        self.container = QWidget()
        self.grid = QGridLayout(self.container)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.scroll.setWidget(self.container)
        
        self.layout.addWidget(self.scroll)
        
        # Data
        self.widgets = {}
        self.selected_paths = []
        self.thumbnail_size = 120
        self.current_images = []
        self.current_actions = {}
        self.current_blur_scores = {}
        
        # Lazy loading
        self.loaded_widgets = set()  # Track which widgets are loaded
        self.load_batch_size = 50  # Load 50 thumbnails at a time
        self.load_timer = QTimer()
        self.load_timer.timeout.connect(self.load_next_batch)
        self.load_timer.setSingleShot(True)
        self.pending_load_start = 0

    def set_images(self, images, actions, blur_scores=None):
        """Set images with lazy loading"""
        # Store data
        self.current_images = images
        self.current_actions = actions
        self.current_blur_scores = blur_scores if blur_scores else {}
        
        # Clear existing
        for i in reversed(range(self.grid.count())): 
            widget = self.grid.itemAt(i).widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()
        
        self.widgets = {}
        self.loaded_widgets.clear()
        self.selected_paths = []
        
        # Update info
        self.info_label.setText(f"合計: {len(images)} 枚")
        
        # Create placeholder widgets
        row = 0
        col = 0
        max_cols = 3
        
        for path in images:
            # Create lightweight placeholder
            placeholder = QLabel("読込中...")
            placeholder.setFixedSize(self.thumbnail_size, self.thumbnail_size)
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("background-color: #f0f0f0; border: 1px solid #ddd;")
            
            self.grid.addWidget(placeholder, row, col)
            self.widgets[path] = placeholder
            
            col += 1
            if col >= max_cols:
                col = 0
                row += 1
        
        # Start lazy loading
        self.pending_load_start = 0
        self.load_next_batch()
    
    def load_next_batch(self):
        """Load next batch of thumbnails"""
        if self.pending_load_start >= len(self.current_images):
            return
        
        end = min(self.pending_load_start + self.load_batch_size, len(self.current_images))
        
        for i in range(self.pending_load_start, end):
            path = self.current_images[i]
            if path in self.loaded_widgets:
                continue
            
            # Replace placeholder with actual thumbnail
            placeholder = self.widgets.get(path)
            if placeholder:
                # Get position
                index = self.grid.indexOf(placeholder)
                if index >= 0:
                    row, col, _, _ = self.grid.getItemPosition(index)
                    
                    # Remove placeholder
                    placeholder.setParent(None)
                    placeholder.deleteLater()
                    
                    # Create actual thumbnail
                    is_checked = self.current_actions.get(path) == 'delete'
                    score = self.current_blur_scores.get(path)
                    
                    w = ThumbnailWidget(path, is_checked, score, self.thumbnail_size)
                    w.clicked.connect(self.handle_click)
                    w.toggled.connect(self.delete_toggled.emit)
                    w.toggled.connect(w.update_style)
                    
                    self.grid.addWidget(w, row, col)
                    self.widgets[path] = w
                    self.loaded_widgets.add(path)
        
        self.pending_load_start = end
        
        # Continue loading if there are more
        if self.pending_load_start < len(self.current_images):
            self.load_timer.start(10)  # Load next batch after 10ms
    
    def on_scroll(self, value):
        """Load more thumbnails when scrolling"""
        # Calculate visible range
        viewport_height = self.scroll.viewport().height()
        content_height = self.container.height()
        
        if content_height > 0:
            visible_ratio = (value + viewport_height) / content_height
            
            # If scrolled past 70%, load more
            if visible_ratio > 0.7 and not self.load_timer.isActive():
                self.load_next_batch()
    
    def set_thumbnail_size(self, size):
        """Update thumbnail size"""
        self.thumbnail_size = size
        # Reload all images with new size
        self.set_images(self.current_images, self.current_actions, self.current_blur_scores)
    
    def handle_click(self, path):
        """Handle thumbnail click"""
        from PySide6.QtWidgets import QApplication
        modifiers = QApplication.keyboardModifiers()
        
        if modifiers & Qt.ControlModifier:
            if path in self.selected_paths:
                self.selected_paths.remove(path)
            else:
                if len(self.selected_paths) < 2:
                    self.selected_paths.append(path)
                else:
                    self.selected_paths.pop(0)
                    self.selected_paths.append(path)
        else:
            self.selected_paths = [path]
            
        self.update_selection_visuals()
        self.selection_changed.emit(self.selected_paths)
    
    def update_selection_visuals(self):
        """Update selection visuals"""
        for p, w in self.widgets.items():
            if isinstance(w, ThumbnailWidget):
                w.set_selected(p in self.selected_paths)
    
    def select_path(self, path):
        """Select a specific path"""
        self.selected_paths = [path]
        self.update_selection_visuals()
        self.selection_changed.emit(self.selected_paths)
