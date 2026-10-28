"""Small themed dialogs: the colour picker and the scrollable information sheet."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog, QDialog, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget
import theme

SWATCHES = ('#ffffff', '#000000', '#ff610a', '#ffb454', '#ffd400', '#7bd88f', '#00a86b', '#2dd4ff', '#2f6bff', '#8a5cff', '#ff4fa3', '#ff4d4d', '#9a9a9a', '#4a4a4a', '#f5e6c8', '#101010')

class ColorDialog(QDialog):
    """Preset swatches on top, a full picker (hue, saturation, hex, RGB) below; OK and Cancel are ours so the whole dialog matches the app."""
    def __init__(self, current, parent=None, title='Choose a colour'):
        super().__init__(parent);self.setWindowTitle(title);self.setModal(True)
        root = QVBoxLayout(self);root.setContentsMargins(20, 16, 20, 16);root.setSpacing(12)
        root.addWidget(theme.label(title, 'title'))
        root.addWidget(theme.label('Pick a preset, or fine-tune below.', 'muted'))
        grid = QGridLayout();grid.setSpacing(8);root.addLayout(grid)
        for i, c in enumerate(SWATCHES):
            b = QPushButton();b.setFixedSize(34, 34);b.setToolTip(c);b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(f'QPushButton{{background:{c};border:2px solid #555;border-radius:17px;padding:0}}QPushButton:hover{{border-color:#ff762b}}')
            b.clicked.connect(lambda _=False, col=c: self.picker.setCurrentColor(QColor(col)));grid.addWidget(b, i // 8, i % 8)
        self.picker = QColorDialog(QColor(current), self)
        self.picker.setWindowFlags(Qt.Widget);self.picker.setOptions(QColorDialog.NoButtons | QColorDialog.DontUseNativeDialog);root.addWidget(self.picker)
        row = QHBoxLayout();row.addStretch(1);root.addLayout(row)
        cancel = QPushButton('Cancel');cancel.clicked.connect(self.reject);row.addWidget(cancel)
        ok = QPushButton('Use this colour');ok.setProperty('primary', True);ok.setDefault(True);ok.clicked.connect(self.accept);row.addWidget(ok)
    def colour(self): return self.picker.currentColor()

def pick_colour(current, parent=None, title='Choose a colour'):
    """Returns the chosen QColor, or None if the dialog was cancelled."""
    d = ColorDialog(current, parent, title)
    return d.colour() if d.exec() == QDialog.Accepted else None

class InfoDialog(QDialog):
    """A titled sheet of sections (heading + paragraph), scrollable, with one Close button."""
    def __init__(self, title, intro, sections, parent=None):
        super().__init__(parent);self.setWindowTitle(title);self.resize(640, 620)
        root = QVBoxLayout(self);root.setContentsMargins(22, 18, 22, 16);root.setSpacing(10)
        root.addWidget(theme.label(title, 'title'));root.addWidget(theme.label(intro, 'muted', True))
        area = QScrollArea();area.setWidgetResizable(True);area.setFrameShape(QScrollArea.NoFrame);root.addWidget(area, 1)
        body = QWidget();inner = QVBoxLayout(body);inner.setContentsMargins(0, 0, 8, 0);inner.setSpacing(10);area.setWidget(body)
        for heading, text in sections:
            frame, box = theme.card();box.addWidget(theme.label(heading.upper(), 'heading'));box.addWidget(theme.label(text, '', True));inner.addWidget(frame)
        inner.addStretch(1)
        row = QHBoxLayout();row.addStretch(1);root.addLayout(row)
        close = QPushButton('Close');close.setProperty('primary', True);close.clicked.connect(self.accept);row.addWidget(close)
