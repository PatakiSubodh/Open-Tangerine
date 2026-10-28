"""Left-hand panels of the time-based tools: Bleep audio (a list of time ranges) and Redact video (boxes drawn on a
video frame, each with its own time range). The tool window (toolwin.py) builds one with make() and reads it with collect()."""
import tempfile
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QDoubleSpinBox, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSlider, QVBoxLayout, QWidget
import theme, toolops

MAX_SECONDS = 86400

def seconds_text(value): return f'{int(value // 60)}:{value % 60:04.1f}'

def spin(value, maximum=MAX_SECONDS):
    w = QDoubleSpinBox();w.setRange(0, maximum);w.setDecimals(2);w.setSingleStep(.5);w.setSuffix(' s');w.setValue(value);w.setMinimumWidth(96);return w

class RangeRow(QWidget):
    def __init__(self, title, start, end, on_remove, on_change, removable=True):
        super().__init__();row = QHBoxLayout(self);row.setContentsMargins(0, 0, 0, 0)
        self.title = QLabel(title);self.title.setMinimumWidth(56);row.addWidget(self.title);row.addWidget(QLabel('from'))
        self.start = spin(start);row.addWidget(self.start);row.addWidget(QLabel('to'));self.end = spin(end);row.addWidget(self.end);row.addStretch(1)
        self.remove = QPushButton('Remove');self.remove.setVisible(removable);self.remove.clicked.connect(lambda: on_remove(self));row.addWidget(self.remove)
        self.start.valueChanged.connect(on_change);self.end.valueChanged.connect(on_change)

class RangeList(QWidget):
    """Rows of start/end times. `open_end` means an end of 0 stands for "until the end of the file"."""
    changed = Signal()
    def __init__(self, noun='Range', open_end=False):
        super().__init__();self.noun = noun;self.open_end = open_end;self.rows = [];self.maximum = MAX_SECONDS;self.column = QVBoxLayout(self);self.column.setContentsMargins(0, 0, 0, 0);self.column.setSpacing(6)
    def add(self, start=0.0, end=0.0):
        row = RangeRow(f'{self.noun} {len(self.rows) + 1}', start, end, self.remove, lambda *_: self.changed.emit());row.start.setMaximum(self.maximum);row.end.setMaximum(self.maximum)
        self.rows.append(row);self.column.addWidget(row);self.changed.emit();return row
    def remove(self, row):
        if row in self.rows: self.rows.remove(row);row.setParent(None);row.deleteLater()
        for i, r in enumerate(self.rows): r.title.setText(f'{self.noun} {i + 1}')
        self.changed.emit()
    def resize_to(self, count):
        while len(self.rows) > count: self.remove(self.rows[-1])
        while len(self.rows) < count: self.add()
    def set_maximum(self, seconds):
        self.maximum = max(1.0, seconds)
        for r in self.rows: r.start.setMaximum(self.maximum);r.end.setMaximum(self.maximum)
    def values(self): return [[r.start.value(), r.end.value()] for r in self.rows]

def scrolling(widget, height):
    """Put a growing list in a scroll area so many rows never squeeze the rest of the panel."""
    area = QScrollArea();area.setWidgetResizable(True);area.setFrameShape(QFrame.NoFrame);area.setWidget(widget);area.setMaximumHeight(height);area.setMinimumHeight(min(height, 64));return area

class BleepPanel(QWidget):
    def __init__(self, left):
        super().__init__();col = QVBoxLayout(self);col.setContentsMargins(0, 0, 0, 0);col.setSpacing(10)
        col.addWidget(theme.label('Add each part of the audio to cover, in seconds. Play the file in any player to find the times.', 'muted', True))
        self.ranges = RangeList('Part');col.addWidget(scrolling(self.ranges, 320));self.ranges.add(0.0, 1.0)
        add = QPushButton('Add another part');add.clicked.connect(lambda: self.ranges.add(0.0, 1.0));bar = QHBoxLayout();bar.addWidget(add);bar.addStretch(1);col.addLayout(bar);col.addStretch(1);left.addWidget(self, 1)
    def set_media(self, exe, path, info):
        if info['duration']: self.ranges.set_maximum(info['duration'])
    def collect(self):
        values = self.ranges.values()
        if not values: raise ValueError('Add at least one part to cover.')
        for i, (a, b) in enumerate(values, 1):
            if b <= a: raise ValueError(f'Part {i} must end after it starts.')
        return {'ranges': values}

def grab_frame(exe, path, seconds):
    """One upright, downscaled frame as a pixmap, or None when FFmpeg cannot produce it."""
    from toolwin import pil_to_pixmap
    from PIL import Image
    with tempfile.TemporaryDirectory(prefix='.opentangerine-') as d:
        out = Path(d) / 'frame.png'
        try: toolops.grab_frame(exe, path, seconds, out)
        except Exception: return None
        try:
            with Image.open(out) as im: return pil_to_pixmap(im.convert('RGB'))
        except Exception: return None

class RedactVideoPanel(QWidget):
    def __init__(self, left, window):
        super().__init__();from toolwin import RegionCanvas
        self.exe = None;self.path = window.paths[0];self.duration = 0.0;self.col = QVBoxLayout(self);self.col.setContentsMargins(0, 0, 0, 0);self.col.setSpacing(8)
        self.col.addWidget(theme.label('Drag on the frame to add areas to hide. Each area is hidden for the time range you set below it.', 'muted', True))
        blank = QPixmap(640, 360);blank.fill(QColor('#101010'));self.canvas = RegionCanvas(blank, False);self.canvas.setMinimumSize(320, 180);self.col.addWidget(self.canvas, 1)
        bar = QHBoxLayout();self.col.addLayout(bar);bar.addWidget(QLabel('Frame'));self.slider = QSlider(Qt.Horizontal);self.slider.setRange(0, 1000);bar.addWidget(self.slider, 1);self.when = QLabel('0:00.0');self.when.setMinimumWidth(52);bar.addWidget(self.when)
        undo = QPushButton('Undo');undo.clicked.connect(self.canvas.undo);bar.addWidget(undo);clear = QPushButton('Clear');clear.clicked.connect(self.canvas.clear);bar.addWidget(clear)
        self.note = theme.label('', 'muted', True);self.col.addWidget(self.note)
        self.areas = RangeList('Area', open_end=True);self.col.addWidget(scrolling(self.areas, 120));self.hint = theme.label('Leave "to" at 0 to hide an area until the end of the video.', 'muted', True);self.col.addWidget(self.hint);self.hint.setVisible(False)
        self.timer = QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(180);self.timer.timeout.connect(self.load_frame)
        self.slider.valueChanged.connect(self.moved);self.canvas.changed.connect(self.sync);left.addWidget(self, 1)
    def seconds(self): return self.duration * self.slider.value() / 1000
    def moved(self): self.when.setText(seconds_text(self.seconds()));self.timer.start()
    def set_media(self, exe, path, info):
        self.exe = exe;self.duration = info['duration'];self.areas.set_maximum(self.duration or MAX_SECONDS);self.slider.setEnabled(bool(self.duration));self.load_frame()
    def load_frame(self):
        if not self.exe: self.note.setText('FFmpeg is needed to show a frame of the video.');return
        pm = grab_frame(self.exe, self.path, self.seconds())
        if pm is None: self.note.setText('Could not read a picture from this video.');return
        self.note.setText('');self.canvas.pixmap = pm;self.canvas.update()
    def sync(self):
        self.areas.resize_to(len(self.canvas.rects));self.hint.setVisible(bool(self.canvas.rects))
    def collect(self):
        if not self.canvas.rects: raise ValueError('Drag on the frame to select at least one area to hide.')
        times = self.areas.values()
        for i, (a, b) in enumerate(times, 1):
            if b and b <= a: raise ValueError(f'Area {i} must end after it starts (or leave "to" at 0).')
        return {'boxes': [[*r, a, b] for r, (a, b) in zip(self.canvas.rects, times)]}

def make(ui, left, window):
    return BleepPanel(left) if ui == 'bleep' else RedactVideoPanel(left, window)
