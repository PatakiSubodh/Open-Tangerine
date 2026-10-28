"""Window for one editing tool: a live preview or editing canvas on the left, the tool's options on the right.
The work itself runs through the isolated worker (see toolops.py); the window only builds the request."""
import os, time
from pathlib import Path
from PySide6.QtCore import Qt, QPointF, QRectF, QSize, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QImage, QPainter, QPen, QPixmap, QTransform
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QProgressBar, QPushButton, QScrollArea, QSlider, QSpinBox, QVBoxLayout, QWidget)
import engine, prefs, toolops, theme, dialogs, settings_dialog
from batch import Batch

ORANGE = QColor('#ff610a')

def pil_to_pixmap(im):
    im = im.convert('RGBA');image = QImage(im.tobytes('raw', 'RGBA'), im.width, im.height, im.width * 4, QImage.Format_RGBA8888);return QPixmap.fromImage(image.copy())

def load_preview(path, side=720):
    """Downscaled, EXIF-upright copy of an image for previews. Coordinates stay valid because the aspect is kept."""
    im = engine.open_image(Path(path));im.thumbnail((side, side));return im.convert('RGBA')

def seconds_text(value): return f'{int(value // 60)}:{value % 60:04.1f}'

class SliderField(QWidget):
    changed = Signal()
    def __init__(self, f):
        super().__init__();self.f = f;row = QHBoxLayout(self);row.setContentsMargins(0, 0, 0, 0)
        self.slider = QSlider(Qt.Horizontal);self.slider.setRange(0, 200);self.label = QLabel();self.label.setMinimumWidth(42);row.addWidget(self.slider, 1);row.addWidget(self.label)
        self.set(f.default);self.slider.valueChanged.connect(lambda _: (self.refresh(), self.changed.emit()))
    def set(self, v): self.slider.setValue(round((float(v) - self.f.lo) / (self.f.hi - self.f.lo) * 200));self.refresh()
    def value(self): return self.f.lo + self.slider.value() / 200 * (self.f.hi - self.f.lo)
    def refresh(self): self.label.setText(f'{self.value():+.2f}' if self.f.lo < 0 else f'{self.value():g}')

class ColorField(QPushButton):
    """A swatch with its hex code; opens the app's own colour dialog."""
    changed = Signal()
    def __init__(self, default):
        super().__init__();self.colour = default;self.setMinimumWidth(120);self.setCursor(Qt.PointingHandCursor);self.clicked.connect(self.pick);self.paint()
    def paint(self):
        dark = QColor(self.colour).lightness() < 128
        self.setText(self.colour.upper());self.setStyleSheet(f'QPushButton{{background:{self.colour};color:{"#f5f3ed" if dark else "#101010"};border:2px solid #666;border-radius:6px;font-weight:bold}}QPushButton:hover{{border-color:#ff762b}}')
    def pick(self):
        c = dialogs.pick_colour(QColor(self.colour), self.window(), 'Choose a colour')
        if c is not None and c.isValid(): self.colour = c.name();self.paint();self.changed.emit()

class OptionsForm(QWidget):
    """Builds a form from a tool's declared fields and hides rows whose `when` condition is not met."""
    changed = Signal()
    def __init__(self, fields):
        super().__init__();self.fields = fields;self.rows = {};form = QFormLayout(self);form.setContentsMargins(0, 0, 0, 0);form.setLabelAlignment(Qt.AlignLeft);form.setVerticalSpacing(12);form.setHorizontalSpacing(14);form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        group = ''
        for f in fields:
            if f.group and f.group != group: group = f.group;heading = theme.label(group.upper(), 'heading');form.addRow(heading)
            if f.kind == 'int': w = QSpinBox();w.setRange(int(f.lo), int(f.hi));w.setValue(int(f.default));w.setSuffix(f.suffix);w.valueChanged.connect(self.touched)
            elif f.kind == 'float' and f.hi - f.lo <= 8 and (f.lo < 0 or f.group): w = SliderField(f);w.changed.connect(self.touched)
            elif f.kind == 'float': w = QDoubleSpinBox();w.setRange(f.lo, f.hi);w.setDecimals(2);w.setValue(float(f.default));w.setSuffix(f.suffix);w.valueChanged.connect(self.touched)
            elif f.kind == 'choice':
                w = QComboBox()
                for value, label in f.options: w.addItem(label, value)
                w.setCurrentIndex(max(0, w.findData(f.default)));w.currentIndexChanged.connect(self.touched)
            elif f.kind == 'bool': w = QCheckBox(f.label);w.setChecked(bool(f.default));w.stateChanged.connect(self.touched)
            elif f.kind == 'color': w = ColorField(f.default);w.changed.connect(self.touched)
            else: w = QLineEdit(str(f.default or ''));w.setMaxLength(200);w.textChanged.connect(self.touched)
            if f.hint: w.setToolTip(f.hint)
            label = QLabel('' if f.kind == 'bool' else f.label);label.setObjectName('muted');self.rows[f.key] = (label, w);form.addRow(label, w)
        self.refresh_rows()
    def value_of(self, f):
        w = self.rows[f.key][1]
        if f.kind in ('int', 'float') and not isinstance(w, SliderField): return w.value()
        if isinstance(w, SliderField): return w.value()
        if f.kind == 'choice': return w.currentData()
        if f.kind == 'bool': return w.isChecked()
        if f.kind == 'color': return w.colour
        return w.text()
    def values(self): return {f.key: self.value_of(f) for f in self.fields}
    def touched(self, *_): self.refresh_rows();self.changed.emit()
    def reset(self):
        """Put every control back to its declared default (one change signal at the end)."""
        for f in self.fields:
            w = self.rows[f.key][1];w.blockSignals(True)
            try:
                if isinstance(w, SliderField): w.slider.blockSignals(True);w.set(f.default);w.slider.blockSignals(False)
                elif f.kind in ('int', 'float'): w.setValue(f.default)
                elif f.kind == 'choice': w.setCurrentIndex(max(0, w.findData(f.default)))
                elif f.kind == 'bool': w.setChecked(bool(f.default))
                elif f.kind == 'color': w.colour = f.default;w.paint()
                else: w.setText(str(f.default or ''))
            finally: w.blockSignals(False)
        self.touched()
    def refresh_rows(self):
        current = self.values()
        for f in self.fields:
            key, want = f.when if f.when else (None, None);show = True
            if key: show = current.get(key) in (want if isinstance(want, tuple) else (want,))
            label, w = self.rows[f.key];label.setVisible(show);w.setVisible(show)

class RegionCanvas(QWidget):
    """Shows the picture and lets the user drag rectangles (crop: exactly one; redact: several). Rectangles are 0–1 fractions."""
    changed = Signal()
    def __init__(self, pixmap, single):
        super().__init__();self.pixmap = pixmap;self.single = single;self.rects = [];self.drag = None;self.ratio = None;self.setMinimumSize(360, 300);self.setCursor(Qt.CrossCursor);self.setMouseTracking(True)
    def frame(self):
        w, h = self.pixmap.width(), self.pixmap.height();s = min((self.width() - 16) / w, (self.height() - 16) / h);fw, fh = w * s, h * s
        return QRectF((self.width() - fw) / 2, (self.height() - fh) / 2, fw, fh)
    def to_unit(self, pos):
        f = self.frame();return (min(1, max(0, (pos.x() - f.left()) / f.width())), min(1, max(0, (pos.y() - f.top()) / f.height())))
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton: self.drag = (self.to_unit(e.position()), self.to_unit(e.position()))
    def mouseMoveEvent(self, e):
        if self.drag: self.drag = (self.drag[0], self.to_unit(e.position()));self.update()
    def mouseReleaseEvent(self, e):
        if not self.drag: return
        (x1, y1), (x2, y2) = self.drag[0], self.to_unit(e.position());self.drag = None
        if self.ratio:
            # Keep the shape, and shrink the box rather than let it run off the picture.
            f = self.frame();dx = abs(x2 - x1) * f.width();dy = dx / self.ratio;sx = 1 if x2 >= x1 else -1;sy = 1 if y2 >= y1 else -1
            room = (1 - y1 if sy > 0 else y1) * f.height();scale = min(1.0, room / dy) if dy else 1.0;dx *= scale;dy *= scale
            x2 = x1 + sx * dx / f.width();y2 = y1 + sy * dy / f.height()
        x, y, w, h = min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1)
        if w > .01 and h > .01:
            if self.single: self.rects = [(x, y, w, h)]
            else: self.rects.append((x, y, w, h))
            self.changed.emit()
        self.update()
    def clear(self): self.rects = [];self.changed.emit();self.update()
    def undo(self):
        if self.rects: self.rects.pop();self.changed.emit();self.update()
    def paintEvent(self, _):
        p = QPainter(self);p.setRenderHint(QPainter.SmoothPixmapTransform);p.setRenderHint(QPainter.Antialiasing);p.setBrush(QColor('#101010'));p.setPen(Qt.NoPen);p.drawRoundedRect(QRectF(self.rect()), 10, 10);f = self.frame();p.drawPixmap(f.toRect(), self.pixmap)
        shown = list(self.rects)
        if self.drag: (x1, y1), (x2, y2) = self.drag;shown.append((min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1)))
        def box(r): return QRectF(f.left() + r[0] * f.width(), f.top() + r[1] * f.height(), r[2] * f.width(), r[3] * f.height())
        if self.single and shown:
            r = box(shown[-1]);shade = QColor(0, 0, 0, 150)
            for part in (QRectF(f.left(), f.top(), f.width(), r.top() - f.top()), QRectF(f.left(), r.bottom(), f.width(), f.bottom() - r.bottom()), QRectF(f.left(), r.top(), r.left() - f.left(), r.height()), QRectF(r.right(), r.top(), f.right() - r.right(), r.height())): p.fillRect(part, shade)
            p.setPen(QPen(ORANGE, 2));p.setBrush(Qt.NoBrush);p.drawRect(r)
        else:
            for i, r in enumerate(shown): b = box(r);p.setPen(QPen(ORANGE, 2));p.setBrush(QColor(255, 97, 10, 70));p.drawRect(b);p.setPen(QColor('#f5f3ed'));p.drawText(b.adjusted(4, 2, 0, 0), Qt.AlignTop | Qt.AlignLeft, str(i + 1))

class ToolWindow(QDialog):
    def __init__(self, tool, paths, settings, parent=None):
        super().__init__(parent);self.tool = tool;self.paths = [str(p) for p in paths];self.settings = settings;self.batch = None;self.outputs = [];self.canvas = None;self.order_list = None;self.page_list = None;self.preview_label = None;self.source = None
        self.setWindowTitle(f'{tool.title} · Open Tangerine');self.resize(940, 620);self.setAttribute(Qt.WA_DeleteOnClose, False)
        icon = Path(__file__).with_name('icon.png')
        if icon.exists(): self.setWindowIcon(QIcon(str(icon)))
        root = QVBoxLayout(self);root.setContentsMargins(24, 20, 24, 18);root.setSpacing(12)
        head = QHBoxLayout();root.addLayout(head);titles = QVBoxLayout();titles.setSpacing(2);head.addLayout(titles, 1)
        titles.addWidget(theme.label(tool.title, 'title'));titles.addWidget(theme.label(tool.caption, 'muted'))
        names = Path(self.paths[0]).name if len(self.paths) == 1 else f'{len(self.paths)} files';chip = theme.label(names, 'chip');chip.setTextFormat(Qt.PlainText);chip.setToolTip(chr(10).join(self.paths));head.addWidget(chip, 0, Qt.AlignTop)
        body = QHBoxLayout();body.setSpacing(14);root.addLayout(body, 1)
        left_card, left = theme.card();body.addWidget(left_card, 3);right_card, right = theme.card();right_card.setMinimumWidth(280);right_card.setVisible(bool(tool.fields));body.addWidget(right_card, 2)
        self.build_left(left)
        if tool.fields: right.addWidget(theme.label('OPTIONS', 'heading'))
        self.form = OptionsForm(tool.fields)
        if len(tool.fields) > 8:
            scroll = QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.NoFrame);scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff);scroll.setWidget(self.form);right.addWidget(scroll, 1)
            reset = QPushButton('Reset all');reset.setToolTip('Put every control back to its starting value');reset.clicked.connect(self.form.reset);right.addWidget(reset)
        else: right.addWidget(self.form)
        self.info = theme.label('', 'muted', True);right.addWidget(self.info);right.addStretch(1)
        self.form.changed.connect(self.schedule_preview)
        self.timer = QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(110);self.timer.timeout.connect(self.update_preview)
        self.banner = QWidget();bl = QHBoxLayout(self.banner);bl.setContentsMargins(0, 0, 0, 0)
        self.banner_text = theme.label('', 'banner', True);bl.addWidget(self.banner_text, 1);fix = QPushButton('Open Settings…');fix.clicked.connect(self.open_settings);bl.addWidget(fix);root.addWidget(self.banner)
        self.status = QLabel('');self.status.setWordWrap(True);self.status.setTextFormat(Qt.PlainText);root.addWidget(self.status)
        self.progress = QProgressBar();self.progress.setRange(0, 0);self.progress.setVisible(False);root.addWidget(self.progress)
        row = QHBoxLayout();root.addLayout(row)
        self.close_btn = QPushButton('Close');self.close_btn.clicked.connect(self.close);row.addWidget(self.close_btn)
        row.addStretch(1)
        self.open_btn = QPushButton('Show result');self.open_btn.setToolTip('Open the folder with the saved file');self.open_btn.setVisible(False);self.open_btn.clicked.connect(self.open_folder);row.addWidget(self.open_btn)
        self.run_btn = QPushButton('Apply');self.run_btn.setProperty('primary', True);self.run_btn.setDefault(True);self.run_btn.clicked.connect(self.run);row.addWidget(self.run_btn)
        self.refresh_requirements();self.update_preview()
        if tool.ui in ('trim', 'bleep', 'redact_video'): self.probe_media()
    # --- left panel -----------------------------------------------------------------
    def build_left(self, left):
        ui = self.tool.ui;first = self.paths[0]
        if ui in ('preview', 'crop', 'redact'):
            try: self.source = load_preview(first)
            except Exception as e: self.source = None;note = QLabel('Preview unavailable: ' + str(e));note.setWordWrap(True);left.addWidget(note)
        if ui in ('crop', 'redact') and self.source is not None:
            left.addWidget(theme.label('Drag on the picture to select the area to keep.' if ui == 'crop' else 'Drag on the picture to add areas to hide. Each box is numbered.', 'muted', True));self.canvas = RegionCanvas(pil_to_pixmap(self.source), single=ui == 'crop');left.addWidget(self.canvas, 1);self.canvas.changed.connect(self.schedule_preview)
            bar = QHBoxLayout();left.addLayout(bar)
            if ui == 'crop':
                bar.addWidget(QLabel('Shape'));shape = QComboBox()
                for label, ratio in (('Free', None), ('Square 1:1', 1.0), ('4:3', 4 / 3), ('16:9', 16 / 9), ('9:16', 9 / 16)): shape.addItem(label, ratio)
                shape.currentIndexChanged.connect(lambda: setattr(self.canvas, 'ratio', shape.currentData()));bar.addWidget(shape)
            undo = QPushButton('Undo');undo.clicked.connect(self.canvas.undo);bar.addWidget(undo);clear = QPushButton('Clear');clear.clicked.connect(self.canvas.clear);bar.addWidget(clear);bar.addStretch(1)
        elif ui == 'preview' and self.source is not None:
            self.preview_label = QLabel();self.preview_label.setAlignment(Qt.AlignCenter);self.preview_label.setMinimumSize(360, 300);self.preview_label.setStyleSheet('background:#101010;border:1px solid #2a2a2a;border-radius:8px;');left.addWidget(self.preview_label, 1)
        elif ui == 'order':
            left.addWidget(theme.label('Order of the files. Drag to rearrange.', 'muted'));self.order_list = QListWidget();self.order_list.setDragDropMode(QAbstractItemView.InternalMove);self.order_list.setDefaultDropAction(Qt.MoveAction);left.addWidget(self.order_list, 1)
            for p in self.paths: item = QListWidgetItem(Path(p).name);item.setData(Qt.UserRole, p);item.setToolTip(p);self.order_list.addItem(item)
            bar = QHBoxLayout();left.addLayout(bar);up = QPushButton('Move up');up.clicked.connect(lambda: self.move_row(-1));bar.addWidget(up);down = QPushButton('Move down');down.clicked.connect(lambda: self.move_row(1));bar.addWidget(down);bar.addStretch(1)
        elif ui in ('bleep', 'redact_video'):
            import mediaui;self.media_panel = mediaui.make(ui, left, self)
        elif ui == 'pages': self.build_pages(left)
        else:
            files = QListWidget()
            for p in self.paths: files.addItem(Path(p).name)
            left.addWidget(files, 1)
    def move_row(self, delta):
        lst = self.order_list;row = lst.currentRow();new = row + delta
        if row < 0 or not 0 <= new < lst.count(): return
        item = lst.takeItem(row);lst.insertItem(new, item);lst.setCurrentRow(new)
    def build_pages(self, left):
        left.addWidget(theme.label('Drag pages to reorder, or use the buttons. Select pages to rotate or remove them.', 'muted', True))
        lst = self.page_list = QListWidget();lst.setFlow(QListWidget.LeftToRight);lst.setWrapping(True);lst.setIconSize(QSize(self.THUMB_W, self.THUMB_H));lst.setGridSize(QSize(self.THUMB_W + 20, self.THUMB_H + 20));lst.setResizeMode(QListWidget.Adjust)
        lst.setSpacing(4);lst.setDragDropMode(QAbstractItemView.InternalMove);lst.setDefaultDropAction(Qt.MoveAction);lst.setSelectionMode(QAbstractItemView.ExtendedSelection);lst.setMovement(QListWidget.Snap);left.addWidget(lst, 1)
        self.thumb_base = {};count = 0
        try: count = len(engine.read_pdf(Path(self.paths[0])).pages)
        except Exception as e: left.addWidget(QLabel('Cannot read this PDF: ' + str(e)))
        for i in range(count):
            item = QListWidgetItem();item.setData(Qt.UserRole, {'page': i, 'rotate': 0});item.setToolTip(f'Page {i + 1}');lst.addItem(item);self.refresh_page_icon(item)
        bar = QHBoxLayout();left.addLayout(bar)
        for label, slot in (('◀ Earlier', lambda: self.move_pages(-1)), ('Later ▶', lambda: self.move_pages(1)), ('Rotate 90°', self.rotate_pages), ('Remove', self.remove_pages)): b = QPushButton(label);b.clicked.connect(slot);bar.addWidget(b)
        bar.addStretch(1);self.thumbs = iter(range(count));self.pdf_doc = None
        try:
            import pypdfium2 as pdfium
            self.pdf_doc = pdfium.PdfDocument(self.paths[0]);QTimer.singleShot(0, self.next_thumb)
        except Exception: self.pdf_doc = None
    THUMB_W, THUMB_H = 108, 144
    def refresh_page_icon(self, item):
        """Thumbnail (or a blank sheet until it has rendered), turned by the pending rotation, with its page number."""
        d = item.data(Qt.UserRole);base = self.thumb_base.get(d['page']);canvas = QPixmap(self.THUMB_W, self.THUMB_H);canvas.fill(Qt.transparent);p = QPainter(canvas);p.setRenderHint(QPainter.SmoothPixmapTransform)
        sheet = base if base is not None else QPixmap(72, 96)
        if base is None: sheet.fill(QColor('#e8e8e8'))
        if d['rotate']: sheet = sheet.transformed(QTransform().rotate(d['rotate']), Qt.SmoothTransformation)
        sheet = sheet.scaled(self.THUMB_W - 8, self.THUMB_H - 8, Qt.KeepAspectRatio, Qt.SmoothTransformation);x = (self.THUMB_W - sheet.width()) // 2;y = (self.THUMB_H - sheet.height()) // 2
        p.drawPixmap(x, y, sheet);p.setPen(QPen(QColor('#444'), 1));p.setBrush(Qt.NoBrush);p.drawRect(x, y, sheet.width() - 1, sheet.height() - 1)
        p.setPen(Qt.NoPen);p.setBrush(ORANGE);p.drawRoundedRect(QRectF(x + 3, y + sheet.height() - 20, 24 if d['page'] < 99 else 30, 17), 8, 8);p.setPen(QColor('#101010'));p.drawText(QRectF(x + 3, y + sheet.height() - 20, 24 if d['page'] < 99 else 30, 17), Qt.AlignCenter, str(d['page'] + 1));p.end()
        item.setIcon(QIcon(canvas));item.setToolTip(f"Page {d['page'] + 1}" + (f" · turned {d['rotate']}°" if d['rotate'] else ''))
    def next_thumb(self):
        i = next(self.thumbs, None)
        if i is None or self.pdf_doc is None: return
        try:
            page = self.pdf_doc[i];w, h = page.get_size();im = page.render(scale=min(self.THUMB_W * 2 / max(w, 1), self.THUMB_H * 2 / max(h, 1))).to_pil();page.close();self.thumb_base[i] = pil_to_pixmap(im)
            for row in range(self.page_list.count()):
                item = self.page_list.item(row)
                if item.data(Qt.UserRole)['page'] == i: self.refresh_page_icon(item)
        except Exception: pass
        QTimer.singleShot(0, self.next_thumb)
    def rotate_pages(self):
        for item in self.page_list.selectedItems(): d = dict(item.data(Qt.UserRole));d['rotate'] = (d['rotate'] + 90) % 360;item.setData(Qt.UserRole, d);self.refresh_page_icon(item)
    def remove_pages(self):
        for item in self.page_list.selectedItems(): self.page_list.takeItem(self.page_list.row(item))
    def move_pages(self, delta):
        """Shift the selected pages one place; the rest keep their order."""
        lst = self.page_list;rows = sorted(lst.row(i) for i in lst.selectedItems())
        if not rows or (delta < 0 and rows[0] == 0) or (delta > 0 and rows[-1] == lst.count() - 1): return
        for row in (rows if delta < 0 else reversed(rows)): lst.insertItem(row + delta, lst.takeItem(row))
        for row in rows: lst.item(row + delta).setSelected(True)
    def media_ready(self, exe, info):
        panel = getattr(self, 'media_panel', None)
        if panel is not None: panel.set_media(exe, self.paths[0], info)
    def probe_media(self):
        exe = self.ffmpeg_path()
        if not exe: return
        try: info = toolops.probe_file(exe, self.paths[0], time.monotonic() + 15);self.media_ready(exe, info);self.info.setText(f'Length: {seconds_text(info["duration"])}' + (f'  ·  {info["size"][0]}×{info["size"][1]}' if info['size'] else ''))
        except Exception: pass
    # --- preview --------------------------------------------------------------------
    def schedule_preview(self): self.timer.start()
    def update_preview(self):
        t = self.tool
        if t.id == 'resize_image' and self.source is not None:
            try: im = engine.open_image(Path(self.paths[0]));size = toolops.resize_target(im.size, self.form.values());im.close();self.info.setText(f'{len(self.paths)} file(s). The first becomes {size[0]}×{size[1]} px.')
            except Exception as e: self.info.setText(str(e))
        if self.preview_label is not None and t.id in toolops.PIXEL_OPS and t.id != 'resize_image':
            try: im = toolops.PIXEL_OPS[t.id](self.source.copy(), self.form.values());self.show_preview(im)
            except Exception as e: self.info.setText(str(e))
        elif self.preview_label is not None: self.show_preview(self.source)
    def show_preview(self, im):
        pm = pil_to_pixmap(im);box = self.preview_label.size() - QSize(16, 16);self.preview_label.setPixmap(pm.scaled(box, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.preview_label is not None: self.schedule_preview()
    # --- running --------------------------------------------------------------------
    def ffmpeg_path(self): return self.settings.value('ffmpeg', '') or str(engine.find_tool('ffmpeg') or '')
    def refresh_requirements(self):
        need = toolops.needs_ffmpeg(self.tool, self.paths);missing = need and not self.ffmpeg_path();self.banner.setVisible(bool(missing));self.run_btn.setEnabled(not missing)
        if missing: self.banner_text.setText('This tool needs FFmpeg, which was not found on this computer. Install it' + (' (winget install Gyan.FFmpeg)' if os.name == 'nt' else '') + ' and it is picked up automatically, or choose it in Settings.')
    def open_settings(self):
        settings_dialog.SettingsDialog(self.settings, self, tab='formats').exec();self.refresh_requirements();self.probe_media()
    def collect(self):
        """(parameters, ordered paths) for the request. Raises ValueError with a message the user can act on."""
        params = self.form.values();paths = list(self.paths);ui = self.tool.ui
        if ui == 'crop':
            if not self.canvas or not self.canvas.rects: raise ValueError('Drag on the picture to select the area to keep.')
            params['rect'] = [list(self.canvas.rects[0])]
        elif ui == 'redact':
            if not self.canvas or not self.canvas.rects: raise ValueError('Drag on the picture to select at least one area to hide.')
            params['rects'] = [list(r) for r in self.canvas.rects]
        elif ui in ('bleep', 'redact_video'): params.update(self.media_panel.collect())
        elif ui == 'order': paths = [self.order_list.item(i).data(Qt.UserRole) for i in range(self.order_list.count())]
        elif ui == 'pages':
            params['pages'] = [dict(self.page_list.item(i).data(Qt.UserRole)) for i in range(self.page_list.count())]
            if not params['pages']: raise ValueError('Keep at least one page.')
        return params, paths
    def run(self):
        try: params, paths = self.collect()
        except ValueError as e: theme.set_status(self.status, str(e), 'warn');return
        self.outputs = [];self.open_btn.setVisible(False);self.run_btn.setEnabled(False);self.progress.setVisible(True);theme.set_status(self.status, self.tool.progress + '…')
        self.batch = Batch(paths, 'tool:' + self.tool.id, {'output': prefs.output_folder(self.settings), 'params': params, 'ffmpeg': self.ffmpeg_path()});self.results = []
        self.batch.result.connect(lambda i, status, outs: (self.results.append(status), self.outputs.extend(outs)));self.batch.finished.connect(self.batch_finished);self.batch.start()
    def batch_finished(self):
        self.progress.setVisible(False);self.run_btn.setEnabled(True);failed = [s for s in self.results if s != 'Done']
        if self.outputs and not failed: theme.set_status(self.status, '✓ Done. Saved ' + (Path(self.outputs[0]).name if len(self.outputs) == 1 else f'{len(self.outputs)} files') + (' to ' + Path(self.outputs[0]).parent.name if prefs.output_folder(self.settings) else ' next to the original') + '.', 'ok')
        elif self.outputs: theme.set_status(self.status, f'{len(self.outputs)} saved, {len(failed)} failed: {failed[0]}', 'warn')
        else: theme.set_status(self.status, failed[0] if failed else 'Nothing was produced.', 'error')
        self.open_btn.setVisible(bool(self.outputs))
        if self.outputs and prefs.reveal_results(self.settings): self.open_folder()
    def open_folder(self):
        if self.outputs: QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.outputs[0]).parent)))
    def closeEvent(self, e):
        if self.batch and self.batch.isRunning(): self.batch.cancel.set();self.batch.wait(5000)
        if getattr(self, 'pdf_doc', None) is not None:
            try: self.pdf_doc.close()
            except Exception: pass
            self.pdf_doc = None
        super().closeEvent(e)
