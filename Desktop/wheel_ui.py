"""Widgets of the wheel: the radial overlay with its Convert / Tools / Actions tabs, and the notification card.
The overlay has two looks, chosen in Settings: Light, the frosted glass of the in-window wheel (glass_design.py, from PR #2),
and Dark, the main window's charcoal and Tangerine orange. The progress card follows the same setting."""
import math
from pathlib import Path
from PySide6.QtCore import Qt, QEvent, QPoint, QPointF, QRectF, QTimer, QUrl, QPropertyAnimation, QEasingCurve, QElapsedTimer, Signal
from PySide6.QtGui import QColor, QCursor, QDesktopServices, QFont, QFontMetricsF, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPainterPathStroker, QPen, QPixmap, QRadialGradient, QTextLayout, QTextOption
from PySide6.QtWidgets import QWidget
from wheelmodel import SLOTS, MODES, MODE_TITLES, MODE_KEYS, EMPTY, PROMPT, items_for, default_items, combine_target

def system_dark():
    """True when the OS app theme is dark (Qt's colour scheme, falling back to the Windows registry); dark when unknown."""
    try:
        scheme = QGuiApplication.styleHints().colorScheme()
        if scheme == Qt.ColorScheme.Dark: return True
        if scheme == Qt.ColorScheme.Light: return False
    except (AttributeError, RuntimeError): pass
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as key: return winreg.QueryValueEx(key, 'AppsUseLightTheme')[0] == 0
    except (ImportError, OSError): return True

class Theme:
    """Dark: the main window's palette (charcoal surfaces, Tangerine orange). Light: pale grey bezel and white tiles.
    `Theme()` follows the system setting; `refresh()` re-reads it each time a widget is shown."""
    accent = QColor('#ff610a')
    def __init__(self, dark=None): self.apply(system_dark() if dark is None else dark)
    def refresh(self): self.apply(system_dark())
    def apply(self, dark):
        self.dark = dark
        if dark:
            self.accent_text = QColor('#ff762b');self.ink = QColor('#101010');self.on_accent = QColor('#101010')
            self.surface = QColor(23, 23, 23, 246);self.raised = QColor(34, 34, 34);self.edge = QColor('#444444');self.tile = QColor(34, 34, 34);self.tile_edge = QColor('#454545')
            self.tile_hi = QColor(42, 42, 42);self.tile_lo = QColor(30, 30, 30);self.bezel = QColor(23, 23, 23, 246);self.hub = QColor(17, 17, 17);self.pill = QColor(34, 34, 34)
            self.text = QColor('#f5f3ed');self.muted = QColor(245, 243, 237, 150);self.track = QColor('#3a3a3a');self.ok = QColor('#4cd964');self.error = QColor('#ff5a52');self.shadow_alpha = 120
        else:
            self.accent_text = QColor('#e0520a');self.ink = QColor('#111111');self.on_accent = QColor('#ffffff')
            self.surface = QColor(250, 250, 250, 248);self.raised = QColor('#ffffff');self.edge = QColor('#d9dcdc');self.tile = QColor('#f1f2f2');self.tile_edge = QColor('#cfd3d3')
            self.tile_hi = QColor('#f8f9f9');self.tile_lo = QColor('#eaeced');self.bezel = QColor('#e9ebeb');self.hub = QColor('#f7f8f8');self.pill = QColor('#ffffff')
            self.text = QColor('#111111');self.muted = QColor(17, 17, 17, 140);self.track = QColor('#d9dcdc');self.ok = QColor('#2fb24c');self.error = QColor('#e5483f');self.shadow_alpha = 60

_logo = []
def app_logo():
    if not _logo:
        pm = QPixmap(str(Path(__file__).with_name('icon.png')));_logo.append(None if pm.isNull() else pm)
    return _logo[0]

def ui_font(size, weight=QFont.Normal):
    f = QFont();f.setFamilies(['Segoe UI Variable Text', 'Segoe UI', 'Arial']);f.setPointSizeF(size);f.setWeight(weight);f.setStyleStrategy(QFont.PreferAntialias);return f

def fit_font(text, width, size, weight):
    f = ui_font(size, weight)
    while size > 6.5 and QFontMetricsF(f).horizontalAdvance(text) > width: size -= .5;f = ui_font(size, weight)
    return f

# Line icons on a 24x24 grid: ('l', points) polyline, ('r', x, y, w, h) rounded rect, ('c', cx, cy, r) circle.
_DOC = [('l', [(6, 3), (14, 3), (19, 8), (19, 21), (6, 21), (6, 3)]), ('l', [(14, 3), (14, 8), (19, 8)])]
_COPY = [('r', 8, 8, 12, 12), ('l', [(16, 8), (16, 4), (4, 4), (4, 16), (8, 16)])]
_CROP = [('l', [(7, 3), (7, 17), (21, 17)]), ('l', [(3, 7), (17, 7), (17, 21)])]
_SPLIT = [('l', [(12, 3), (12, 21)]), ('l', [(4, 8), (8, 12), (4, 16)]), ('l', [(20, 8), (16, 12), (20, 16)])]
_MERGE = [('l', [(4, 5), (12, 12), (4, 19)]), ('l', [(12, 12), (21, 12)]), ('l', [(17, 8), (21, 12), (17, 16)])]
_BARS = [('l', [(5, 10), (5, 14)]), ('l', [(9, 6), (9, 18)]), ('l', [(13, 9), (13, 15)]), ('l', [(17, 4), (17, 20)]), ('l', [(21, 10), (21, 14)])]
ICONS = {
    'edit_image': [('l', [(3, 7), (21, 7)]), ('l', [(3, 12), (21, 12)]), ('l', [(3, 17), (21, 17)]), ('c', 8, 7, 2.2), ('c', 16, 12, 2.2), ('c', 10, 17, 2.2)],
    'frame_image': [('r', 3, 4, 18, 16), ('l', [(3, 16), (9, 10), (14, 15), (17, 12), (21, 16)])],
    'crop_image': _CROP, 'crop_video': _CROP,
    'redact_image': [('r', 3, 8, 18, 8), ('l', [(4, 20), (20, 4)])],
    'resize_image': [('l', [(4, 10), (10, 10), (10, 4)]), ('l', [(20, 14), (14, 14), (14, 20)]), ('l', [(4, 4), (10, 10)]), ('l', [(20, 20), (14, 14)])],
    'compress': [('l', [(4, 4), (10, 10)]), ('l', [(10, 5), (10, 10), (5, 10)]), ('l', [(20, 20), (14, 14)]), ('l', [(14, 19), (14, 14), (19, 14)])],
    'rotate_image': [('l', [(19, 12), (19, 8), (15, 4), (9, 4), (5, 8), (5, 14), (9, 19), (15, 19)]), ('l', [(15, 15), (15, 19), (19, 19)])],
    'create_pdf': _DOC, 'organize_pdf': _DOC, 'reveal': [('l', [(3, 7), (10, 7), (12, 9), (21, 9), (21, 19), (3, 19), (3, 7)])],
    'collage': [('r', 3, 3, 8, 8), ('r', 13, 3, 8, 8), ('r', 3, 13, 8, 8), ('r', 13, 13, 8, 8)],
    'merge_pdf': _MERGE, 'join_videos': _MERGE, 'split_pdf': _SPLIT, 'split_media': _SPLIT,
    'metadata': [('l', [(3, 12), (12, 3), (21, 3), (21, 12), (12, 21), (3, 12)]), ('c', 16.5, 7.5, 1.6)],
    'trim': [('c', 7, 17, 3), ('c', 17, 17, 3), ('l', [(9, 15), (18, 4)]), ('l', [(15, 15), (6, 4)])],
    'speed_video': [('l', [(4, 6), (11, 12), (4, 18), (4, 6)]), ('l', [(13, 6), (20, 12), (13, 18), (13, 6)])],
    'video_frames': [('r', 3, 5, 18, 14), ('l', [(9, 5), (9, 19)]), ('l', [(15, 5), (15, 19)])],
    'normalize_audio': _BARS, 'audio_channels': _BARS, 'audio_visualizer': _BARS,
    'copy_files': _COPY, 'copy_paths': _DOC, 'duplicate': _COPY + [('l', [(11, 14), (17, 14)]), ('l', [(14, 11), (14, 17)])],
    'hash': [('l', [(9, 4), (7, 20)]), ('l', [(17, 4), (15, 20)]), ('l', [(4, 9), (20, 9)]), ('l', [(3, 15), (19, 15)])],
}

def draw_icon(p, key, rect, color):
    """Stroke the icon for `key` into `rect` (a plain circle for anything unknown)."""
    spec = ICONS.get(key, [('c', 12, 12, 8)]);p.save();p.translate(rect.topLeft());p.scale(rect.width() / 24, rect.height() / 24)
    p.setPen(QPen(color, 1.9, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin));p.setBrush(Qt.NoBrush)
    for op in spec:
        if op[0] == 'l': p.drawPolyline([QPointF(x, y) for x, y in op[1]])
        elif op[0] == 'r': p.drawRoundedRect(QRectF(op[1], op[2], op[3], op[4]), 2.5, 2.5)
        else: p.drawEllipse(QPointF(op[1], op[2]), op[3], op[3])
    p.restore()

# Frosted glass material shared with glass_design.py: pearly rim, light panes, Tangerine orange for the pane under the cursor.
RIM = ((0, (248, 253, 255, 170)), (.55, (161, 184, 198, 85)), (1, (245, 250, 255, 130)))
PANE = ((0, (255, 255, 255, 205)), (.5, (224, 237, 243, 178)), (1, (183, 206, 220, 200)))
PANE_HOT = ((0, (255, 179, 107, 245)), (.5, (255, 102, 25, 235)), (1, (235, 79, 12, 245)))
GLASS_INK = QColor('#213340');GLASS_MUTED = QColor(38, 61, 74, 170);GLASS_EDGE = QColor(255, 255, 255, 220)

class Look:
    """Colours of one wheel theme. Gradients are (position, rgba) stops; `sheen` adds the glass highlight and the soft drop under each pane."""
    def __init__(self, **kw): self.__dict__.update(kw)

LOOKS = {
    'light': Look(rim=RIM, rim_edge=QColor(255, 255, 255, 100), pane=PANE, pane_edge=GLASS_EDGE, hot=PANE_HOT, sheen=True,
                  ink=GLASS_INK, ink_hot=QColor('#ffffff'), muted=GLASS_MUTED, hub=(QColor(255, 255, 255, 248), QColor(217, 234, 243, 190)), hub_edge=GLASS_EDGE,
                  pill=QColor(255, 255, 255, 155), pill_edge=QColor(255, 255, 255, 200), tab=QColor(239, 248, 253, 225), tab_hover=QColor(255, 255, 255, 240),
                  tab_edge=QColor(255, 255, 255, 170), tab_hint_hot=QColor(255, 255, 255, 190), shadow=90),
    # The main window's palette (theme.py): charcoal surfaces, #444 edges, Tangerine orange with near-black text on it.
    'dark': Look(rim=((0, (27, 27, 27, 246)), (1, (20, 20, 20, 246))), rim_edge=QColor('#444444'), pane=((0, (42, 42, 42, 255)), (1, (30, 30, 30, 255))),
                 pane_edge=QColor('#454545'), hot=((0, (255, 118, 43, 255)), (1, (255, 97, 10, 255))), sheen=False,
                 ink=QColor('#f5f3ed'), ink_hot=QColor('#101010'), muted=QColor(245, 243, 237, 150), hub=(QColor(24, 24, 24), QColor(17, 17, 17)), hub_edge=QColor('#444444'),
                 pill=QColor(34, 34, 34), pill_edge=QColor('#444444'), tab=QColor(23, 23, 23, 246), tab_hover=QColor(34, 34, 34),
                 tab_edge=QColor('#444444'), tab_hint_hot=QColor(16, 16, 16, 170), shadow=120)}

def glass(a, b, stops, alpha=1.0):
    g = QLinearGradient(a, b)
    for at, (r, gr, bl, al) in stops: g.setColorAt(at, QColor(r, gr, bl, int(al * alpha)))
    return g

def ease_out_back(t):
    t = max(0.0, min(1.0, t));c = 1.45;return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2

class WheelOverlay(QWidget):
    """Radial flyout. Tiles bloom out of the hub; the tile under the cursor lifts and takes the accent colour.
    The disc is the drop target: the ring of tiles picks an item, the centre and the rim do nothing.
    Tabs below the disc switch between Convert, Tools and Actions without touching the keyboard."""
    chosen = Signal(list, str, str)       # files, kind (convert / tool / action), key
    mode_changed = Signal(str)
    # Logical pixels; Windows display scaling enlarges them (440 px is 550 px on screen at 125%).
    SIZE = 440;HEIGHT = 470;OUTER = 182;INNER = 70;TILE = 66
    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground);self.setAttribute(Qt.WA_ShowWithoutActivating);self.setMouseTracking(True)
        self.setAcceptDrops(True);self.setFixedSize(self.SIZE, self.HEIGHT);self.paths = [];self.mode = 'convert';self.items = default_items();self.hover = -1;self.hover_tab = -1;self.hover_part = None
        self.interactive = False;self.focusless = True;self.setAccessibleName('Open Tangerine drag wheel')
        self.theme = Theme();self.look = 'light';self.wedges = {};self.open = 1.0;self.lift = [0.0] * SLOTS;self.clock = QElapsedTimer();self.last = 0
        self.hide_timer = QTimer(self);self.hide_timer.setSingleShot(True);self.hide_timer.timeout.connect(self.dismiss)
        self.frames = QTimer(self);self.frames.setInterval(8);self.frames.setTimerType(Qt.PreciseTimer);self.frames.timeout.connect(self.advance)
    # --- lifecycle ------------------------------------------------------------------
    def present(self, center, mode='convert', paths=None, interactive=False):
        """Show the wheel with the ring centred on `center`. With `paths` and interactive=True it is a click-to-pick menu."""
        self.theme.refresh();self.hide_timer.stop();self.paths = list(paths or []);self.mode = mode;self.interactive = interactive;self.hover = -1;self.hover_tab = -1;self.hover_part = None;self.lift = [0.0] * SLOTS
        self.items = items_for(mode, self.paths) if self.paths else (default_items() if mode == 'convert' else [])
        want_focusless = not interactive
        if want_focusless != self.focusless: self.setWindowFlag(Qt.WindowDoesNotAcceptFocus, want_focusless);self.focusless = want_focusless
        screen = QGuiApplication.screenAt(center) or QGuiApplication.primaryScreen();area = screen.availableGeometry()
        half = self.SIZE // 2;x = min(max(center.x() - half, area.left()), area.right() - self.SIZE + 1);y = min(max(center.y() - half, area.top()), area.bottom() - self.HEIGHT + 1)
        self.open = 0.0;self.setWindowOpacity(0.0);self.move(x, y);self.show();self.raise_()
        if interactive: self.activateWindow();self.setFocus()
        self.clock.start();self.last = 0;self.frames.start();self.update()
    def dismiss(self): self.hide_timer.stop();self.frames.stop();self.hide();self.paths = [];self.hover = -1;self.interactive = False
    def dismiss_soon(self):
        # The release poll can win the race against Windows delivering the drop; keep the target alive briefly.
        if self.isVisible(): self.hide_timer.start(600)
    def set_mode(self, mode):
        if mode == self.mode or mode not in MODES: return
        self.mode = mode;self.items = items_for(mode, self.paths) if self.paths else (default_items() if mode == 'convert' else [])
        self.hover = -1;self.lift = [0.0] * SLOTS;self.open = min(self.open, .55);self.restart_clock();self.mode_changed.emit(mode);self.update()
    def restart_clock(self):
        if not self.clock.isValid(): self.clock.start()
        self.last = self.clock.elapsed();self.frames.start()
    def advance(self):
        """Time-based, so it looks identical at 60, 144 or 300 Hz."""
        now = self.clock.elapsed();dt = min((now - self.last) / 1000, .05);self.last = now;busy = False
        if self.open < 1: self.open = min(1.0, self.open + dt / .32);busy = True;self.setWindowOpacity(min(1.0, self.open * 3))
        k = 1 - math.exp(-dt * 22)
        for i in range(SLOTS):
            goal = 1.0 if i == self.hover else 0.0;delta = goal - self.lift[i]
            if abs(delta) > .004: self.lift[i] += delta * k;busy = True
            else: self.lift[i] = goal
        self.update()
        if not busy: self.frames.stop()
    # --- geometry -------------------------------------------------------------------
    def ring_radius(self): return (self.OUTER + self.INNER) / 2
    def tile_size(self, n): return min(self.TILE, 2 * self.ring_radius() * math.sin(math.pi / max(n, 2)) * .9)
    def segment_at(self, pos):
        c = self.SIZE / 2;dx = pos.x() - c;dy = pos.y() - c;r = math.hypot(dx, dy);n = len(self.items)
        if not self.paths or not n or r < self.INNER or r > self.OUTER: return -1
        return 0 if n == 1 else int((math.atan2(dx, -dy) % (2 * math.pi)) / (2 * math.pi / n))
    def tile_centre(self, i, n):
        angle = math.radians(90 if n == 1 else 90 - (i + .5) * 360 / n);r = self.ring_radius();c = self.SIZE / 2
        return QPointF(c + r * math.cos(angle), c - r * math.sin(angle))
    def split_radius(self): return (self.INNER + 6 + self.OUTER) / 2
    def splits(self, i):
        """Does tile i offer Separate / One file? Only PDF and Word conversions of several files."""
        return 0 <= i < len(self.items) and self.items[i].kind == 'convert' and bool(combine_target(self.items[i].key, self.paths))
    def part_at(self, pos, i):
        """'one' on the outer half of a split tile, 'separate' on the inner half, None for an ordinary tile."""
        if not self.splits(i): return None
        c = self.SIZE / 2;return 'one' if math.hypot(pos.x() - c, pos.y() - c) >= self.split_radius() else 'separate'
    def key_at(self, pos, i):
        key = self.items[i].key
        return combine_target(key, self.paths) if self.part_at(pos, i) == 'one' else key
    def tab_rects(self):
        w, h, gap = 122, 30, 10;x0 = (self.SIZE - (3 * w + 2 * gap)) / 2;y = self.SIZE / 2 + self.OUTER + 18
        return [QRectF(x0 + i * (w + gap), y, w, h) for i in range(3)]
    def tab_at(self, pos):
        for i, r in enumerate(self.tab_rects()):
            if r.adjusted(-3, -3, 3, 3).contains(QPointF(pos)): return i
        return -1
    # --- drag and drop --------------------------------------------------------------
    @staticmethod
    def local_files(mime):
        if not mime.hasUrls(): return []
        return [u.toLocalFile() for u in mime.urls() if u.isLocalFile() and not Path(u.toLocalFile()).is_dir()]
    def accept_copy(self, event):
        # Shift makes Explorer propose Move, after which the source deletes the originals.
        # Only a Copy answer is ever given.
        if event.possibleActions() & Qt.CopyAction: event.setDropAction(Qt.CopyAction);event.accept();return True
        event.ignore();return False
    def set_hover(self, index, tab=-1, part=None):
        if index == self.hover and tab == self.hover_tab and part == self.hover_part: return
        self.hover = index;self.hover_tab = tab;self.hover_part = part;self.restart_clock();self.describe();self.update()
    def hover_label(self):
        item = self.items[self.hover];label = item.label if item.kind == 'convert' else item.label.upper()
        return label + {'one': ' · One file', 'separate': ' · Separate files'}.get(self.hover_part, '')
    def describe(self):
        """Accessible description: the mode, and the tile under the pointer if any."""
        hot = self.hover_label() if 0 <= self.hover < len(self.items) else ''
        self.setAccessibleDescription(MODE_TITLES.get(self.mode, '') + (': ' + hot if hot else ''))
    def point_changed(self, pos):
        tab = self.tab_at(pos)
        if tab >= 0: self.set_mode(MODES[tab]);self.set_hover(-1, tab)
        else: index = self.segment_at(pos);self.set_hover(index, part=self.part_at(pos, index))
    def dragEnterEvent(self, event):
        files = self.local_files(event.mimeData())
        if not files or not self.accept_copy(event): event.ignore();return
        self.hide_timer.stop();self.paths = files;self.items = items_for(self.mode, files);self.hover = -1;self.update()
    def dragMoveEvent(self, event):
        if not self.paths or not self.accept_copy(event): event.ignore();return
        self.point_changed(event.position().toPoint())
    def dragLeaveEvent(self, event): self.set_hover(-1)
    def dropEvent(self, event):
        pos = event.position().toPoint();index = self.segment_at(pos);files = self.paths
        if index < 0 or not files or not self.accept_copy(event): event.ignore();self.dismiss();return
        item = self.items[index];key = self.key_at(pos, index);self.dismiss();self.chosen.emit(list(files), item.kind, key)
    # --- click-to-pick (tray and window menus) ---------------------------------------
    def mouseMoveEvent(self, event):
        if self.interactive: self.point_changed(event.position().toPoint())
    def mousePressEvent(self, event):
        if not self.interactive: return
        pos = event.position().toPoint();tab = self.tab_at(pos)
        if tab >= 0: self.set_mode(MODES[tab]);return
        index = self.segment_at(pos)
        if index >= 0: item = self.items[index];key = self.key_at(pos, index);files = list(self.paths);self.dismiss();self.chosen.emit(files, item.kind, key)
        else: self.dismiss()
    def keyPressEvent(self, event):
        if self.interactive and event.key() == Qt.Key_Escape: self.dismiss()
    def changeEvent(self, event):
        if event.type() == QEvent.ActivationChange and self.interactive and self.isVisible() and not self.isActiveWindow(): self.dismiss()
        super().changeEvent(event)
    # --- painting -------------------------------------------------------------------
    # GAP keeps clear space between neighbouring panes.
    BEZEL = 9;GAP = 8;ROUND = 12
    def wedge(self, i, n):
        """Rounded annular sector for slot i of n (cached). Sides are parallel to the radial centre line, so the gaps between wedges stay even."""
        key = (n, i)
        if key in self.wedges: return self.wedges[key]
        c = QPointF(self.SIZE / 2, self.SIZE / 2);k = self.ROUND;r_in = self.INNER + 6 + k;r_out = self.OUTER - k;path = QPainterPath()
        def ring(r): return QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
        if n == 1: path.addEllipse(ring(r_out));path.addEllipse(ring(r_in));path = path.simplified()
        else:
            step = 360 / n;hi = 90 - i * step;lo = hi - step;d = self.GAP / 2 + k
            m_in = math.degrees(math.asin(d / r_in));m_out = math.degrees(math.asin(d / r_out))
            path.arcMoveTo(ring(r_out), lo + m_out);path.arcTo(ring(r_out), lo + m_out, step - 2 * m_out)
            path.arcTo(ring(r_in), hi - m_in, -(step - 2 * m_in));path.closeSubpath()
        stroker = QPainterPathStroker();stroker.setWidth(2 * k);stroker.setJoinStyle(Qt.RoundJoin);shape = path.united(stroker.createStroke(path))
        self.wedges[key] = shape;return shape
    def paintEvent(self, _):
        L = LOOKS.get(self.look, LOOKS['light']);p = QPainter(self);p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
        c = QPointF(self.SIZE / 2, self.SIZE / 2);grow = ease_out_back(self.open);n = len(self.items);R = self.OUTER
        shadow = QRadialGradient(c + QPointF(0, 10), R + 30);shadow.setColorAt(.80, QColor(0, 0, 0, L.shadow));shadow.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen);p.setBrush(shadow);p.drawEllipse(c + QPointF(0, 10), R + 30, R + 30)
        # Light: light passing through a pearly rim gives the separate panes a shared surface.
        disc = (R + self.BEZEL) * (.86 + .14 * grow)
        p.setBrush(glass(QPointF(c.x() - disc, c.y() - disc), QPointF(c.x() + disc * .8, c.y() + disc), L.rim));p.setPen(QPen(L.rim_edge, 1.2));p.drawEllipse(c, disc, disc)
        rmid = (R + self.INNER + 6) / 2;top, bottom = QPointF(c.x() - R * .75, c.y() - R), QPointF(c.x() + R * .6, c.y() + R)
        for i, item in enumerate(self.items):
            local = ease_out_back(self.open * 1.5 - i * .05);lift = self.lift[i];shape = self.wedge(i, n)
            angle = math.radians(90 if n == 1 else 90 - (i + .5) * 360 / n);cen = QPointF(c.x() + rmid * math.cos(angle), c.y() - rmid * math.sin(angle))
            p.save();p.setOpacity(max(0.0, min(1.0, local * 1.4)));grow_in = .55 + .45 * min(1.0, max(0.0, local))
            p.translate(c);p.scale(grow_in, grow_in);p.translate(-c);p.translate(cen);p.scale(1 + .06 * lift, 1 + .06 * lift);p.translate(-cen)
            if L.sheen: p.save();p.translate(0, 3);p.setBrush(QColor(12, 33, 48, 18));p.setPen(QPen(QColor(12, 33, 48, 12), 5));p.drawPath(shape);p.restore()
            p.setBrush(glass(top, bottom, L.pane));p.setPen(QPen(L.pane_edge, 1.1));p.drawPath(shape)
            split = self.splits(i);halves = None
            if split:
                rim = QPainterPath();rs = self.split_radius();rim.addEllipse(c, rs, rs);halves = {'separate': shape.intersected(rim), 'one': shape.subtracted(rim)}
            # A split tile lights only the half under the pointer.
            hot_shape = halves[self.hover_part] if split and i == self.hover and self.hover_part else shape
            if lift > .01: p.setBrush(glass(top, bottom, L.hot, lift));p.setPen(Qt.NoPen);p.drawPath(hot_shape)
            if L.sheen:
                p.save();p.setClipPath(shape);sheen = QRadialGradient(c.x() - R * .35, c.y() - R * .9, R * 1.5)
                sheen.setColorAt(0, QColor(255, 255, 255, 95));sheen.setColorAt(1, QColor(255, 255, 255, 0));p.fillRect(shape.boundingRect(), sheen);p.restore()
            width = min(R - self.INNER - 34, 2 * rmid * math.sin(math.pi / max(n, 2)) * .7);ink = L.ink_hot if lift > .5 else L.ink;p.setPen(ink)
            if split:
                # A faint seam marks the two halves; hovering names them.
                p.save();p.setClipPath(shape);p.setPen(QPen(L.pane_edge if i == self.hover else L.muted, 1.2, Qt.SolidLine if i == self.hover else Qt.DotLine));p.setBrush(Qt.NoBrush)
                p.drawEllipse(c, self.split_radius(), self.split_radius());p.restore();p.setPen(ink)
            if split and i == self.hover and lift > .05:
                # Hovered with several files: name both halves so the drop can go straight to the right one.
                for part, text, r in (('separate', 'Separate', (self.INNER + 6 + self.split_radius()) / 2), ('one', 'One file', (self.split_radius() + R) / 2)):
                    at = QPointF(c.x() + r * math.cos(angle), c.y() - r * math.sin(angle));w = max(28.0, min(R - self.INNER - 20, 2 * r * math.sin(math.pi / max(n, 2)) * .8))
                    p.setPen(L.ink_hot if part == self.hover_part and lift > .5 else L.ink);p.setFont(fit_font(text, w, 9, QFont.Bold));p.drawText(QRectF(at.x() - w / 2, at.y() - 10, w, 20), Qt.AlignCenter, text)
            elif item.kind == 'convert':
                p.setFont(fit_font(item.label, width, 11, QFont.Bold));p.drawText(QRectF(cen.x() - width / 2, cen.y() - 12, width, 24), Qt.AlignCenter, item.label)
            else:
                draw_icon(p, item.key, QRectF(cen.x() - 9, cen.y() - 20, 18, 18), ink)
                p.setFont(fit_font(item.label.upper(), width, 7, QFont.Bold));p.drawText(QRectF(cen.x() - width / 2, cen.y() + 2, width, 14), Qt.AlignCenter, item.label.upper())
            p.restore()
        self.paint_hub(p, c, grow, L);self.paint_tabs(p, L)
    def paint_hub(self, p, c, grow, L):
        r = (self.INNER - 4) * min(1.0, .6 + .4 * grow);hot = 0 <= self.hover < len(self.items)
        halo = QRadialGradient(c.x() - r * .25, c.y() - r * .4, r * 1.3);halo.setColorAt(0, L.hub[0]);halo.setColorAt(1, L.hub[1])
        p.setBrush(halo);p.setPen(QPen(L.hub_edge, 1.2));p.drawEllipse(c, r, r)
        box = QRectF(c.x() - r + 8, c.y() - r + 8, 2 * r - 16, 2 * r - 16);pill = QRectF(box.left(), c.y() - 16, box.width(), 32)
        p.setBrush(L.pill);p.setPen(QPen(L.pill_edge, 1));p.drawRoundedRect(pill, 16, 16);inner = pill.adjusted(6, 2, -6, -2);p.setPen(L.ink)
        if hot:
            item = self.items[self.hover];label = self.hover_label();p.setFont(fit_font(label, inner.width(), 11 if item.kind == 'convert' else 8, QFont.Normal if item.kind == 'convert' else QFont.Bold))
            p.drawText(inner, Qt.AlignCenter, label)
        else:
            message = ('Drag files here' if not self.paths else EMPTY[self.mode] if not self.items else PROMPT[self.mode]);p.setFont(fit_font(message, inner.width(), 9, QFont.DemiBold))
            p.drawText(inner, Qt.AlignCenter | Qt.TextWordWrap, message)
        p.setFont(ui_font(7.5));p.setPen(L.muted)
        p.drawText(QRectF(box.left(), pill.bottom() + 6, box.width(), 16), Qt.AlignCenter, p.fontMetrics().elidedText(self.summary(), Qt.ElideMiddle, int(box.width())))
    def paint_tabs(self, p, L):
        for i, (mode, rect) in enumerate(zip(MODES, self.tab_rects())):
            active = mode == self.mode;hovered = i == self.hover_tab and not active
            p.setBrush(glass(rect.topLeft(), rect.bottomRight(), L.hot) if active else L.tab_hover if hovered else L.tab)
            p.setPen(QPen(L.tab_edge, 1));p.drawRoundedRect(rect, 15, 15)
            p.setFont(ui_font(9, QFont.DemiBold));p.setPen(L.ink_hot if active else L.ink);p.drawText(QRectF(rect.left() + 12, rect.top(), rect.width() - 24, rect.height()), Qt.AlignVCenter | Qt.AlignLeft, MODE_TITLES[mode])
            p.setFont(ui_font(7));p.setPen(L.tab_hint_hot if active else L.muted)
            p.drawText(QRectF(rect.left() + 12, rect.top(), rect.width() - 24, rect.height()), Qt.AlignVCenter | Qt.AlignRight, MODE_KEYS[mode])
    def summary(self):
        if not self.paths: return ''
        first = Path(self.paths[0]).name
        return first if len(self.paths) == 1 else f'{len(self.paths)} files'

class CardLook:
    def __init__(self, **kw): self.__dict__.update(kw)

CARD_LOOKS = {
    # Light: frosted glass like the Light wheel. Dark: the main window's charcoal and Tangerine orange.
    'light': CardLook(top=QColor(255, 255, 255, 245), bottom=QColor(234, 243, 248, 240), edge=QColor(33, 51, 64, 45), text=QColor('#213340'), muted=QColor(38, 61, 74, 185),
                      track=QColor(33, 51, 64, 38), accent=QColor('#ff610a'), ok=QColor('#2f9e5a'), error=QColor('#d9443a'), glyph=QColor('#ffffff'),
                      button=QColor(255, 255, 255, 215), button_hot=QColor(255, 255, 255), button_edge=QColor(33, 51, 64, 55), shadow=38),
    'dark': CardLook(top=QColor(27, 27, 27, 248), bottom=QColor(21, 21, 21, 248), edge=QColor('#444444'), text=QColor('#f5f3ed'), muted=QColor(245, 243, 237, 160),
                     track=QColor('#3a3a3a'), accent=QColor('#ff610a'), ok=QColor('#4cd964'), error=QColor('#ff5a52'), glyph=QColor('#101010'),
                     button=QColor(34, 34, 34), button_hot=QColor(44, 44, 44), button_edge=QColor('#4a4a4a'), shadow=70)}

def wrap_lines(text, font, width, max_lines):
    """Lines of `text` wrapped to `width` (at word boundaries, or anywhere for long paths); the last allowed line is elided if more remains."""
    if not text: return []
    layout = QTextLayout(text, font);option = QTextOption();option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere);layout.setTextOption(option)
    layout.beginLayout();starts = []
    while True:
        line = layout.createLine()
        if not line.isValid(): break
        line.setLineWidth(width);starts.append((line.textStart(), line.textLength()))
    layout.endLayout()
    lines = [text[a:a + n].rstrip() for a, n in starts[:max_lines]]
    if len(starts) > max_lines: lines[-1] = QFontMetricsF(font).elidedText(text[starts[max_lines - 1][0]:].replace('\n', ' '), Qt.ElideRight, width)
    return lines

class Notch(QWidget):
    """Progress card: a floating notification that shows what the drag wheel is doing.

    It sits in the screen corner chosen in Settings (top left, top centre, top right, bottom left or bottom right) and
    follows the Light/Dark theme. The title and the full description wrap instead of being cut off, and the card grows
    to fit. Finished messages stay for at least their reading time (errors longer), pause while the pointer is over the
    card, and show the time left as a thin line along the bottom. × closes it; Open folder and Copy details are buttons."""
    W = 380;M = 26;GAP = 14;RADIUS = 14;PAD = 16
    TITLE_LINES = 3;DETAIL_LINES = 12
    MIN_SECONDS = {'ok': 6.0, 'error': 15.0}
    def __init__(self, settings=None):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground);self.setAttribute(Qt.WA_ShowWithoutActivating);self.setMouseTracking(True)
        self.setAccessibleName('Open Tangerine progress');self.settings = settings;self.look = 'light';self.position = 'top-center';self.H = 96;self.setFixedSize(self.W + 2 * self.M, self.H + 2 * self.M)
        self.text = '';self.detail = '';self.kind = 'info';self.folder = None;self.fraction = None;self.shown = 0.0;self.phase = 0.0;self.hot = False;self.hide_when_done = False
        self.total = 0.0;self.left = 0.0;self.hover_button = None;self.copied = False;self.rects = {};self.lines = ([], [])
        self.theme = Theme();self.shadow_cache = None
        self.move_anim = QPropertyAnimation(self, b'pos', self);self.move_anim.setDuration(280);self.move_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.fade_anim = QPropertyAnimation(self, b'windowOpacity', self);self.fade_anim.setDuration(200);self.fade_anim.finished.connect(self.slide_done)
        self.spin = QTimer(self);self.spin.setInterval(16);self.spin.setTimerType(Qt.PreciseTimer);self.spin.timeout.connect(self.step);self.clock = QElapsedTimer();self.last = 0
    # --- placement --------------------------------------------------------------------
    def read_settings(self):
        if self.settings is None: return
        import prefs
        self.look = prefs.wheel_theme(self.settings);self.position = prefs.card_position(self.settings)
    def anchor(self):
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen();g = screen.availableGeometry();vertical, _, horizontal = self.position.partition('-')
        x = g.left() + self.GAP - self.M if horizontal == 'left' else g.right() - self.GAP - self.W - self.M + 1 if horizontal == 'right' else g.center().x() - self.width() // 2
        y = g.bottom() - self.GAP - self.H - self.M + 1 if vertical == 'bottom' else g.top() + self.GAP - self.M
        return QPoint(x, y)
    def offset(self, distance):
        """Toward the nearest screen edge: up for top positions, down for bottom ones."""
        return QPoint(0, distance if self.position.startswith('bottom') else -distance)
    def slide(self, end, visible):
        self.move_anim.stop();self.fade_anim.stop();self.hide_when_done = not visible
        self.move_anim.setStartValue(self.pos());self.move_anim.setEndValue(end);self.fade_anim.setStartValue(self.windowOpacity());self.fade_anim.setEndValue(1.0 if visible else 0.0)
        self.move_anim.start();self.fade_anim.start()
    def slide_done(self):
        if self.hide_when_done: self.hide();self.spin.stop()
    # --- content ----------------------------------------------------------------------
    def fonts(self): return ui_font(10.5, QFont.DemiBold), ui_font(9.5), ui_font(8.5, QFont.DemiBold), ui_font(9, QFont.DemiBold)
    def buttons(self):
        names = []
        if self.folder and self.kind != 'info': names.append(('folder', 'Open folder'))
        if self.kind == 'error' and self.detail: names.append(('copy', 'Copied' if self.copied else 'Copy details'))
        return names
    def layout(self):
        """Measure the card for the current message and remember where each part goes."""
        title_font, detail_font, _, button_font = self.fonts();text_left = self.PAD + 34;width = self.W - text_left - self.PAD
        title = wrap_lines(self.text, title_font, width, self.TITLE_LINES);detail = wrap_lines(self.detail, detail_font, width, self.DETAIL_LINES)
        tl, dl = QFontMetricsF(title_font).lineSpacing(), QFontMetricsF(detail_font).lineSpacing()
        y = 44.0;self.rects = {'close': QRectF(self.W - self.PAD - 22, 11, 22, 22), 'status': QRectF(self.PAD, y + 1, 24, 24)}
        self.rects['title'] = QRectF(text_left, y, width, tl * max(1, len(title)));y += tl * max(1, len(title))
        if detail: y += 3;self.rects['detail'] = QRectF(text_left, y, width, dl * len(detail));y += dl * len(detail)
        if self.kind == 'info': y += 12;self.rects['track'] = QRectF(text_left, y, width - 44, 5);y += 5
        names = self.buttons()
        if names:
            y += 14;x = self.W - self.PAD;fm = QFontMetricsF(button_font)
            for key, label in reversed(names):
                w = fm.horizontalAdvance(label) + 26;x -= w;self.rects['button:' + key] = QRectF(x, y, w, 28);x -= 8
            y += 28
        self.lines = (title, detail);return int(math.ceil(y + self.PAD))
    def reading_seconds(self):
        """Time to read the message at a relaxed pace (about 15 characters a second), plus a moment to notice it."""
        return 3.0 + len(self.text + self.detail) / 15
    def show_message(self, text, kind='info', folder=None, seconds=0, fraction=None, detail=''):
        """kind: info (working), ok, error. Finished messages (`seconds`>0, or any ok/error) close on their own after
        at least their reading time; a working message stays until replaced."""
        if not self.isVisible(): self.read_settings()
        self.text = text;self.detail = detail;self.kind = kind;self.folder = folder;self.fraction = fraction;self.copied = False
        self.setAccessibleDescription(text + ('. ' + detail if detail else '') + (f' {round(100 * fraction)}%' if fraction is not None else ''))
        # Beyond DETAIL_LINES the last line is elided; the tooltip and Copy details still give the whole text.
        height = self.layout();self.setToolTip(detail if detail and len(wrap_lines(detail, self.fonts()[1], self.rects['title'].width(), 999)) > self.DETAIL_LINES else '')
        if height != self.H: self.H = height;self.setFixedSize(self.W + 2 * self.M, self.H + 2 * self.M);self.shadow_cache = None
        timed = kind != 'info' or seconds;self.total = self.left = max(seconds, self.MIN_SECONDS.get(kind, 0.0), self.reading_seconds()) if timed else 0.0
        top = self.anchor()
        if not self.isVisible(): self.theme.refresh();self.shadow_cache = None;self.shown = 0.0;self.setWindowOpacity(0.0);self.move(top + self.offset(16));self.show()
        if self.pos() != top or self.windowOpacity() < 1 or self.hide_when_done: self.slide(top, True)
        self.clock.start();self.last = 0;self.spin.start();self.update()
    def retract(self): self.total = self.left = 0.0;self.slide(self.pos() + self.offset(14), False)
    def step(self):
        now = self.clock.elapsed();dt = min((now - self.last) / 1000, .05);self.last = now;self.phase = (self.phase + dt * 1.25) % 1.0
        goal = self.fraction if self.fraction is not None else 0.0;self.shown += (goal - self.shown) * (1 - math.exp(-dt * 9))
        if self.total and not self.hot and not self.hide_when_done:
            self.left -= dt
            if self.left <= 0: self.retract()
        if self.kind != 'info' and not self.total and not self.isVisible(): self.spin.stop()
        self.update()
    # --- pointer ----------------------------------------------------------------------
    def card_point(self, pos): return QPointF(pos) - QPointF(self.M, self.M)
    def button_at(self, pos):
        point = self.card_point(pos)
        for key, rect in self.rects.items():
            if (key == 'close' or key.startswith('button:')) and rect.adjusted(-3, -3, 3, 3).contains(point): return key
        return None
    # Hovering pauses the countdown, so a message never disappears while it is being read.
    def enterEvent(self, _): self.hot = True;self.update()
    def leaveEvent(self, _):
        self.hot = False;self.hover_button = None;self.setCursor(Qt.ArrowCursor)
        if self.total: self.left = max(self.left, 2.5)
        self.update()
    def mouseMoveEvent(self, event):
        key = self.button_at(event.position());self.setCursor(Qt.PointingHandCursor if key else Qt.ArrowCursor)
        if key != self.hover_button: self.hover_button = key;self.update()
    def mousePressEvent(self, event):
        key = self.button_at(event.position())
        if key == 'close': self.retract()
        elif key == 'button:folder': QDesktopServices.openUrl(QUrl.fromLocalFile(self.folder));self.retract()
        elif key == 'button:copy':
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(f'{self.text}\n{self.detail}');self.copied = True;self.layout();self.update()
    # --- painting ---------------------------------------------------------------------
    def shadow(self):
        if self.shadow_cache is None:
            L = CARD_LOOKS.get(self.look, CARD_LOOKS['light']);pm = QPixmap(self.size());pm.fill(Qt.transparent);q = QPainter(pm);q.setRenderHint(QPainter.Antialiasing);q.setPen(Qt.NoPen)
            for i in range(self.M - 6, 0, -1):
                a = int(L.shadow * (1 - i / (self.M - 5)) ** 2.2);q.setBrush(QColor(0, 0, 0, a));q.drawRoundedRect(QRectF(self.M - i, self.M - i + 5, self.W + 2 * i, self.H + 2 * i), self.RADIUS + i, self.RADIUS + i)
            q.end();self.shadow_cache = pm
        return self.shadow_cache
    def paintEvent(self, _):
        L = CARD_LOOKS.get(self.look, CARD_LOOKS['light']);p = QPainter(self);p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
        p.drawPixmap(0, 0, self.shadow());p.translate(self.M, self.M);card = QRectF(0, 0, self.W, self.H)
        face = QLinearGradient(0, 0, 0, self.H);face.setColorAt(0, L.top);face.setColorAt(1, L.bottom);p.setBrush(face);p.setPen(QPen(L.edge, 1));p.drawRoundedRect(card.adjusted(.5, .5, -.5, -.5), self.RADIUS, self.RADIUS)
        title_font, detail_font, header_font, button_font = self.fonts()
        # Header: app icon and name, × to close.
        logo = app_logo();icon = QRectF(self.PAD, 13, 18, 18)
        if logo: clip = QPainterPath();clip.addRoundedRect(icon, 5, 5);p.save();p.setClipPath(clip);p.drawPixmap(icon.toRect(), logo);p.restore()
        p.setFont(header_font);p.setPen(L.muted);p.drawText(QRectF(icon.right() + 8, 11, 200, 22), Qt.AlignVCenter | Qt.AlignLeft, 'Open Tangerine')
        close = self.rects['close'];hot = self.hover_button == 'close'
        if hot: p.setPen(Qt.NoPen);p.setBrush(L.track);p.drawRoundedRect(close, 6, 6)
        p.setPen(QPen(L.text if hot else L.muted, 1.5, Qt.SolidLine, Qt.RoundCap));c = close.center()
        p.drawLine(c + QPointF(-4, -4), c + QPointF(4, 4));p.drawLine(c + QPointF(-4, 4), c + QPointF(4, -4))
        # Status: spinner while working, a check when done, ! on error.
        status = self.rects['status'];sc = status.center();tone = {'ok': L.ok, 'error': L.error}.get(self.kind, L.accent)
        if self.kind == 'info':
            p.setBrush(Qt.NoBrush);p.setPen(QPen(L.track, 2.6));p.drawEllipse(sc, 10, 10)
            p.setPen(QPen(tone, 2.6, Qt.SolidLine, Qt.RoundCap));p.drawArc(QRectF(sc.x() - 10, sc.y() - 10, 20, 20), int(-self.phase * 360 * 16), 110 * 16)
        else:
            p.setPen(Qt.NoPen);p.setBrush(tone);p.drawEllipse(sc, 11, 11);p.setPen(QPen(L.glyph, 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin));p.setBrush(Qt.NoBrush)
            if self.kind == 'ok': check = QPainterPath();check.moveTo(sc + QPointF(-4.5, .3));check.lineTo(sc + QPointF(-1.2, 3.6));check.lineTo(sc + QPointF(4.8, -3.4));p.drawPath(check)
            else: p.drawLine(sc + QPointF(0, -5), sc + QPointF(0, 1));p.drawPoint(sc + QPointF(0, 4.8))
        # Title and the full description, wrapped.
        title, detail = self.lines
        for font, color, lines, rect in ((title_font, L.text, title, self.rects['title']), (detail_font, L.muted, detail, self.rects.get('detail'))):
            if not rect: continue
            p.setFont(font);p.setPen(color);fm = QFontMetricsF(font);y = rect.top()
            for line in lines: p.drawText(QRectF(rect.left(), y, rect.width() + 2, fm.lineSpacing()), Qt.AlignLeft | Qt.AlignVCenter, line);y += fm.lineSpacing()
        # Progress: determinate with a percentage, or a sweeping segment when the amount is unknown.
        track = self.rects.get('track')
        if track:
            p.setPen(Qt.NoPen);p.setBrush(L.track);p.drawRoundedRect(track, 2.5, 2.5);p.setBrush(L.accent)
            if self.fraction is None:
                span = track.width() * .32;x = track.left() + (track.width() + span) * self.phase - span;a = max(track.left(), x);b = min(x + span, track.right())
                if b > a: p.drawRoundedRect(QRectF(a, track.top(), b - a, track.height()), 2.5, 2.5)
            else:
                if self.shown > 0: p.drawRoundedRect(QRectF(track.left(), track.top(), max(5, track.width() * min(1.0, self.shown)), track.height()), 2.5, 2.5)
                p.setFont(button_font);p.setPen(L.muted);p.drawText(QRectF(track.right() + 6, track.center().y() - 9, 38, 18), Qt.AlignRight | Qt.AlignVCenter, f'{round(100 * min(1.0, self.fraction))}%')
        for key, label in self.buttons():
            rect = self.rects['button:' + key];hot = self.hover_button == 'button:' + key
            p.setBrush(L.button_hot if hot else L.button);p.setPen(QPen(L.button_edge, 1));p.drawRoundedRect(rect, 8, 8)
            p.setFont(button_font);p.setPen(L.text);p.drawText(rect, Qt.AlignCenter, label)
        # Time left before it closes; frozen while the pointer is over the card.
        if self.total and self.left > 0:
            p.setPen(Qt.NoPen);c = QColor(tone);c.setAlpha(140);p.setBrush(c);p.save();edge = QPainterPath();edge.addRoundedRect(card, self.RADIUS, self.RADIUS);p.setClipPath(edge)
            p.drawRect(QRectF(0, self.H - 3, self.W * self.left / self.total, 3));p.restore()
