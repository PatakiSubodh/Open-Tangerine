"""Settings window: General (output folder, start with Windows, drag wheel, excluded applications), Formats (helper programs) and About."""
import os, subprocess, sys
from pathlib import Path
from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QScrollArea,
                               QStackedWidget, QVBoxLayout, QWidget)
import engine, prefs, theme

PURPOSE = {'ffmpeg': 'Audio and video conversion, trim, compress', 'tesseract': 'OCR: read text from images and scanned PDFs', 'soffice': 'Word, Excel and PowerPoint to PDF'}
VERSION_ARGS = {'ffmpeg': ['-version'], 'tesseract': ['--version'], 'soffice': ['--version']}
PAGES = (('general', 'General', 'Where results go, and how the drag wheel behaves.'), ('formats', 'Formats', 'The optional programs behind OCR, Office and audio/video.'), ('about', 'About', 'Small utility. Open possibilities.'))
WEBSITE = 'https://sintaxerrorpvtltd.github.io/Open-Tangerine/'
STYLE = '''
QListWidget#sidebar{background:#141414;border:none;border-right:1px solid #2c2c2c;border-radius:0;padding:14px 10px;outline:0}
QListWidget#sidebar::item{padding:11px 14px;border-radius:9px;margin-bottom:4px;color:#d8d8d8}
QListWidget#sidebar::item:selected{background:#ff610a;color:#101010;font-weight:bold}
QListWidget#sidebar::item:hover:!selected{background:#262626}
QScrollArea{border:none}
'''

def helper_state(settings, key):
    """(path, source) where source is 'chosen', 'detected' or '' when the helper is unavailable."""
    chosen = settings.value(key, '')
    if chosen and Path(chosen).is_file(): return chosen, 'chosen'
    found = engine.find_tool(key)
    return (str(found), 'detected') if found else ('', '')

def helper_health(path, args, timeout=8):
    """Ask a helper for its version, as the Mac does for FFmpeg. Returns ('ready', first line of its answer) or ('broken', why)."""
    try:
        done = subprocess.run([path, *args], capture_output=True, text=True, errors='replace', timeout=timeout, stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except subprocess.TimeoutExpired: return 'broken', f'did not answer within {timeout} seconds'
    except OSError as e: return 'broken', e.strerror or str(e)
    lines = [l.strip() for l in (done.stdout + '\n' + done.stderr).splitlines() if l.strip()]
    if done.returncode != 0: return 'broken', (lines[0][:120] if lines else f'exited with code {done.returncode}')
    return 'ready', lines[0][:120] if lines else 'no version reported'

def probe_path(key, path):
    """The program to ask for a version. On Windows, `soffice.exe --version` opens a terminal window of its own (LibreOffice 26.x),
    so its console twin soffice.com, which answers silently into our pipe, is asked instead."""
    p = Path(path)
    if key == 'soffice' and os.name == 'nt' and p.suffix.lower() == '.exe' and p.with_suffix('.com').is_file(): return str(p.with_suffix('.com'))
    return path

class HealthCheck(QThread):
    """Runs helper_health off the interface thread, so a slow LibreOffice start never freezes the window."""
    answered = Signal(str, str, str)
    def __init__(self, key, path, parent=None): super().__init__(parent);self.key = key;self.path = path
    def run(self): state, text = helper_health(probe_path(self.key, self.path), VERSION_ARGS[self.key]);self.answered.emit(self.key, state, text)

def section(title, body=None):
    """A heading and a card; returns (heading, card layout)."""
    frame, box = theme.card();return theme.label(title, 'heading'), frame, box

class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None, controller=None, tab='general'):
        super().__init__(parent);self.settings = settings;self.controller = controller;self.rows = {};self.checks = [];self.pages = {}
        self.setWindowTitle('Settings');self.setMinimumSize(780, 560);self.resize(820, 620);self.setStyleSheet(STYLE)
        outer = QHBoxLayout(self);outer.setContentsMargins(0, 0, 0, 0);outer.setSpacing(0)
        self.sidebar = QListWidget();self.sidebar.setObjectName('sidebar');self.sidebar.setFixedWidth(190);self.sidebar.setFocusPolicy(Qt.TabFocus)
        for key, title, _ in PAGES: item = QListWidgetItem(title);item.setData(Qt.UserRole, key);self.sidebar.addItem(item)
        outer.addWidget(self.sidebar)
        right = QVBoxLayout();right.setContentsMargins(26, 20, 26, 16);right.setSpacing(10);outer.addLayout(right, 1)
        self.title = theme.label('', 'title');self.blurb = theme.label('', 'muted', True);right.addWidget(self.title);right.addWidget(self.blurb)
        self.stack = QStackedWidget();right.addWidget(self.stack, 1)
        for key, builder in (('general', self.build_general), ('formats', self.build_formats), ('about', self.build_about)):
            page = QWidget();column = QVBoxLayout(page);column.setContentsMargins(0, 6, 8, 6);column.setSpacing(10);builder(column);column.addStretch(1)
            area = QScrollArea();area.setWidgetResizable(True);area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff);area.setWidget(page);self.stack.addWidget(area);self.pages[key] = self.stack.count() - 1
        close = QPushButton('Done');close.setProperty('primary', True);close.clicked.connect(self.accept);row = QHBoxLayout();row.addStretch(1);row.addWidget(close);right.addLayout(row)
        self.sidebar.currentRowChanged.connect(self.show_page);self.show_tab(tab);self.refresh()

    def show_tab(self, key):
        row = self.pages.get(key, 0);self.sidebar.setCurrentRow(row);self.show_page(row)
    def show_page(self, row):
        if row < 0: return
        self.stack.setCurrentIndex(row);_, title, blurb = PAGES[row];self.title.setText(title);self.blurb.setText(blurb)

    # --- General ---------------------------------------------------------------------
    def build_general(self, col):
        head, frame, box = section('Output');col.addWidget(head);col.addWidget(frame)
        row = QHBoxLayout();row.addWidget(QLabel('Save converted files'));self.mode = QComboBox()
        for key, title in prefs.OUTPUT_MODES: self.mode.addItem(title, key)
        self.mode.setCurrentIndex(max(0, self.mode.findData(prefs.output_mode(self.settings))));self.mode.currentIndexChanged.connect(self.mode_changed);row.addWidget(self.mode, 1);box.addLayout(row)
        self.custom_row = QWidget();custom = QHBoxLayout(self.custom_row);custom.setContentsMargins(0, 0, 0, 0)
        self.custom_label = theme.label('', 'muted', True);custom.addWidget(self.custom_label, 1);pick = QPushButton('Choose folder…');pick.clicked.connect(self.choose_folder);custom.addWidget(pick);box.addWidget(self.custom_row)
        self.reveal = QCheckBox('Show the results in Explorer when a conversion finishes');self.reveal.setChecked(prefs.reveal_results(self.settings));self.reveal.toggled.connect(lambda on: self.settings.setValue('output/reveal', bool(on)));box.addWidget(self.reveal)
        box.addWidget(theme.label('A folder you pick for one conversion in the main window overrides this once.', 'muted', True))
        # Shown on every platform: the glass wheel in the main window follows it everywhere, and on Windows the drag wheel too.
        head, frame, box = section('Appearance');col.addWidget(head);col.addWidget(frame)
        row = QHBoxLayout();row.addWidget(QLabel('Theme'));self.wheel_theme = QComboBox();self.wheel_theme.setAccessibleName('Wheel and progress card theme')
        for key, title in prefs.WHEEL_THEMES: self.wheel_theme.addItem(title, key)
        self.wheel_theme.setCurrentIndex(max(0, self.wheel_theme.findData(prefs.wheel_theme(self.settings))));self.wheel_theme.currentIndexChanged.connect(lambda _: self.settings.setValue('wheel/theme', self.wheel_theme.currentData()));row.addWidget(self.wheel_theme, 1);box.addLayout(row)
        box.addWidget(theme.label('Light is frosted glass; Dark uses the window colours, charcoal and Tangerine orange. Applies to the wheel beside the file list' + (', the drag wheel and the progress card.' if os.name == 'nt' else '.'), 'muted', True))
        if os.name == 'nt':
            import wheel
            head, frame, box = section('Windows');col.addWidget(head);col.addWidget(frame)
            self.startup = QCheckBox('Start with Windows');self.startup.setChecked(wheel.startup_enabled());self.startup.toggled.connect(self.set_startup);box.addWidget(self.startup)
            box.addWidget(theme.label('Opens Open Tangerine in the system tray after you sign in, ready for the drag wheel. Moving or renaming the program afterwards turns this off; switch it on again here.', 'muted', True))
        if self.controller:
            head, frame, box = section('Drag wheel');col.addWidget(head);col.addWidget(frame)
            self.wheel_on = QCheckBox('Drag wheel');self.wheel_on.setChecked(self.controller.enabled);self.wheel_on.toggled.connect(self.controller.set_enabled);box.addWidget(self.wheel_on)
            row = QHBoxLayout();row.addWidget(QLabel('Progress card'));self.card_position = QComboBox();self.card_position.setAccessibleName('Progress card position')
            for key, title in prefs.CARD_POSITIONS: self.card_position.addItem(title, key)
            self.card_position.setCurrentIndex(max(0, self.card_position.findData(prefs.card_position(self.settings))));self.card_position.currentIndexChanged.connect(lambda _: self.settings.setValue('card/position', self.card_position.currentData()));row.addWidget(self.card_position, 1);box.addLayout(row)
            self.any_app = QCheckBox('Also trigger from other apps');self.any_app.setChecked(self.settings.value('wheel/any_app', False, type=bool));self.any_app.toggled.connect(self.controller.set_any_app);box.addWidget(self.any_app)
            box.addWidget(theme.label('Hold a key while you drag files, then release over a tile. Shift converts, Alt opens the editing tools and Ctrl+Shift opens file actions. By default the wheel starts from Explorer, the desktop and file dialogs only.', 'muted', True))
        head, frame, box = section('Excluded applications');col.addWidget(head);col.addWidget(frame)
        box.addWidget(theme.label('The drag wheel stays off when a drag starts in one of these programs, for example a design tool that uses Shift while dragging. You can still open the wheel from the tray menu.', 'muted', True))
        self.excluded = QListWidget();self.excluded.setMinimumHeight(96);self.excluded.setMaximumHeight(150);self.excluded.itemSelectionChanged.connect(self.update_excluded_buttons);box.addWidget(self.excluded)
        row = QHBoxLayout();add = QPushButton('Add application…');add.clicked.connect(self.add_excluded);row.addWidget(add)
        self.remove_excluded = QPushButton('Remove');self.remove_excluded.clicked.connect(self.remove_selected_excluded);row.addWidget(self.remove_excluded);row.addStretch(1);box.addLayout(row)
        self.update_excluded();self.mode_changed()
    def mode_changed(self, *_):
        mode = self.mode.currentData();self.settings.setValue('output/mode', mode);self.custom_row.setVisible(mode == 'custom')
        folder = prefs.custom_folder(self.settings)
        self.custom_label.setText(folder if folder and Path(folder).is_dir() else 'No folder chosen yet; results stay next to the original until you choose one.' if not folder else f'{folder} was not found; results stay next to the original.')
    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Choose where converted files are saved', prefs.custom_folder(self.settings) or str(Path.home()))
        if folder: self.settings.setValue('output/folder', str(Path(folder)));self.mode_changed()
    def set_startup(self, on):
        import wheel
        try: wheel.set_startup(on)
        except OSError: self.startup.blockSignals(True);self.startup.setChecked(wheel.startup_enabled());self.startup.blockSignals(False)
        if self.controller: self.controller.refresh_menu()
    def update_excluded(self):
        self.excluded.clear()
        for name, display in prefs.excluded(self.settings).items():
            item = QListWidgetItem(f'{display}   ({name})');item.setData(Qt.UserRole, name);self.excluded.addItem(item)
        self.update_excluded_buttons()
    def update_excluded_buttons(self): self.remove_excluded.setEnabled(bool(self.excluded.selectedItems()))
    def add_excluded(self):
        start = os.environ.get('ProgramFiles', str(Path.home())) if os.name == 'nt' else str(Path.home())
        paths = QFileDialog.getOpenFileNames(self, 'Choose programs where the drag wheel should stay off', start, 'Programs (*.exe)')[0]
        for p in paths: prefs.add_excluded(self.settings, p)
        self.update_excluded()
    def remove_selected_excluded(self):
        for item in self.excluded.selectedItems(): prefs.remove_excluded(self.settings, item.data(Qt.UserRole))
        self.update_excluded()

    # --- Formats ---------------------------------------------------------------------
    def build_formats(self, col):
        col.addWidget(theme.label('Open Tangerine finds these programs automatically when they are installed. They run only when a conversion needs them and are never downloaded for you.', 'muted', True))
        for key, (name, _, hint) in engine.TOOLS.items():
            frame, box = theme.card()
            top = QHBoxLayout();top.addWidget(QLabel(f'<b>{name}</b> — {PURPOSE[key]}'), 1)
            choose = QPushButton('Choose…');choose.clicked.connect(lambda _=False, k=key, n=name: self.choose(k, n));top.addWidget(choose)
            auto = QPushButton('Use automatic');auto.setToolTip('Forget the chosen file and look for an installed copy');auto.clicked.connect(lambda _=False, k=key: self.reset(k));top.addWidget(auto)
            status = QLabel();status.setWordWrap(True);status.setTextInteractionFlags(Qt.TextSelectableByMouse)
            box.addLayout(top);box.addWidget(status);col.addWidget(frame);self.rows[key] = (status, auto, hint)
        self.langs = theme.label('', 'muted', True);col.addWidget(self.langs)
    def refresh(self):
        self.checks = [c for c in self.checks if c.isRunning()]
        for key, (status, auto, hint) in self.rows.items():
            path, source = helper_state(self.settings, key);auto.setVisible(source == 'chosen')
            if source:
                status.setText(f'<span style="color:#a8a8a8">Checking…</span> {path}');check = HealthCheck(key, path, self);check.answered.connect(self.health);self.checks.append(check);check.start()
            else: status.setText('<span style="color:#ffb454">Not found.</span> ' + (f'Install it with <code>{hint}</code> or choose the program yourself.' if os.name == 'nt' else 'Install it with your package manager or choose the program yourself.'))
        path, _ = helper_state(self.settings, 'tesseract')
        installed = [l for l in engine.tesseract_languages(path) if l != 'osd'] if path else []
        self.langs.setText('OCR languages installed: ' + ', '.join(installed) + '. Type a code such as eng+deu in the OCR language box to combine them.' if installed else '')
    def health(self, key, state, text):
        status, _, _ = self.rows[key];path, source = helper_state(self.settings, key)
        if not source: return
        how = 'Chosen' if source == 'chosen' else 'Found'
        status.setText(f'<span style="color:#7bd88f">✓ Ready</span> — {text}<br><span style="color:#a8a8a8">{how}: {path}</span>' if state == 'ready' else f'<span style="color:#ff7b7b">✕ Cannot run</span> — {text}<br><span style="color:#a8a8a8">{how}: {path}</span>')
    def choose(self, key, name):
        path = QFileDialog.getOpenFileName(self, f'Select {name} from a trusted installation')[0]
        if path: self.settings.setValue(key, str(Path(path).resolve()));self.refresh()
    def reset(self, key):
        self.settings.remove(key);self.refresh()

    # --- About -----------------------------------------------------------------------
    def build_about(self, col):
        frame, box = theme.card();box.setSpacing(6);col.addWidget(frame)
        icon = QLabel();icon.setAlignment(Qt.AlignCenter);pm = QPixmap(str(Path(__file__).with_name('icon.png')))
        if not pm.isNull(): icon.setPixmap(pm.scaled(84, 84, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        box.addWidget(icon)
        for text, name in (('Open Tangerine', 'title'), (f'VERSION {engine.VERSION}  ·  {"WINDOWS" if os.name == "nt" else "LINUX"} DESKTOP TRIAL', 'muted'), ('Sintax Error Private Limited', ''),
                           ('Free to use. Open to make better.', 'muted'), ('GPL-3.0-only · Based on Satsuma by plyght (MIT).\nIndependent of Tangerine. Some features remain experimental.', 'muted')):
            label = theme.label(text, name, True);label.setAlignment(Qt.AlignCenter);box.addWidget(label)
        row = QHBoxLayout();row.addStretch(1)
        for text, url in (('Downloads / updates', WEBSITE + '?platform=desktop&version=' + engine.VERSION + '#desktop'), ('Privacy', WEBSITE + 'privacy.html'), ('Source code', 'https://github.com/sintaxerrorpvtltd/Open-Tangerine')):
            b = QPushButton(text);b.setProperty('link', True);b.setCursor(Qt.PointingHandCursor);b.clicked.connect(lambda _=False, u=url: QDesktopServices.openUrl(QUrl(u)));row.addWidget(b)
        row.addStretch(1);box.addLayout(row)

    def done(self, result):
        for check in self.checks: check.wait(10000)
        if self.controller: self.controller.refresh_menu()
        super().done(result)
