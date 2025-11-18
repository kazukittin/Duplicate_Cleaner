from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QFileDialog, QSplitter, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QLabel, QPushButton, QProgressBar, QMessageBox,
    QHeaderView, QStyleFactory, QComboBox, QHBoxLayout, QScrollArea, QFrame, QAbstractItemView,
    QStackedWidget, QApplication, QTabWidget, QSlider, QSizePolicy, QSpacerItem, QCheckBox
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
        self.resize(1280, 820)

        self.accent_color = "#4F8CF5"
        self.danger_color = "#E05858"
        self.bg_color = "#202226"
        self.panel_color = "#1C1E22"

        self.setStyle(QStyleFactory.create("Fusion"))
        self._build_palette()

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(18, 16, 18, 16)
        root_layout.setSpacing(12)

        self.header = self._build_header(root)
        root_layout.addWidget(self.header)

        self.progress_bar = self._build_progress_bar()
        root_layout.addWidget(self.progress_bar)

        splitter = QSplitter(self)
        splitter.setHandleWidth(2)
        splitter.setChildrenCollapsible(False)

        sidebar = self._build_sidebar()
        splitter.addWidget(sidebar)

        content = self._build_content()
        splitter.addWidget(content)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 900])

        root_layout.addWidget(splitter)
        self.setCentralWidget(root)

        self.statusBar().setStyleSheet("color:#e0e0e0;background:#1a1b1f;border:1px solid #262830;")

        self.folder = None
        self.worker = None
        self.thumb = ThumbnailProvider()

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
        slider_map = {"weak": 0, "medium": 1, "strong": 2}
        if level_key in slider_map:
            self.sim_slider.blockSignals(True)
            self.sim_slider.setValue(slider_map[level_key])
            self.sim_slider.blockSignals(False)

    def pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, "対象フォルダを選択")
        if d:
            self.folder = d
            self.folder_label.setText(d)
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
        self.group_indicator.setText("グループ 0 / 0")


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
        self.update_group_indicator()

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
        self.update_group_indicator()

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
        self.compare_layout.addItem(QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))

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

    # ---- UI building helpers ----
    def _build_palette(self):
        palette = self.palette()
        palette.setColor(palette.Window, Qt.black)
        self.setPalette(palette)
        self.setStyleSheet(
            f"""
            QMainWindow {{ background: {self.bg_color}; color: #e6e6e6; }}
            QWidget {{ background: {self.bg_color}; color: #e6e6e6; font-size: 13px; }}
            QFrame#panel {{ background:{self.panel_color}; border:1px solid #2b2d33; border-radius:10px; }}
            QTabWidget::pane {{ border: 1px solid #2b2d33; border-radius:8px; top:-2px; }}
            QTabBar::tab {{ background:#25272d; padding:8px 14px; border:1px solid #2b2d33; border-bottom:0; border-top-left-radius:8px; border-top-right-radius:8px; margin-right:2px; }}
            QTabBar::tab:selected {{ background:{self.panel_color}; color:#fff; }}
            QLabel.sectionTitle {{ font-weight:600; letter-spacing:0.4px; color:#f5f5f7; }}
            QPushButton.primary {{ background:{self.accent_color}; color:#fff; border:1px solid #3e72c9; border-radius:8px; padding:10px 14px; }}
            QPushButton.primary:hover {{ background:#3f7ce6; }}
            QPushButton.ghost {{ background:transparent; border:1px solid #2b2d33; color:#d7d9df; border-radius:8px; padding:8px 12px; }}
            QPushButton.ghost:hover {{ border-color:{self.accent_color}; color:#fff; }}
            QPushButton.danger {{ background:transparent; border:1px solid {self.danger_color}; color:{self.danger_color}; border-radius:8px; padding:10px 14px; }}
            QPushButton.danger:hover {{ background:{self.danger_color}; color:#fff; }}
            QProgressBar {{ border:1px solid #2b2d33; border-radius:6px; text-align:center; background:#1a1b20; height:18px; }}
            QProgressBar::chunk {{ background:{self.accent_color}; border-radius:6px; }}
            QTreeWidget {{ background:{self.panel_color}; alternate-background-color:#23252b; border:1px solid #2b2d33; }}
            QTreeWidget::item:selected {{ background:{self.accent_color}; color:#fff; }}
            QScrollArea {{ border: none; }}
            QSlider::groove:horizontal {{ height:6px; background:#2b2d33; border-radius:3px; }}
            QSlider::handle:horizontal {{ background:{self.accent_color}; width:18px; border-radius:9px; margin:-6px 0; }}
            QSlider::handle:horizontal:hover {{ background:#3f7ce6; }}
            QCheckBox {{ spacing:8px; }}
            QToolTip {{ background:#2b2d33; color:#fff; border-radius:6px; padding:6px; }}
            """
        )

    def _build_header(self, parent: QWidget) -> QWidget:
        header = QFrame(parent)
        header.setObjectName("panel")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        title = QLabel("DupSnap")
        title.setStyleSheet("font-size:18px;font-weight:700; letter-spacing:0.4px;")
        subtitle = QLabel("Duplicate & Noise Cleaner")
        subtitle.setStyleSheet("color:#9ea0a6;font-size:12px;")

        title_wrap = QVBoxLayout()
        title_wrap.setContentsMargins(0,0,0,0)
        title_wrap.setSpacing(2)
        title_wrap.addWidget(title)
        title_wrap.addWidget(subtitle)

        layout.addLayout(title_wrap)
        layout.addStretch(1)

        self.btn_settings = QPushButton("設定")
        self.btn_settings.setToolTip("環境設定 (準備中)")
        self.btn_settings.setProperty("class", "ghost")
        self.btn_settings.setObjectName("ghost_btn")
        self.btn_settings.setStyleSheet("")
        self.btn_settings.setCursor(Qt.PointingHandCursor)

        self.btn_about = QPushButton("About")
        self.btn_about.setToolTip("アプリ情報")
        self.btn_about.setProperty("class", "ghost")
        self.btn_about.setCursor(Qt.PointingHandCursor)

        for btn in (self.btn_settings, self.btn_about):
            btn.setFixedHeight(32)
            btn.setStyleSheet("QPushButton{background:transparent;border:1px solid #2b2d33;border-radius:8px;padding:6px 12px;} QPushButton:hover{border-color:%s;color:#fff;}" % self.accent_color)
            layout.addWidget(btn)

        return header

    def _build_progress_bar(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("panel")
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(10)

        self.progress = QProgressBar(self)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFixedHeight(16)

        self.lbl_progress_detail = QLabel("待機中")
        self.lbl_progress_detail.setStyleSheet("color:#cdd0d6;")

        lay.addWidget(self.progress, 2)
        lay.addWidget(self.lbl_progress_detail, 1)
        return frame

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("panel")
        sidebar.setMinimumWidth(260)
        sidebar.setMaximumWidth(320)
        lay = QVBoxLayout(sidebar)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)

        folder_title = QLabel("スキャン対象")
        folder_title.setProperty("class", "sectionTitle")
        lay.addWidget(folder_title)

        folder_row = QHBoxLayout()
        folder_row.setSpacing(8)
        self.btn_pick = QPushButton("フォルダ選択")
        self.btn_pick.setCursor(Qt.PointingHandCursor)
        self.btn_pick.setStyleSheet(f"QPushButton{{background:{self.accent_color};color:#fff;border:1px solid #3e72c9;border-radius:8px;padding:10px 12px;}} QPushButton:hover{{background:#3f7ce6;}}");
        self.btn_pick.clicked.connect(self.pick_folder)
        folder_row.addWidget(self.btn_pick)

        lay.addLayout(folder_row)

        self.folder_label = QLabel("未選択")
        self.folder_label.setStyleSheet("color:#9ea0a6; word-break:break-all;")
        self.folder_label.setWordWrap(True)
        lay.addWidget(self.folder_label)

        sens_title = QLabel("感度設定")
        sens_title.setProperty("class", "sectionTitle")
        lay.addWidget(sens_title)

        slider_box = QVBoxLayout()
        slider_box.setSpacing(6)
        slider_box.addWidget(QLabel("類似度しきい値"))
        self.sim_slider = QSlider(Qt.Horizontal)
        self.sim_slider.setRange(0, 2)
        self.sim_slider.setValue(1)
        self.sim_slider.setToolTip("弱・中・強の3段階を切り替え")
        self.sim_slider.valueChanged.connect(self.on_sim_slider_changed)
        slider_box.addWidget(self.sim_slider)

        self.sim_combo = QComboBox()
        self.sim_combo.addItem("弱", "weak")
        self.sim_combo.addItem("中", "medium")
        self.sim_combo.addItem("強", "strong")
        self.sim_combo.setCurrentIndex(1)
        self.sim_combo.currentIndexChanged.connect(self.on_sim_level_changed)
        self.sim_combo.setVisible(False)
        slider_box.addWidget(self.sim_combo)
        lay.addLayout(slider_box)

        noise_box = QVBoxLayout()
        noise_box.setSpacing(6)
        noise_box.addWidget(QLabel("ノイズ検出レベル"))
        self.noise_combo = QComboBox()
        self.noise_combo.addItem("弱", "weak")
        self.noise_combo.addItem("中", "medium")
        self.noise_combo.addItem("強", "strong")
        self.noise_combo.setCurrentIndex(1)
        self.noise_combo.currentIndexChanged.connect(self.on_noise_level_changed)
        noise_box.addWidget(self.noise_combo)
        lay.addLayout(noise_box)

        options_title = QLabel("オプション")
        options_title.setProperty("class", "sectionTitle")
        lay.addWidget(options_title)

        opt_auto = QCheckBox("類似度が高い順に自動選択")
        opt_auto.setToolTip("今は表示のみ。スキャンロジックはそのままです")
        opt_preview = QCheckBox("画像を自動プレビュー")
        opt_preview.setChecked(True)
        opt_preview.setEnabled(False)
        for opt in (opt_auto, opt_preview):
            opt.setStyleSheet("color:#cfd1d7;")
            lay.addWidget(opt)

        lay.addStretch(1)

        self.btn_scan = QPushButton("スキャン開始")
        self.btn_scan.setCursor(Qt.PointingHandCursor)
        self.btn_scan.setProperty("class", "primary")
        self.btn_scan.setStyleSheet("")
        self.btn_scan.clicked.connect(self.start_scan)
        lay.addWidget(self.btn_scan)

        self.btn_delete = QPushButton("選択を削除")
        self.btn_delete.setCursor(Qt.PointingHandCursor)
        self.btn_delete.setProperty("class", "danger")
        self.btn_delete.setStyleSheet("")
        self.btn_delete.clicked.connect(self.delete_checked)
        lay.addWidget(self.btn_delete)

        return sidebar

    def _build_content(self) -> QWidget:
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)

        # Navigation bar for groups
        nav = QFrame()
        nav.setObjectName("panel")
        nav_lay = QHBoxLayout(nav)
        nav_lay.setContentsMargins(12, 10, 12, 10)
        nav_lay.setSpacing(10)

        self.btn_prev_group = QPushButton("◀ 前へ")
        self.btn_prev_group.setProperty("class", "ghost")
        self.btn_prev_group.setCursor(Qt.PointingHandCursor)
        self.btn_prev_group.clicked.connect(lambda: self.navigate_group(-1))
        self.btn_next_group = QPushButton("次へ ▶")
        self.btn_next_group.setProperty("class", "ghost")
        self.btn_next_group.setCursor(Qt.PointingHandCursor)
        self.btn_next_group.clicked.connect(lambda: self.navigate_group(1))

        self.group_indicator = QLabel("グループ 0 / 0")
        self.group_indicator.setStyleSheet("color:#dfe1e6;font-weight:600;")

        self.btn_load_more = QPushButton("もっと読み込む")
        self.btn_load_more.setProperty("class", "ghost")
        self.btn_load_more.setCursor(Qt.PointingHandCursor)
        self.btn_load_more.clicked.connect(self.load_more)

        nav_lay.addWidget(self.btn_prev_group)
        nav_lay.addWidget(self.btn_next_group)
        nav_lay.addSpacing(10)
        nav_lay.addWidget(self.group_indicator)
        nav_lay.addStretch(1)
        nav_lay.addWidget(self.btn_load_more)

        content_layout.addWidget(nav)

        # Preview area
        preview_panel = QFrame()
        preview_panel.setObjectName("panel")
        preview_panel_layout = QVBoxLayout(preview_panel)
        preview_panel_layout.setContentsMargins(12, 12, 12, 12)
        preview_panel_layout.setSpacing(10)

        self.stack = QStackedWidget()

        self.page_single = QWidget()
        ps_lay = QVBoxLayout(self.page_single)
        self.preview = QLabel("ここにプレビュー")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setStyleSheet("background:#0f1013;color:#aaa;border:1px solid #2b2d33;border-radius:10px;padding:12px;")
        ps_lay.addWidget(self.preview)
        self.stack.addWidget(self.page_single)

        self.page_pair = QWidget()
        pair_lay = QHBoxLayout(self.page_pair)
        self.preview_left = QLabel("左")
        self.preview_left.setAlignment(Qt.AlignCenter)
        self.preview_right = QLabel("右")
        self.preview_right.setAlignment(Qt.AlignCenter)
        for lbl in (self.preview_left, self.preview_right):
            lbl.setStyleSheet("background:#0f1013;color:#aaa;border:1px dashed #2b2d33;border-radius:10px;padding:10px;")
        pair_lay.addWidget(self.preview_left)
        pair_lay.addWidget(self.preview_right)
        self.stack.addWidget(self.page_pair)

        self.page_group = QWidget()
        pg_lay = QVBoxLayout(self.page_group)
        self.compare_scroll = QScrollArea()
        self.compare_scroll.setWidgetResizable(True)
        self.compare_container = QWidget()
        self.compare_layout = QHBoxLayout(self.compare_container)
        self.compare_layout.setContentsMargins(12, 8, 12, 8)
        self.compare_layout.setSpacing(12)
        self.compare_scroll.setWidget(self.compare_container)
        pg_lay.addWidget(self.compare_scroll)
        self.stack.addWidget(self.page_group)

        self.stack.setCurrentWidget(self.page_single)
        preview_panel_layout.addWidget(self.stack)
        content_layout.addWidget(preview_panel, 3)

        # Table area
        table_panel = QFrame()
        table_panel.setObjectName("panel")
        table_layout = QVBoxLayout(table_panel)
        table_layout.setContentsMargins(12, 10, 12, 12)
        table_layout.setSpacing(8)

        tab_title = QLabel("検出結果")
        tab_title.setProperty("class", "sectionTitle")
        table_layout.addWidget(tab_title)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.currentChanged.connect(self.on_tab_changed)
        table_layout.addWidget(self.tabs)

        content_layout.addWidget(table_panel, 5)
        return content

    def on_sim_slider_changed(self, value: int):
        mapping = {0: 0, 1: 1, 2: 2}
        if value in mapping:
            self.sim_combo.setCurrentIndex(mapping[value])

    def navigate_group(self, delta: int):
        tree = self.current_tree()
        if tree is None:
            return
        total = tree.topLevelItemCount()
        if total == 0:
            return
        current_idx = 0
        selected = tree.selectedItems()
        if selected:
            root_item = selected[0]
            if root_item.parent():
                root_item = root_item.parent()
            current_idx = tree.indexOfTopLevelItem(root_item)
        next_idx = max(0, min(total - 1, current_idx + delta))
        item = tree.topLevelItem(next_idx)
        if item:
            tree.setCurrentItem(item)
            tree.scrollToItem(item, QAbstractItemView.PositionAtCenter)
            self.update_group_indicator()

    def update_group_indicator(self):
        tree = self.current_tree()
        if tree is None:
            self.group_indicator.setText("グループ 0 / 0")
            return
        total = tree.topLevelItemCount()
        selected = tree.selectedItems()
        if selected:
            item = selected[0]
            if item.parent():
                item = item.parent()
            idx = tree.indexOfTopLevelItem(item)
            self.group_indicator.setText(f"グループ {idx+1} / {total}")
        else:
            self.group_indicator.setText(f"グループ 0 / {total}")
