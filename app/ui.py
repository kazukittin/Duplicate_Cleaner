from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QAction, QPixmap
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QFileDialog, QSplitter, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QLabel, QToolBar, QPushButton, QProgressBar, QMessageBox,
    QHeaderView, QStyleFactory, QSlider, QHBoxLayout, QScrollArea, QFrame
)
from .workers import ScanWorker
from .models import ResultGroup, ResultItem
from .thumbnails import ThumbnailProvider
from .image_utils import format_bytes
from send2trash import send2trash
import os

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DupSnap — Duplicate & Blurry Finder")
        self.resize(1280, 780)

        splitter = QSplitter(self)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["選択", "種類", "スコア", "ファイル名", "解像度", "サイズ", "パス"])
        self.tree.header().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tree.header().setStretchLastSection(True)
        self.tree.itemSelectionChanged.connect(self.on_select)

        # Preview area: stacked - single image label + horizontal compare area
        right = QWidget()
        right_lay = QVBoxLayout(right)
        self.preview = QLabel("ここにプレビュー")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setStyleSheet("background:#121212;color:#aaa;border:1px solid #333; min-height:300px;")
        right_lay.addWidget(self.preview)

        # Horizontal compare scroller
        self.compare_scroll = QScrollArea()
        self.compare_scroll.setWidgetResizable(True)
        self.compare_container = QWidget()
        self.compare_layout = QHBoxLayout(self.compare_container)
        self.compare_layout.setContentsMargins(6,6,6,6)
        self.compare_layout.setSpacing(12)
        self.compare_scroll.setWidget(self.compare_container)
        self.compare_scroll.setMinimumHeight(260)
        right_lay.addWidget(self.compare_scroll)

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

        # Similarity threshold slider
        tb.addSeparator()
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(20)
        self.slider.setValue(5) # default
        self.slider.setFixedWidth(160)
        self.slider.valueChanged.connect(self.on_thresh_changed)
        tb.addWidget(QLabel(" 類似しきい値(Hamming)："))
        tb.addWidget(self.slider)
        self.lbl_thresh = QLabel("5")
        tb.addWidget(self.lbl_thresh)

        self.btn_rescan = QPushButton("再スキャン")
        self.btn_rescan.clicked.connect(self.start_scan)
        tb.addWidget(self.btn_rescan)

        self.btn_delete = QPushButton("選択を削除")
        self.btn_delete.clicked.connect(self.delete_checked)
        tb.addWidget(self.btn_delete)

        self.progress = QProgressBar(self)
        self.statusBar().addPermanentWidget(self.progress, 1)
        self.progress.setValue(0)

        self.setStyle(QStyleFactory.create("Fusion"))
        style_path = os.path.join(os.path.dirname(__file__), "styles.qss")
        if os.path.exists(style_path):
            with open(style_path, "r", encoding="utf8") as f:
                self.setStyleSheet(f.read())

        self.folder = None
        self.worker = None
        self.thumb = ThumbnailProvider()

    def on_thresh_changed(self, v: int):
        self.lbl_thresh.setText(str(v))

    def pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, "対象フォルダを選択")
        if d:
            self.folder = d
            self.statusBar().showMessage(f"対象: {d}")

    def start_scan(self):
        if not self.folder:
            QMessageBox.information(self, "フォルダ未選択", "先に対象フォルダを選んでね")
            return
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "実行中", "スキャンは既に実行中だよ")
            return
        self.tree.clear()
        self.preview.clear()
        self.clear_compare()
        self.progress.setValue(0)
        sim_thresh = self.slider.value()
        self.worker = ScanWorker(self.folder, sim_thresh=sim_thresh)
        self.worker.sig_progress.connect(self.progress.setValue)
        self.worker.sig_finished.connect(self.on_scan_finished)
        self.worker.sig_error.connect(lambda msg: QMessageBox.critical(self, "エラー", msg))
        self.worker.start()
        self.statusBar().showMessage("スキャン中…")

    def on_scan_finished(self, groups):
        self.statusBar().showMessage("解析完了")
        self.populate_tree(groups)

    def populate_tree(self, groups: list[ResultGroup]):
        for g in groups:
            root = QTreeWidgetItem(["", g.kind, f"{g.score:.2f}" if g.score else "-", f"{g.title}", "", "", ""])
            self.tree.addTopLevelItem(root)
            root.setFirstColumnSpanned(True)
            # decide keep (largest) for checkmarks
            if g.items:
                keep = max(g.items, key=lambda it: (it.pixels, it.size))
            else:
                keep = None
            for item in g.items:
                child = QTreeWidgetItem(["", "ファイル", f"{item.similarity:.2f}" if item.similarity is not None else "-",
                                          os.path.basename(item.path), f"{item.width}x{item.height}",
                                          format_bytes(item.size), item.path])
                # auto-check lower-res for deletion, keep biggest unchecked
                child.setCheckState(0, Qt.Unchecked if item is keep else Qt.Checked)
                root.addChild(child)
        self.tree.expandAll()

    def on_select(self):
        items = self.tree.selectedItems()
        if not items:
            return
        it = items[0]
        path = it.text(6)
        # If a file row selected -> single preview
        if os.path.isfile(path):
            pix = self.thumb.get_pixmap(path, max_w=900, max_h=520)
            if pix:
                self.preview.setPixmap(pix)
            else:
                self.preview.setText("プレビュー不可")
            # Clear compare strip
            self.clear_compare()
        else:
            # Group selected -> build horizontal compare thumbnails
            self.preview.setText("グループ比較（横並び）")
            self.build_group_compare(it)

    def clear_compare(self):
        # remove all widgets from compare_layout
        while self.compare_layout.count():
            item = self.compare_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)

    def build_group_compare(self, root_item: QTreeWidgetItem):
        self.clear_compare()
        # create small cards for each child
        for j in range(root_item.childCount()):
            ch = root_item.child(j)
            p = ch.text(6)
            card = self.make_thumb_card(p, ch)
            if card:
                self.compare_layout.addWidget(card)

        spacer = QFrame()
        spacer.setFrameShape(QFrame.NoFrame)
        self.compare_layout.addWidget(spacer)

    def make_thumb_card(self, path: str, row_item: QTreeWidgetItem):
        if not os.path.isfile(path):
            return None
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(6,6,6,6)
        lbl = QLabel()
        pix = self.thumb.get_pixmap(path, max_w=300, max_h=220)
        if pix:
            lbl.setPixmap(pix)
        else:
            lbl.setText("No preview")
        meta = QLabel(f"{os.path.basename(path)}\n{row_item.text(4)}  {row_item.text(5)}")
        meta.setStyleSheet("color:#bbb;")
        lay.addWidget(lbl)
        lay.addWidget(meta)
        w.setStyleSheet("background:#161616;border:1px solid #2a2a2a;border-radius:10px;")
        return w

    def delete_checked(self):
        to_delete = []
        for i in range(self.tree.topLevelItemCount()):
            root = self.tree.topLevelItem(i)
            for j in range(root.childCount()):
                ch = root.child(j)
                if ch.checkState(0) == Qt.Checked:
                    p = ch.text(6)
                    if p:
                        to_delete.append(p)
        if not to_delete:
            QMessageBox.information(self, "削除対象なし", "チェックが入ってないよ")
            return
        ok = QMessageBox.question(self, "確認", f"{len(to_delete)} 件をごみ箱へ移動するよ。OK？")
        if ok != QMessageBox.Yes:
            return
        failed = 0
        for p in to_delete:
            try:
                send2trash(p)
            except Exception:
                failed += 1
        if failed:
            QMessageBox.warning(self, "一部失敗", f"{failed} 件は削除に失敗したよ")
        else:
            QMessageBox.information(self, "完了", "削除したよ！")
        self.start_scan()
