from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QAction, QPixmap
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QFileDialog, QSplitter, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QLabel, QToolBar, QPushButton, QProgressBar, QMessageBox,
    QHeaderView, QStyleFactory, QComboBox, QHBoxLayout, QScrollArea, QFrame, QAbstractItemView,
    QStackedWidget, QApplication, QTabWidget
)
from .workers import ScanWorker
from .models import ResultGroup, ResultItem
from .thumbnails import ThumbnailProvider
from .image_utils import format_bytes
from .video_utils import is_video_path
from send2trash import send2trash
import os, stat, time

BATCH_SIZE = 1000

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DupSnap — Duplicate & Noisy Finder")
        self.resize(1280, 780)

        splitter = QSplitter(self)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.currentChanged.connect(self.on_tab_changed)

        tab_defs = [
            ("similar", "類似（重複）"),
            ("blur", "ブレ（ノイズ）"),
            ("video", "映像"),
        ]
        self._tab_keys = [key for key, _ in tab_defs]
        self._group_data = {}
        self._path_items: dict[str, list[QTreeWidgetItem]] = {}

        for key, title in tab_defs:
            tree = self._create_tree()
            tree.itemSelectionChanged.connect(self.on_select)
            self.tabs.addTab(tree, title)
            self._group_data[key] = {"tree": tree, "groups": [], "page": 0}

        left_layout.addWidget(self.tabs)
        splitter.addWidget(left_panel)

        right = QWidget()
        right_lay = QVBoxLayout(right)
        self.stack = QStackedWidget()

        self.page_single = QWidget()
        ps_lay = QVBoxLayout(self.page_single)
        self.preview = QLabel("ここにプレビュー")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setStyleSheet("background:#121212;color:#aaa;border:1px solid #333;")
        ps_lay.addWidget(self.preview)
        self.stack.addWidget(self.page_single)

        self.page_pair = QWidget()
        pair_lay = QHBoxLayout(self.page_pair)
        self.preview_left = QLabel("左")
        self.preview_left.setAlignment(Qt.AlignCenter)
        self.preview_right = QLabel("右")
        self.preview_right.setAlignment(Qt.AlignCenter)
        for lbl in (self.preview_left, self.preview_right):
            lbl.setStyleSheet("background:#101010;color:#aaa;border:1px dashed #333;")
        pair_lay.addWidget(self.preview_left)
        pair_lay.addWidget(self.preview_right)
        self.stack.addWidget(self.page_pair)

        self.page_group = QWidget()
        pg_lay = QVBoxLayout(self.page_group)
        self.compare_scroll = QScrollArea()
        self.compare_scroll.setWidgetResizable(True)
        self.compare_container = QWidget()
        self.compare_layout = QHBoxLayout(self.compare_container)
        self.compare_layout.setContentsMargins(6,6,6,6)
        self.compare_layout.setSpacing(12)
        self.compare_scroll.setWidget(self.compare_container)
        pg_lay.addWidget(self.compare_scroll)
        self.stack.addWidget(self.page_group)

        self.stack.setCurrentWidget(self.page_single)
        right_lay.addWidget(self.stack)

        splitter.addWidget(right)
        splitter.setSizes([780, 500])

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.addWidget(splitter)
        self.setCentralWidget(central)

        tb = QToolBar("Main", self)
        tb.setIconSize(QSize(18,18))
        self.addToolBar(tb)

        act_open = QAction("フォルダ選択", self)
        act_open.triggered.connect(self.pick_folder)
        tb.addAction(act_open)

        self.btn_scan = QPushButton("スキャン開始")
        self.btn_scan.clicked.connect(self.start_scan)
        tb.addWidget(self.btn_scan)

        tb.addSeparator()
        tb.addWidget(QLabel(" 類似検出："))
        self.sim_combo = QComboBox()
        self.sim_combo.addItem("弱", "weak")
        self.sim_combo.addItem("中", "medium")
        self.sim_combo.addItem("強", "strong")
        self.sim_combo.setCurrentIndex(1)
        self.sim_combo.currentIndexChanged.connect(self.on_sim_level_changed)
        tb.addWidget(self.sim_combo)

        tb.addSeparator()
        tb.addWidget(QLabel(" ノイズ検出："))
        self.noise_combo = QComboBox()
        self.noise_combo.addItem("弱", "weak")
        self.noise_combo.addItem("中", "medium")
        self.noise_combo.addItem("強", "strong")
        self.noise_combo.setCurrentIndex(1)
        self.noise_combo.currentIndexChanged.connect(self.on_noise_level_changed)
        tb.addWidget(self.noise_combo)

        self.btn_delete = QPushButton("選択を削除")
        self.btn_delete.clicked.connect(self.delete_checked)
        tb.addWidget(self.btn_delete)

        self.progress = QProgressBar(self)
        self.statusBar().addPermanentWidget(self.progress, 1)
        self.progress.setValue(0)
        self.lbl_progress_detail = QLabel("待機中")
        self.lbl_progress_detail.setStyleSheet("color:#ddd;padding-left:8px;")
        self.statusBar().addPermanentWidget(self.lbl_progress_detail)

        self.setStyle(QStyleFactory.create("Fusion"))
        self.folder = None
        self.worker = None
        self.thumb = ThumbnailProvider()

        self._all_groups = []
        self._page = 0

    def on_noise_level_changed(self, index: int):
        level_text = self.noise_combo.itemText(index) if index >= 0 else self.noise_combo.currentText()
        self.statusBar().showMessage(f"ノイズ検出感度：{level_text}", 2000)

    def on_sim_level_changed(self, index: int):
        level_text = self.sim_combo.itemText(index) if index >= 0 else self.sim_combo.currentText()
        level_key = self.sim_combo.itemData(index) if index >= 0 else self.sim_combo.currentData()
        thresh = ScanWorker.SIMILARITY_LEVELS.get(level_key, ScanWorker.SIMILARITY_LEVELS.get("medium"))
        detail = f" (ハミング≦{thresh})" if thresh is not None else ""
        self.statusBar().showMessage(f"類似判定感度：{level_text}{detail}", 2000)

    def pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, "対象フォルダを選択")
        if d:
            self.folder = d
            self.statusBar().showMessage(f"対象: {d}")

    def start_scan(self):
        if not self.folder:
            QMessageBox.information(self, "フォルダ未選択", "先に対象フォルダを選んでね"); return
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "実行中", "スキャンは既に実行中だよ"); return

        self.preview.clear(); self.clear_compare(); self.progress.setValue(0)
        self._all_groups = []; self._page = 0
        self._path_items.clear()
        for data in self._group_data.values():
            data["tree"].clear()
            data["groups"] = []
            data["page"] = 0

        # ★ 追加：DBをスキャン対象フォルダ内に作る
        import os
        db_dir = os.path.join(self.folder, ".dupsnap")
        os.makedirs(db_dir, exist_ok=True)
        db_path = os.path.join(db_dir, "cache.db")

        sim_level = self.sim_combo.currentData()
        # ★ db_path を渡す
        noise_level = self.noise_combo.currentData()
        self.worker = ScanWorker(self.folder, sim_level=sim_level, noise_level=noise_level, db_path=db_path)
        self.worker.sig_progress.connect(self.progress.setValue)
        self.worker.sig_stage.connect(self.update_stage)
        self.worker.sig_finished.connect(self.on_scan_finished)
        self.worker.sig_error.connect(self.on_scan_error)
        self.worker.start()
        self.statusBar().showMessage("スキャン中…")
        self.lbl_progress_detail.setText("準備中…")


    def on_scan_finished(self, groups):
        self.statusBar().showMessage("解析完了")
        self.lbl_progress_detail.setText("完了")
        self._all_groups = groups or []
        self._page = 0
        for data in self._group_data.values():
            tree = data["tree"]
            tree.setUpdatesEnabled(False)
            tree.clear()
            tree.setUpdatesEnabled(True)
            data["groups"] = []
            data["page"] = 0
        self._path_items.clear()

        categorized = {"similar": [], "blur": [], "video": []}
        for g in self._all_groups:
            if g.kind == "ノイズ":
                categorized["blur"].append(g)
            elif any(is_video_path(it.path) for it in g.items):
                categorized["video"].append(g)
            else:
                categorized["similar"].append(g)

        for key, groups_list in categorized.items():
            if key in ("similar", "blur"):
                groups_list.sort(key=lambda grp: grp.score if grp.score is not None else -1, reverse=True)
            if key in self._group_data:
                self._group_data[key]["groups"] = groups_list
                self._group_data[key]["page"] = 0
                self._group_data[key]["tree"].clear()

        for key in self._tab_keys:
            while self.load_more(tab_key=key):
                pass

    def load_more(self, tab_key: str | None = None) -> bool:
        if tab_key is None:
            tab_key = self.current_tab_key()
        if tab_key not in self._group_data:
            return False
        data = self._group_data[tab_key]
        groups = data["groups"]
        if not groups:
            return False
        start = data["page"] * BATCH_SIZE
        end = min(len(groups), start + BATCH_SIZE)
        if start >= end:
            return False
        tree = data["tree"]
        tree.setUpdatesEnabled(False)
        for g in groups[start:end]:
            kind_label = "映像" if tab_key == "video" else g.kind
            score_text = str(int(round(g.score))) if g.score is not None else "-"
            root = QTreeWidgetItem(["", kind_label, score_text, "-", g.title, "", "", ""])
            tree.addTopLevelItem(root)
            root.setFirstColumnSpanned(True)
            if g.kind == "ノイズ":
                keep = None
            else:
                keep = max(g.items, key=lambda it: (it.width*it.height, it.size)) if g.items else None
            for item in g.items:
                sim_text = str(int(round(item.similarity))) if item.similarity is not None else "-"
                noise_text = str(int(round(item.noise_score))) if getattr(item, "noise_score", None) is not None else "-"
                child = QTreeWidgetItem(["", "ファイル", sim_text,
                                          noise_text,
                                          os.path.basename(item.path), f"{item.width}x{item.height}",
                                          format_bytes(item.size), item.path])
                child.setCheckState(0, Qt.Unchecked if item is keep else Qt.Checked)
                root.addChild(child)
                self._register_item(item.path, child)
        tree.setUpdatesEnabled(True)
        tree.viewport().update()
        QApplication.processEvents()
        tree.expandAll()
        data["page"] += 1
        return True

    def update_stage(self, text: str):
        self.lbl_progress_detail.setText(text)

    def on_scan_error(self, msg: str):
        QMessageBox.critical(self, "エラー", msg)
        self.lbl_progress_detail.setText("エラー")

    def on_select(self):
        tree = self.sender()
        if not isinstance(tree, QTreeWidget):
            tree = self.current_tree()
        if tree is None:
            return
        items = tree.selectedItems()
        if not items: return
        file_rows = [it for it in items if os.path.isfile(it.text(7))]
        if len(file_rows) == 2 and file_rows[0].parent() is file_rows[1].parent():
            self.show_pair(file_rows[0].text(7), file_rows[1].text(7))
            self.stack.setCurrentWidget(self.page_pair)
            return
        it = items[0]; path = it.text(7)
        if os.path.isfile(path):
            pix = self.thumb.get_pixmap(path, max_w=900, max_h=520)
            if pix: self.preview.setPixmap(pix)
            else: self.preview.setText("プレビュー不可")
            self.stack.setCurrentWidget(self.page_single)
        else:
            self.build_group_compare(it)
            self.stack.setCurrentWidget(self.page_group)

    def clear_compare(self):
        layout = getattr(self, "compare_layout", None)
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w: w.setParent(None)

    def build_group_compare(self, root_item):
        self.clear_compare()
        for j in range(root_item.childCount()):
            ch = root_item.child(j); p = ch.text(7)
            card = self.make_thumb_card(p, ch)
            if card: self.compare_layout.addWidget(card)

    def make_thumb_card(self, path, row_item):
        if not os.path.isfile(path): return None
        w = QWidget(); lay = QVBoxLayout(w)
        lbl = QLabel()
        pix = self.thumb.get_pixmap(path, max_w=300, max_h=220)
        if pix: lbl.setPixmap(pix)
        else: lbl.setText("No preview")
        meta = QLabel(f"{row_item.text(4)}\n{row_item.text(5)}  {row_item.text(6)}\nノイズ指標: {row_item.text(3)}")
        meta.setStyleSheet("color:#bbb;")
        lay.addWidget(lbl); lay.addWidget(meta)
        w.setStyleSheet("background:#161616;border:1px solid #2a2a2a;border-radius:10px;")
        return w

    def show_pair(self, path_left, path_right):
        pix_l = self.thumb.get_pixmap(path_left, max_w=640, max_h=540)
        pix_r = self.thumb.get_pixmap(path_right, max_w=640, max_h=540)
        if pix_l: self.preview_left.setPixmap(pix_l)
        else: self.preview_left.setText("左: プレビュー不可")
        if pix_r: self.preview_right.setPixmap(pix_r)
        else: self.preview_right.setText("右: プレビュー不可")

    def delete_checked(self):
        try: self.preview.clear()
        except: pass
        try: self.clear_compare()
        except: pass
        paths = []
        seen = set()
        for tree in self._iter_trees():
            for i in range(tree.topLevelItemCount()):
                root = tree.topLevelItem(i)
                for j in range(root.childCount()):
                    ch = root.child(j)
                    if ch.checkState(0) == Qt.Checked:
                        p = ch.text(7)
                        if p and p not in seen:
                            paths.append(p)
                            seen.add(p)
        if not paths:
            QMessageBox.information(self, "削除対象なし", "チェックが入ってないよ"); return
        ok = QMessageBox.question(self, "確認", f"{len(paths)} 件をごみ箱へ移動するよ。OK？")
        if ok != QMessageBox.Yes: return

        errors = []; deleted = 0
        removed_paths = []
        def win_long(path):
            if os.name == "nt":
                ap = os.path.abspath(path)
                if not ap.startswith('\\?\\') and len(ap) > 240:
                    return '\\?\\' + ap.replace('/', '\\')
                return ap
            return path

        for p in paths:
            pp = win_long(p)
            try:
                mode = os.stat(pp).st_mode
                if not (mode & stat.S_IWUSR):
                    os.chmod(pp, stat.S_IWUSR | stat.S_IRUSR)
                send2trash(pp); deleted += 1
                removed_paths.append(p)
            except Exception as e1:
                try:
                    os.remove(pp); deleted += 1
                    removed_paths.append(p)
                except Exception as e2:
                    errors.append((p, str(e1), str(e2)))
        if errors:
            log_path = os.path.join(os.getcwd(), "dup_del_errors.log")
            with open(log_path, "a", encoding="utf-8") as lf:
                lf.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
                for p, e1, e2 in errors: lf.write(f"{p}\n -> {e1}\n -> fallback {e2}\n")
            msg = "\n".join([os.path.basename(p) for p,_,_ in errors[:3]])
            if len(errors) > 3: msg += f"\n…ほか {len(errors)-3} 件"
            QMessageBox.warning(self, "一部失敗", f"{deleted} 件削除、{len(errors)} 件失敗\n詳細: dup_del_errors.log を確認してね\n{msg}")
        else:
            QMessageBox.information(self, "完了", f"{deleted} 件削除したよ！")
        for p in removed_paths:
            self._remove_path_everywhere(p)
        self.start_scan()

    def _create_tree(self) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        tree.setHeaderLabels(["選択", "種類", "スコア", "ノイズ指標", "ファイル名", "解像度", "サイズ", "パス"])
        tree.header().setSectionResizeMode(QHeaderView.ResizeToContents)
        tree.header().setStretchLastSection(True)
        return tree

    def current_tab_key(self) -> str:
        idx = self.tabs.currentIndex()
        if 0 <= idx < len(self._tab_keys):
            return self._tab_keys[idx]
        return "similar"

    def current_tree(self) -> QTreeWidget | None:
        key = self.current_tab_key()
        data = self._group_data.get(key)
        return data["tree"] if data else None

    def on_tab_changed(self, index: int):
        self.clear_compare()
        preview = getattr(self, "preview", None)
        if preview is not None:
            preview.clear()

    def _iter_trees(self):
        for key in self._tab_keys:
            data = self._group_data.get(key)
            if data:
                yield data["tree"]

    def _register_item(self, path: str, item: QTreeWidgetItem):
        if not path:
            return
        self._path_items.setdefault(path, []).append(item)

    def _remove_path_everywhere(self, path: str):
        items = self._path_items.pop(path, [])
        for item in items:
            parent = item.parent()
            if parent is None:
                continue
            tree = parent.treeWidget()
            idx = parent.indexOfChild(item)
            if idx >= 0:
                parent.takeChild(idx)
            if parent.childCount() == 0 and tree is not None:
                top_idx = tree.indexOfTopLevelItem(parent)
                if top_idx >= 0:
                    tree.takeTopLevelItem(top_idx)
