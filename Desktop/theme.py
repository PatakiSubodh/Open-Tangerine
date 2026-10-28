"""One look for every window: the main window, the tool windows, the colour picker and the info dialogs."""
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

ORANGE = '#ff610a'
STYLE = '''
QWidget{background:#171717;color:#f5f3ed;font-size:13px}
QDialog,QMainWindow{background:#171717}
QPushButton,QComboBox,QSpinBox,QDoubleSpinBox,QLineEdit{padding:7px 10px;border:1px solid #5a5a5a;border-radius:6px;background:#1e1e1e}
QPushButton:hover,QComboBox:hover,QSpinBox:hover,QDoubleSpinBox:hover,QLineEdit:hover{border-color:#ff762b}
QPushButton:focus,QComboBox:focus,QSpinBox:focus,QDoubleSpinBox:focus,QLineEdit:focus{border-color:#ff762b}
QPushButton:disabled,QComboBox:disabled,QSpinBox:disabled,QLineEdit:disabled{color:#777;border-color:#3a3a3a}
QPushButton[primary="true"]{background:#ff610a;color:#101010;font-weight:bold;border:none;padding:11px 22px;font-size:14px}
QPushButton[primary="true"]:hover{background:#ff7a2e}
QPushButton[primary="true"]:disabled{background:#4a2c18;color:#8a7a70}
QPushButton[link="true"]{border:none;color:#b8b8b8;padding:4px 8px;background:transparent}
QPushButton[link="true"]:hover{color:#ff9a5c;text-decoration:underline}
QComboBox QAbstractItemView{background:#1e1e1e;border:1px solid #5a5a5a;selection-background-color:#4a2c18;selection-color:#fff;outline:0}
QListWidget{background:#202020;border:1px solid #3a3a3a;border-radius:10px;padding:8px;outline:0}
QListWidget::item{padding:5px 4px;border-radius:5px}
QListWidget::item:selected{background:#4a2c18;color:#fff}
QListWidget#drop{border:2px dashed #666}
QListWidget#drop[dragging="true"]{border:2px solid #ff610a;background:#2a201a}
QProgressBar{border:none;border-radius:4px;background:#2c2c2c;text-align:center;max-height:8px}
QProgressBar::chunk{background:#ff610a;border-radius:4px}
QCheckBox{spacing:8px;background:transparent}
QCheckBox::indicator{width:16px;height:16px;border:1px solid #6a6a6a;border-radius:4px;background:#1e1e1e}
QCheckBox::indicator:checked{background:#ff610a;border-color:#ff610a}
QSlider{background:transparent}
QSlider::groove:horizontal{height:4px;background:#3a3a3a;border-radius:2px}
QSlider::sub-page:horizontal{background:#ff610a;border-radius:2px}
QSlider::handle:horizontal{width:14px;height:14px;margin:-6px 0;border-radius:7px;background:#f5f3ed}
QScrollBar:vertical{background:transparent;width:10px;margin:0}
QScrollBar::handle:vertical{background:#4a4a4a;border-radius:5px;min-height:30px}
QScrollBar::add-line,QScrollBar::sub-line{height:0}
QLabel{background:transparent}
QLabel#muted{color:#a8a8a8}
QLabel#step{color:#ff9a5c;font-weight:bold}
QLabel#title{font-size:22px;font-weight:bold;color:#ff762b}
QLabel#heading{color:#ff9a5c;font-weight:bold;font-size:12px}
QLabel#banner{background:#33260f;border:1px solid #b36a1c;border-radius:6px;padding:10px;color:#ffd9a8}
QLabel#chip{background:#262626;border:1px solid #3a3a3a;border-radius:10px;padding:2px 10px;color:#cfcfcf}
QFrame#card{background:#1c1c1c;border:1px solid #333;border-radius:10px}
QFrame#card QLabel,QFrame#card QCheckBox{background:transparent}
QToolTip{background:#2b2b2b;color:#f5f3ed;border:1px solid #666}
'''

def card(layout_cls=QVBoxLayout, margins=(14, 12, 14, 12), spacing=8):
    """A bordered panel. Returns (frame, layout)."""
    frame = QFrame();frame.setObjectName('card');box = layout_cls(frame);box.setContentsMargins(*margins);box.setSpacing(spacing);return frame, box

def label(text, name='', wrap=False):
    w = QLabel(text);w.setWordWrap(wrap)
    if name: w.setObjectName(name)
    return w

def set_status(widget, text, kind=''):
    """Status line colours: ok (green), warn (amber), error (red); anything else is plain."""
    widget.setText(text);widget.setStyleSheet({'ok': 'color:#7bd88f', 'warn': 'color:#ffb454', 'error': 'color:#ff7b7b'}.get(kind, ''))

def spin_css():
    """Spin-box arrows. Qt draws none once a box is restyled, so paint two small triangles to a temp folder and point the stylesheet at them."""
    import tempfile
    from pathlib import Path
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QPainter, QPixmap, QPolygonF
    from PySide6.QtCore import QPointF
    folder = Path(tempfile.gettempdir()) / 'open-tangerine-ui';folder.mkdir(exist_ok=True);paths = {}
    for name, pts in (('up', [(1, 6), (5, 1), (9, 6)]), ('down', [(1, 1), (5, 6), (9, 1)])):
        pm = QPixmap(10, 7);pm.fill(Qt.transparent);p = QPainter(pm);p.setRenderHint(QPainter.Antialiasing);p.setBrush(QColor('#cfcfcf'));p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in pts]));p.end();target = folder / f'{name}.png';pm.save(str(target));paths[name] = target.as_posix()
    both = 'QSpinBox{{}}::{0},QDoubleSpinBox::{0}'
    return (f'QSpinBox,QDoubleSpinBox{{padding-right:24px}}'
            f'QSpinBox::up-button,QDoubleSpinBox::up-button{{subcontrol-origin:border;subcontrol-position:top right;width:22px;border:none;border-left:1px solid #444;background:transparent}}'
            f'QSpinBox::down-button,QDoubleSpinBox::down-button{{subcontrol-origin:border;subcontrol-position:bottom right;width:22px;border:none;border-left:1px solid #444;background:transparent}}'
            f'QSpinBox::up-arrow,QDoubleSpinBox::up-arrow{{image:url({paths["up"]});width:10px;height:7px}}'
            f'QSpinBox::down-arrow,QDoubleSpinBox::down-arrow{{image:url({paths["down"]});width:10px;height:7px}}')

def apply(app):
    """Install the shared stylesheet on the application."""
    try: extra = spin_css()
    except Exception: extra = ''
    app.setStyleSheet(STYLE + extra)
