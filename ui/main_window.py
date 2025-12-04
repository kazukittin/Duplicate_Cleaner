import os
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QPushButton, QLabel, QFileDialog, 
                               QProgressBar, QSplitter, QMessageBox, QSlider)
from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QAction

# Import core modules
from core.scanner import Scanner
from core.blur_detector import BlurDetector
from core.hash_engine import HashEngine
from core.group_builder import GroupBuilder
from core.rule_engine import RuleEngine
from core.executor import Executor
from core.settings import Settings

# Import UI components
from ui.components import GroupListWidget, PreviewWidget, DetailWidget
from ui.lazy_thumbnail_grid import LazyThumbnailGridWidget

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("画像整理ツール")
        self.resize(1200, 900)
        
        # Enable drag and drop
        self.setAcceptDrops(True)
        
        # Load settings
        self.settings = Settings()
        
        # Apply stylesheet
        try:
            with open('ui/styles.qss', 'r', encoding='utf-8') as f:
                self.setStyleSheet(f.read())
        except:
            pass  # Stylesheet is optional
        
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
        
        # Thumbnail size slider
        self.thumb_size_label = QLabel("サムネイルサイズ:")
        self.thumb_size_slider = QSlider(Qt.Horizontal)
        self.thumb_size_slider.setMinimum(80)
        self.thumb_size_slider.setMaximum(200)
        self.thumb_size_slider.setValue(self.settings.get('thumbnail_size', 120))
        self.thumb_size_slider.setFixedWidth(150)
        self.thumb_size_slider.valueChanged.connect(self.on_thumbnail_size_changed)
        self.thumb_size_value_label = QLabel(f"{self.settings.get('thumbnail_size', 120)}px")
        
        # AI Auto-select button
        self.ai_select_btn = QPushButton("AI推奨を適用")
        self.ai_select_btn.clicked.connect(self.apply_ai_selection)
        self.ai_select_btn.setEnabled(False)
        self.ai_select_btn.setToolTip("各グループで最高品質の画像を自動選択")
        
        self.top_bar.addWidget(self.browse_btn)
        self.top_bar.addWidget(self.path_label)
        self.top_bar.addStretch()
        self.top_bar.addWidget(self.ai_select_btn)
        self.top_bar.addWidget(self.thumb_size_label)
        self.top_bar.addWidget(self.thumb_size_slider)
        self.top_bar.addWidget(self.thumb_size_value_label)
        self.top_bar.addWidget(self.scan_btn)
        
        self.layout.addLayout(self.top_bar)
        
        # --- Progress Bar ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.layout.addWidget(self.progress_bar)
        
        # --- Progress Details ---
        self.progress_detail_label = QLabel("")
        self.progress_detail_label.setVisible(False)
        self.progress_detail_label.setWordWrap(True)
        self.progress_detail_label.setStyleSheet("color: #666; font-size: 10pt;")
        self.layout.addWidget(self.progress_detail_label)
        
        # --- Status Label ---
        self.status_label = QLabel("準備完了")
        self.layout.addWidget(self.status_label)
        
        # --- Main Layout (Vertical Splitter: Preview / Bottom Panes) ---
        self.main_splitter = QSplitter(Qt.Vertical)
        
        # Top: Preview
        self.preview_widget = PreviewWidget()
        self.main_splitter.addWidget(self.preview_widget)
        
        # Bottom: 3-Pane Splitter (now 4-pane with filter)
        self.bottom_splitter = QSplitter(Qt.Horizontal)
        
        # Left: Filter Panel
        from ui.filter_widget import FilterWidget
        self.filter_widget = FilterWidget()
        self.filter_widget.filter_changed.connect(self.apply_filters)
        self.bottom_splitter.addWidget(self.filter_widget)
        
        # Group List
        self.group_list = GroupListWidget()
        self.group_list.group_selected.connect(self.on_group_selected)
        self.group_list.batch_operation.connect(self.handle_batch_operation)
        self.bottom_splitter.addWidget(self.group_list)
        
        # Center: Thumbnails (Lazy Loading)
        self.thumbnail_grid = LazyThumbnailGridWidget()
        self.thumbnail_grid.selection_changed.connect(self.on_selection_changed)
        self.thumbnail_grid.delete_toggled.connect(self.on_delete_toggled)
        self.thumbnail_grid.batch_select_all.connect(self.batch_select_all_current_group)
        self.thumbnail_grid.batch_deselect_all.connect(self.batch_deselect_all_current_group)
        self.bottom_splitter.addWidget(self.thumbnail_grid)
        
        # Right: Details
        self.detail_widget = DetailWidget()
        self.detail_widget.toggle_delete.connect(self.on_delete_toggled)
        self.bottom_splitter.addWidget(self.detail_widget)
        
        # Set initial sizes for bottom splitter (ratio 1:1:3:1)
        self.bottom_splitter.setSizes([150, 200, 500, 250])
        
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
        self.current_groups = [] # List of lists of paths (filtered)
        self.current_group_types = [] # List of types (filtered)
        self.all_groups = [] # All groups (unfiltered)
        self.all_group_types = [] # All group types (unfiltered)
        self.current_group_index = -1
        self.current_selected_paths = []
        self.filter_criteria = {
            'show_blur': True,
            'show_duplicate': True,
            'show_with_delete': True,
            'show_unprocessed': True,
        }

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "フォルダを選択")
        if folder:
            self.selected_folder = folder
            self.path_label.setText(folder)
            self.scan_btn.setEnabled(True)
    
    def on_thumbnail_size_changed(self, value):
        """Handle thumbnail size slider change"""
        self.thumb_size_value_label.setText(f"{value}px")
        self.thumbnail_grid.set_thumbnail_size(value)
        self.settings.set('thumbnail_size', value)

    def start_scan(self):
        if not self.selected_folder:
            return
            
        self.scan_btn.setEnabled(False)
        self.browse_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_detail_label.setVisible(True)
        self.progress_detail_label.setText("初期化中...")
        self.status_label.setText("スキャン中...")
        
        # Clear UI
        self.group_list.set_groups([])
        self.thumbnail_grid.set_images([], {})
        self.preview_widget.set_images(None)
        self.detail_widget.set_info(None)
        
        # Start Thread
        self.scan_thread = ScanWorker(self.selected_folder)
        self.scan_thread.progress.connect(self.update_progress)
        self.scan_thread.progress_detail.connect(self.update_progress_detail)
        self.scan_thread.status.connect(self.update_status)
        self.scan_thread.finished.connect(self.scan_finished)
        self.scan_thread.start()

    def update_progress(self, value):
        self.progress_bar.setValue(value)
    
    def update_progress_detail(self, current_file, processed, total, elapsed_time):
        """Update detailed progress information"""
        # Calculate estimated time remaining
        if processed > 0 and elapsed_time > 0:
            avg_time_per_file = elapsed_time / processed
            remaining_files = total - processed
            estimated_remaining = avg_time_per_file * remaining_files
            
            # Format time
            if estimated_remaining < 60:
                time_str = f"{int(estimated_remaining)}秒"
            else:
                minutes = int(estimated_remaining / 60)
                seconds = int(estimated_remaining % 60)
                time_str = f"{minutes}分{seconds}秒"
            
            detail_text = f"処理中: {os.path.basename(current_file)}\n{processed} / {total} ファイル (残り約 {time_str})"
        else:
            detail_text = f"処理中: {os.path.basename(current_file)}\n{processed} / {total} ファイル"
        
        self.progress_detail_label.setText(detail_text)
        
    def update_status(self, text):
        self.status_label.setText(text)

    def scan_finished(self, results):
        self.results = results
        self.scan_btn.setEnabled(True)
        self.browse_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.progress_detail_label.setVisible(False)
        self.status_label.setText("スキャン完了")
        self.execute_btn.setEnabled(True)
        self.ai_select_btn.setEnabled(True)
        
        # Process results
        self.all_groups = []
        self.all_group_types = []
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
            
            self.all_groups.append(blur_group)
            self.all_group_types.append("ブレ画像")
            
        # 2. Duplicates
        groups = self.results.get('groups', [])
        for group in groups:
            self.all_groups.append(group)
            self.all_group_types.append("重複・類似")
            
            # Apply rules
            group_actions = RuleEngine.apply_rules(group)
            self.actions.update(group_actions)
        
        # Apply filters to show filtered groups
        self.apply_filters(self.filter_criteria)
        
        # Show statistics
        self.show_statistics()

    def on_group_selected(self, index):
        if 0 <= index < len(self.current_groups):
            self.current_group_index = index
            group = self.current_groups[index]
            
            # Show group size info
            self.status_label.setText(f"グループ #{index+1}: {len(group)} 枚の画像")
            
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
    
    def batch_select_all_current_group(self):
        """Mark all files in current group as delete candidates"""
        if self.current_group_index < 0:
            return
        group = self.current_groups[self.current_group_index]
        for path in group:
            self.on_delete_toggled(path, True)
    
    def batch_deselect_all_current_group(self):
        """Mark all files in current group as keep"""
        if self.current_group_index < 0:
            return
        group = self.current_groups[self.current_group_index]
        for path in group:
            self.on_delete_toggled(path, False)
    
    def handle_batch_operation(self, group_index, operation):
        """Handle batch operations from context menu"""
        if group_index < 0 or group_index >= len(self.current_groups):
            return
        
        group = self.current_groups[group_index]
        
        if operation == "mark_all_delete":
            for path in group:
                self.on_delete_toggled(path, True)
        
        elif operation == "mark_all_keep":
            for path in group:
                self.on_delete_toggled(path, False)
        
        elif operation == "delete_except_highest_res":
            # Find highest resolution image
            from PIL import Image
            max_res = 0
            best_path = None
            
            for path in group:
                try:
                    with Image.open(path) as img:
                        res = img.width * img.height
                        if res > max_res:
                            max_res = res
                            best_path = path
                except:
                    pass
            
            # Mark all except best as delete
            for path in group:
                if path == best_path:
                    self.on_delete_toggled(path, False)
                else:
                    self.on_delete_toggled(path, True)
        
        elif operation == "delete_except_newest":
            # Find newest file by modification time
            newest_path = None
            newest_time = 0
            
            for path in group:
                try:
                    mtime = os.path.getmtime(path)
                    if mtime > newest_time:
                        newest_time = mtime
                        newest_path = path
                except:
                    pass
            
            # Mark all except newest as delete
            for path in group:
                if path == newest_path:
                    self.on_delete_toggled(path, False)
                else:
                    self.on_delete_toggled(path, True)

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
                new_path = group[new_idx]
                # Update thumbnail selection
                self.thumbnail_grid.select_path(new_path)
                # Scroll to make it visible
                if new_path in self.thumbnail_grid.widgets:
                    widget = self.thumbnail_grid.widgets[new_path]
                    self.thumbnail_grid.scroll.ensureWidgetVisible(widget)
        except ValueError:
            pass
    
    def apply_filters(self, criteria):
        """Apply filter criteria to groups"""
        self.filter_criteria = criteria
        
        # Filter groups based on criteria
        self.current_groups = []
        self.current_group_types = []
        
        for i, (group, group_type) in enumerate(zip(self.all_groups, self.all_group_types)):
            # Check group type filter
            if group_type == "ブレ画像" and not criteria['show_blur']:
                continue
            if group_type == "重複・類似" and not criteria['show_duplicate']:
                continue
            
            # Check status filter
            has_delete = any(self.actions.get(path) == 'delete' for path in group)
            if has_delete and not criteria['show_with_delete']:
                continue
            if not has_delete and not criteria['show_unprocessed']:
                continue
            
            # Add to filtered groups
            self.current_groups.append(group)
            self.current_group_types.append(group_type)
        
        # Update UI
        self.group_list.set_groups(self.current_groups, self.current_group_types)
        if self.current_groups:
            self.group_list.list_widget.setCurrentRow(0)
    
    def show_statistics(self):
        """Show statistics dialog"""
        from ui.statistics_widget import StatisticsDialog
        
        # Calculate statistics
        total_files = sum(len(group) for group in self.all_groups)
        blur_groups = sum(1 for gt in self.all_group_types if gt == "ブレ画像")
        duplicate_groups = sum(1 for gt in self.all_group_types if gt == "重複・類似")
        
        delete_candidates = [p for p, a in self.actions.items() if a == 'delete']
        total_delete_size = 0
        for path in delete_candidates:
            try:
                total_delete_size += os.path.getsize(path)
            except:
                pass
        
        stats = {
            'total_files_scanned': len(Scanner.scan_directory(self.selected_folder)) if self.selected_folder else 0,
            'total_groups': len(self.all_groups),
            'blur_groups': blur_groups,
            'duplicate_groups': duplicate_groups,
            'total_delete_candidates': len(delete_candidates),
            'total_delete_size': total_delete_size,
        }
        
        dialog = StatisticsDialog(stats, self)
        dialog.exec()
    
    def apply_ai_selection(self):
        """Apply AI-based automatic selection"""
        try:
            from core.image_quality import ImageQuality
            
            for group in self.all_groups:
                best_path, score = ImageQuality.get_best_image_in_group(group, self.blur_scores)
                
                # Mark all except best as delete
                for path in group:
                    if path == best_path:
                        self.on_delete_toggled(path, False)
                    else:
                        self.on_delete_toggled(path, True)
            
            QMessageBox.information(self, "AI推奨適用完了", 
                                  "各グループで最高品質の画像を保持し、他を削除候補にしました。")
        except ImportError:
            QMessageBox.warning(self, "エラー", 
                              "AI機能を使用するにはnumpyをインストールしてください。\npip install numpy")
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"AI推奨の適用中にエラーが発生しました: {str(e)}")
    
    def dragEnterEvent(self, event):
        """Handle drag enter event for drag-and-drop support"""
        if event.mimeData().hasUrls():
            # Check if at least one URL is a directory
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    path = url.toLocalFile()
                    if os.path.isdir(path):
                        event.acceptProposedAction()
                        # Visual feedback: change background color
                        self.central_widget.setStyleSheet("background-color: #e3f2fd;")
                        return
        event.ignore()
    
    def dragLeaveEvent(self, event):
        """Handle drag leave event"""
        # Reset background color
        self.central_widget.setStyleSheet("")
    
    def dropEvent(self, event):
        """Handle drop event for drag-and-drop support"""
        # Reset background color
        self.central_widget.setStyleSheet("")
        
        if event.mimeData().hasUrls():
            folders = []
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    path = url.toLocalFile()
                    if os.path.isdir(path):
                        folders.append(path)
            
            if folders:
                # For now, use the first folder (later we can support multiple)
                self.selected_folder = folders[0]
                self.path_label.setText(self.selected_folder)
                self.scan_btn.setEnabled(True)
                
                # Optionally, auto-start scan
                # Uncomment the next line to automatically start scanning after drop
                # self.start_scan()
                
                event.acceptProposedAction()
            else:
                event.ignore()
        else:
            event.ignore()


class ScanWorker(QThread):
    progress = Signal(int)
    progress_detail = Signal(str, int, int, float)
    status = Signal(str)
    finished = Signal(dict)
    
    def __init__(self, folder):
        super().__init__()
        self.folder = folder
        self._should_stop = False
        
    def stop(self):
        self._should_stop = True
        
    def run(self):
        import time
        from core.cache import Cache
        from core.video_hash import VideoHash
        
        start_time = time.time()
        
        # Load cache
        cache = Cache()
        cache.load(self.folder)
        
        self.status.emit("ファイルをスキャン中...")
        files = Scanner.scan_directory(self.folder)
        total = len(files)
        
        blurry_images = []
        hashes = []
        
        # Process in batches to save memory
        batch_size = 100
        save_interval = 500  # Save cache every 500 files
        
        for i, f in enumerate(files):
            if self._should_stop:
                break
                
            try:
                # Get file modification time
                try:
                    mtime = os.path.getmtime(f)
                except:
                    mtime = 0
                    
                # Check cache
                cached = cache.get(f, mtime)
                
                # Determine if file is video
                ext = os.path.splitext(f)[1].lower()
                is_video = ext in {'.mp4', '.avi', '.mov', '.mkv'}
                
                if cached:
                    # Use cached values
                    h = cached.get('hash')
                    score = cached.get('blur_score', 0)
                else:
                    # Compute new values
                    if is_video:
                        h = VideoHash.compute_hash(f)
                        score = 0
                    else:
                        score = BlurDetector.calculate_blur_score(f)
                        h = HashEngine.compute_hash(f)
                    
                    # Cache the results
                    cache.set(f, mtime, h, score)
                
                # Add to results
                if not is_video and BlurDetector.is_blurry(score):
                    blurry_images.append((f, score))
                    
                hashes.append((f, h))
                
                # Emit progress less frequently for better performance
                if i % 5 == 0:
                    elapsed = time.time() - start_time
                    self.progress_detail.emit(f, i + 1, total, elapsed)
                    self.progress.emit(int((i / total) * 50))
                
                # Save cache periodically
                if i % save_interval == 0 and i > 0:
                    cache.save(self.folder)
                    
            except Exception as e:
                print(f"Error processing {f}: {e}")
                continue
                
        # Final cache save
        cache.save(self.folder)
        
        if not self._should_stop:
            self.status.emit("画像をグループ化中...")
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
