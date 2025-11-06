from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QAction, QPixmap
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QFileDialog, QSplitter, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QLabel, QToolBar, QPushButton, QProgressBar, QMessageBox,
    QHeaderView, QStyleFactory, QSlider, QHBoxLayout, QScrollArea, QFrame, QAbstractItemView, QStackedWidget, QApplication
)
from .workers import ScanWorker
from .models import ResultGroup, ResultItem
from .thumbnails import ThumbnailProvider
from .image_utils import format_bytes
from send2trash import send2trash
import os, stat, time

BATCH_SIZE = 1000

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DupSnap — Duplicate & Blurry Finder")
        self.resize(1280, 780)

        splitter = QSplitter(self)

        self.tree = QTreeWidget()
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setHeaderLabels(["選択", "種類", "スコア", "ブレ指標", "ファイル名", "解像度", "サイズ", "パス"])
        self.tree.header().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tree.header().setStretchLastSection(True)
        self.tree.itemSelectionChanged.connect(self.on_select)

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

        splitter.addWidget(self.tree)
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
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(0); self.slider.setMaximum(20); self.slider.setValue(5)
        self.slider.setFixedWidth(160)
        self.slider.valueChanged.connect(self.on_thresh_changed)
        tb.addWidget(QLabel(" 類似しきい値(Hamming)："))
        tb.addWidget(self.slider)
        self.lbl_thresh = QLabel("5")
        tb.addWidget(self.lbl_thresh)

        tb.addSeparator()
        self.blur_slider = QSlider(Qt.Horizontal)
        self.blur_slider.setMinimum(0); self.blur_slider.setMaximum(500); self.blur_slider.setValue(80)
        self.blur_slider.setFixedWidth(160)
        self.blur_slider.valueChanged.connect(self.on_blur_thresh_changed)
        tb.addWidget(QLabel(" ブレしきい値："))
        tb.addWidget(self.blur_slider)
        self.lbl_blur_thresh = QLabel("80")
        tb.addWidget(self.lbl_blur_thresh)

        self.btn_rescan = QPushButton("再スキャン")
        self.btn_rescan.clicked.connect(self.start_scan)
        tb.addWidget(self.btn_rescan)

        self.btn_showmore = QPushButton("もっと表示")
        self.btn_showmore.clicked.connect(self.load_more)
        self.btn_showmore.setEnabled(False)
        tb.addWidget(self.btn_showmore)

        self.btn_delete = QPushButton("選択を削除")
        self.btn_delete.clicked.connect(self.delete_checked)
        tb.addWidget(self.btn_delete)

        self.progress = QProgressBar(self)
        self.statusBar().addPermanentWidget(self.progress, 1)
        self.progress.setValue(0)

        self.setStyle(QStyleFactory.create("Fusion"))
        self.folder = None
        self.worker = None
        self.thumb = ThumbnailProvider()

        self._all_groups = []
        self._page = 0

    def on_thresh_changed(self, v: int):
        self.lbl_thresh.setText(str(v))

    def on_blur_thresh_changed(self, v: int):
        self.lbl_blur_thresh.setText(str(v))

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

        self.tree.clear(); self.preview.clear(); self.clear_compare(); self.progress.setValue(0)
        self._all_groups = []; self._page = 0; self.btn_showmore.setEnabled(False)

        # ★ 追加：DBをスキャン対象フォルダ内に作る
        import os
        db_dir = os.path.join(self.folder, ".dupsnap")
        os.makedirs(db_dir, exist_ok=True)
        db_path = os.path.join(db_dir, "cache.db")

        sim_thresh = self.slider.value()
        # ★ db_path を渡す
        blur_thresh = self.blur_slider.value()
        self.worker = ScanWorker(self.folder, sim_thresh=sim_thresh, blur_thresh=blur_thresh, db_path=db_path)
        self.worker.sig_progress.connect(self.progress.setValue)
        self.worker.sig_finished.connect(self.on_scan_finished)
        self.worker.sig_error.connect(lambda msg: QMessageBox.critical(self, "エラー", msg))
        self.worker.start()
        self.statusBar().showMessage("スキャン中…")


    def on_scan_finished(self, groups):
        self.statusBar().showMessage("解析完了")
        self._all_groups = groups or []
        self._page = 0
        self.tree.setUpdatesEnabled(False)
        self.tree.clear()
        self.tree.setUpdatesEnabled(True)
        self.load_more()
        self.btn_showmore.setEnabled(len(self._all_groups) > BATCH_SIZE)

    def load_more(self):
        if not self._all_groups: return
        start = self._page * BATCH_SIZE
        end = min(len(self._all_groups), start + BATCH_SIZE)
        if start >= end:
            self.btn_showmore.setEnabled(False); return
        self.tree.setUpdatesEnabled(False)
        for g in self._all_groups[start:end]:
            root = QTreeWidgetItem(["", g.kind, f"{g.score:.2f}" if g.score is not None else "-", "-", g.title, "", "", ""])
            self.tree.addTopLevelItem(root)
            root.setFirstColumnSpanned(True)
            if g.kind == "ブレ":
                keep = None
            else:
                keep = max(g.items, key=lambda it: (it.width*it.height, it.size)) if g.items else None
            for item in g.items:
                child = QTreeWidgetItem(["", "ファイル", f"{item.similarity:.2f}" if item.similarity is not None else "-",
                                          f"{item.blur:.1f}" if item.blur is not None else "-",
                                          os.path.basename(item.path), f"{item.width}x{item.height}",
                                          format_bytes(item.size), item.path])
                child.setCheckState(0, Qt.Unchecked if item is keep else Qt.Checked)
                root.addChild(child)
        self.tree.setUpdatesEnabled(True)
        self.tree.viewport().update()
        QApplication.processEvents()
        self.tree.expandAll()
        self._page += 1
        self.btn_showmore.setEnabled(self._page * BATCH_SIZE < len(self._all_groups))

    def on_select(self):
        items = self.tree.selectedItems()
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
        while self.compare_layout.count():
            item = self.compare_layout.takeAt(0)
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
        meta = QLabel(f"{row_item.text(4)}\n{row_item.text(5)}  {row_item.text(6)}\nブレ指標: {row_item.text(3)}")
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
        to_delete = []
        for i in range(self.tree.topLevelItemCount()):
            root = self.tree.topLevelItem(i)
            for j in range(root.childCount()):
                ch = root.child(j)
                if ch.checkState(0) == Qt.Checked:
                    p = ch.text(7)
                    if p: to_delete.append((root, ch, p))
        if not to_delete:
            QMessageBox.information(self, "削除対象なし", "チェックが入ってないよ"); return
        ok = QMessageBox.question(self, "確認", f"{len(to_delete)} 件をごみ箱へ移動するよ。OK？")
        if ok != QMessageBox.Yes: return

        errors = []; deleted = 0
        def win_long(path):
            if os.name == "nt":
                ap = os.path.abspath(path)
                if not ap.startswith('\\?\\') and len(ap) > 240:
                    return '\\?\\' + ap.replace('/', '\\')
                return ap
            return path

        for root, ch, p in to_delete:
            pp = win_long(p)
            try:
                mode = os.stat(pp).st_mode
                if not (mode & stat.S_IWUSR):
                    os.chmod(pp, stat.S_IWUSR | stat.S_IRUSR)
                send2trash(pp); deleted += 1
                parent = ch.parent(); idx = parent.indexOfChild(ch); parent.takeChild(idx)
            except Exception as e1:
                try:
                    os.remove(pp); deleted += 1
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
        self.start_scan()
