from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QPushButton, QLabel, QFileDialog, 
                               QProgressBar, QSplitter, QMessageBox)
from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QAction

# Import core modules
from core.scanner import Scanner
from core.blur_detector import BlurDetector
from core.hash_engine import HashEngine
from core.group_builder import GroupBuilder
from core.rule_engine import RuleEngine
from core.executor import Executor

from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QPushButton, QLabel, QFileDialog, 
                               QProgressBar, QSplitter, QMessageBox)
from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QAction

# Import core modules
from core.scanner import Scanner
from core.blur_detector import BlurDetector
from core.hash_engine import HashEngine
from core.group_builder import GroupBuilder
from core.rule_engine import RuleEngine
from core.executor import Executor

# Import UI components
from ui.components import GroupListWidget, ThumbnailGridWidget, PreviewWidget, DetailWidget

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("画像整理ツール")
        self.resize(1200, 900)
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        
        # --- Top Bar ---
        self.top_bar = QHBoxLayout()
        self.path_label = QLabel("フォルダ未選択")
        self.browse_btn = QPushButton("フォルダを選択")
        self.browse_btn.clicked.connect(self.browse_folder)
        self.scan_btn = QPushButton("スキャン開始")
        self.scan_btn.clicked.connect(self.start_scan)
        self.scan_btn.setEnabled(False)
        
        self.top_bar.addWidget(self.browse_btn)
        self.top_bar.addWidget(self.path_label)
        self.top_bar.addStretch()
        self.top_bar.addWidget(self.scan_btn)
        
        self.layout.addLayout(self.top_bar)
        
        # --- Progress Bar ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.layout.addWidget(self.progress_bar)
        
        # --- Status Label ---
        self.status_label = QLabel("準備完了")
        self.layout.addWidget(self.status_label)
        
        # --- Main Layout (Vertical Splitter: Preview / Bottom Panes) ---
        self.main_splitter = QSplitter(Qt.Vertical)
        
        # Top: Preview
        self.preview_widget = PreviewWidget()
        self.main_splitter.addWidget(self.preview_widget)
        
        # Bottom: 3-Pane Splitter
        self.bottom_splitter = QSplitter(Qt.Horizontal)
        
        # Left: Group List
        self.group_list = GroupListWidget()
        self.group_list.group_selected.connect(self.on_group_selected)
        self.bottom_splitter.addWidget(self.group_list)
        
        # Center: Thumbnails
        self.thumbnail_grid = ThumbnailGridWidget()
        self.thumbnail_grid.selection_changed.connect(self.on_selection_changed)
        self.thumbnail_grid.delete_toggled.connect(self.on_delete_toggled)
        self.bottom_splitter.addWidget(self.thumbnail_grid)
        
        # Right: Details
        self.detail_widget = DetailWidget()
        self.detail_widget.toggle_delete.connect(self.on_delete_toggled)
        self.bottom_splitter.addWidget(self.detail_widget)
        
        # Set initial sizes for bottom splitter (ratio 1:2:1)
        self.bottom_splitter.setSizes([250, 500, 250])
        
        self.main_splitter.addWidget(self.bottom_splitter)
        # Set initial sizes for main splitter (Preview bigger)
        self.main_splitter.setSizes([500, 300])
        
        self.layout.addWidget(self.main_splitter)
        
        # --- Bottom Bar ---
        self.bottom_bar = QHBoxLayout()
        self.execute_btn = QPushButton("処理を実行 (ゴミ箱へ移動)")
        self.execute_btn.clicked.connect(self.execute_actions)
        self.execute_btn.setEnabled(False)
        self.bottom_bar.addStretch()
        self.bottom_bar.addWidget(self.execute_btn)
        
        self.layout.addLayout(self.bottom_bar)
        
        # Data
        self.selected_folder = ""
        self.scan_thread = None
        self.results = {} 
        self.actions = {} # path -> 'keep' or 'delete'
        self.blur_scores = {} # path -> score
        self.current_groups = [] # List of lists of paths
        self.current_group_types = [] # List of types
        self.current_group_index = -1
        self.current_selected_paths = []

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "フォルダを選択")
        if folder:
            self.selected_folder = folder
            self.path_label.setText(folder)
            self.scan_btn.setEnabled(True)

    def start_scan(self):
        if not self.selected_folder:
            return
            
        self.scan_btn.setEnabled(False)
        self.browse_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("スキャン中...")
        
        # Clear UI
        self.group_list.set_groups([])
        self.thumbnail_grid.set_images([], {})
        self.preview_widget.set_images(None)
        self.detail_widget.set_info(None)
        
        # Start Thread
        self.scan_thread = ScanWorker(self.selected_folder)
        self.scan_thread.progress.connect(self.update_progress)
        self.scan_thread.status.connect(self.update_status)
        self.scan_thread.finished.connect(self.scan_finished)
        self.scan_thread.start()

    def update_progress(self, value):
        self.progress_bar.setValue(value)
        
    def update_status(self, text):
        self.status_label.setText(text)

    def scan_finished(self, results):
        self.results = results
        self.scan_btn.setEnabled(True)
        self.browse_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText("スキャン完了")
        self.execute_btn.setEnabled(True)
        
        # Process results
        self.current_groups = []
        self.current_group_types = []
        self.blur_scores = {}
        self.actions = {}
        
        # 1. Blurry Images
        blurry_images = self.results.get('blurry', [])
        if blurry_images:
            blur_group = []
            for path, score in blurry_images:
                blur_group.append(path)
                self.blur_scores[path] = score
                self.actions[path] = 'delete'
            
            self.current_groups.append(blur_group)
            self.current_group_types.append("ブレ画像")
            
        # 2. Duplicates
        groups = self.results.get('groups', [])
        for group in groups:
            self.current_groups.append(group)
            self.current_group_types.append("重複・類似")
            
            # Apply rules
            group_actions = RuleEngine.apply_rules(group)
            self.actions.update(group_actions)
            
        # Update UI
        self.group_list.set_groups(self.current_groups, self.current_group_types)
        if self.current_groups:
            self.group_list.list_widget.setCurrentRow(0)

    def on_group_selected(self, index):
        if 0 <= index < len(self.current_groups):
            self.current_group_index = index
            group = self.current_groups[index]
            self.thumbnail_grid.set_images(group, self.actions, self.blur_scores)
            
            # Select first image in group
            if group:
                self.thumbnail_grid.select_path(group[0])

    def on_selection_changed(self, paths):
        self.current_selected_paths = paths
        
        # Update Preview (Handle 1 or 2 images)
        if not paths:
            self.preview_widget.set_images(None)
            self.detail_widget.set_info(None)
            return
            
        path1 = paths[0]
        path2 = paths[1] if len(paths) > 1 else None
        
        self.preview_widget.set_images(path1, path2)
        
        # Update Details (Show info for the last selected one, usually the primary focus)
        # Or maybe the first one? Let's use the last one in the list as "primary"
        primary_path = paths[-1]
        self.update_details(primary_path)

    def update_details(self, path):
        info = {}
        try:
            size = os.path.getsize(path)
            info['size'] = f"{size / 1024:.1f} KB"
            
            exif = Scanner.get_exif_data(path)
            info['date'] = exif.get('DateTimeOriginal', '不明')
            
            if path in self.blur_scores:
                info['blur_score'] = f"{self.blur_scores[path]:.2f}"
            
            from PIL import Image
            with Image.open(path) as img:
                info['resolution'] = f"{img.width}x{img.height}"
                
        except Exception:
            pass
            
        is_checked = self.actions.get(path) == 'delete'
        self.detail_widget.set_info(path, info, is_checked)

    def on_delete_toggled(self, path, checked):
        self.actions[path] = 'delete' if checked else 'keep'
        
        # Update Thumbnail Grid
        if self.current_group_index >= 0:
            group = self.current_groups[self.current_group_index]
            if path in group:
                if path in self.thumbnail_grid.widgets:
                    self.thumbnail_grid.widgets[path].set_checked(checked)
                    
        # Update Details if showing this path
        if self.detail_widget.current_path == path:
            self.detail_widget.update_btn_style(checked)

    def execute_actions(self):
        to_delete = [p for p, a in self.actions.items() if a == 'delete']
        if not to_delete:
            return
            
        confirm = QMessageBox.question(self, "実行確認", 
                                       f"{len(to_delete)} 個のファイルをゴミ箱へ移動しますか？",
                                       QMessageBox.Yes | QMessageBox.No)
        
        if confirm == QMessageBox.Yes:
            log_path = Executor.execute_actions(self.actions, self.selected_folder)
            QMessageBox.information(self, "完了", f"移動しました。\nログ: {log_path}")
            self.start_scan()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space:
            # Toggle delete for current primary selection
            if self.current_selected_paths:
                path = self.current_selected_paths[-1]
                current_action = self.actions.get(path, 'keep')
                new_checked = (current_action == 'keep')
                self.on_delete_toggled(path, new_checked)
                
        elif event.key() == Qt.Key_Up:
            new_index = self.current_group_index - 1
            if new_index >= 0:
                self.group_list.list_widget.setCurrentRow(new_index)
                
        elif event.key() == Qt.Key_Down:
            new_index = self.current_group_index + 1
            if new_index < len(self.current_groups):
                self.group_list.list_widget.setCurrentRow(new_index)
                
        elif event.key() == Qt.Key_Left:
            self.navigate_image(-1)
            
        elif event.key() == Qt.Key_Right:
            self.navigate_image(1)
            
        else:
            super().keyPressEvent(event)

    def navigate_image(self, delta):
        if self.current_group_index < 0:
            return
        group = self.current_groups[self.current_group_index]
        if not group:
            return
            
        # Use the last selected path as reference
        current_path = self.current_selected_paths[-1] if self.current_selected_paths else None
        
        if not current_path or current_path not in group:
            self.thumbnail_grid.select_path(group[0])
            return
            
        try:
            idx = group.index(current_path)
            new_idx = idx + delta
            if 0 <= new_idx < len(group):
                self.thumbnail_grid.select_path(group[new_idx])
        except ValueError:
            pass


class ScanWorker(QThread):
    progress = Signal(int)
    status = Signal(str)
    finished = Signal(dict)
    
    def __init__(self, folder):
        super().__init__()
        self.folder = folder
        
    def run(self):
        self.status.emit("Scanning files...")
        files = Scanner.scan_directory(self.folder)
        total = len(files)
        
        blurry_images = []
        hashes = []
        
        for i, f in enumerate(files):
            # Blur Check
            score = BlurDetector.calculate_blur_score(f)
            if BlurDetector.is_blurry(score):
                blurry_images.append((f, score))
                
            # Hash
            h = HashEngine.compute_hash(f)
            hashes.append((f, h))
            
            if i % 10 == 0:
                self.progress.emit(int((i / total) * 50)) # First 50%
                
        self.status.emit("Grouping images...")
        groups = GroupBuilder.build_groups(hashes, threshold=5)
        
        self.progress.emit(100)
        
        results = {
            'blurry': blurry_images,
            'groups': groups
        }
        self.finished.emit(results)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
