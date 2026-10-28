"""Drag wheel for Windows: hold Shift (convert), Alt (tools) or Ctrl+Shift (file actions) while dragging files.

Detection polls the left mouse button, the Shift/Alt/Ctrl modifier state and the class of the window under
the cursor every few milliseconds. It installs no hooks and reads no keystrokes. The wheel is an ordinary
drop target, so Windows hands it the real file paths when the drag is released."""
import os, sys
from pathlib import Path
from PySide6.QtCore import QObject, QPoint, QTimer, Signal
from PySide6.QtGui import QCursor, QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication, QFileDialog, QMenu, QSystemTrayIcon
from engine import IMAGE_OUTPUTS, MEDIA_OUTPUTS, COMBINED_TARGETS
from batch import Batch
import actions, prefs, toolops
from wheelmodel import *                      # noqa: F401,F403  (re-exported: items, modes, DragDetector, Sample)
from wheelmodel import TITLES, DONE, MODES, MODE_TITLES, MODE_KEYS, Sample, DragDetector, short_label, targets_for, items_for
from wheel_ui import Theme, WheelOverlay, Notch      # noqa: F401

SOURCE_CLASSES = {'CabinetWClass', 'ExploreWClass', 'Progman', 'WorkerW', '#32770'}  # Explorer, desktop, file dialogs

class WindowsSampler:
    """Reads physical input state through user32; no hooks and no key contents."""
    VK_SHIFT, VK_CONTROL, VK_MENU = 0x10, 0x11, 0x12
    def __init__(self, any_app=False, excluded=None):
        import ctypes
        from ctypes import wintypes
        self.ct = ctypes;self.wt = wintypes;self.any_app = any_app;self.excluded = excluded or (lambda: frozenset())       # excluded() -> file names of programs that must not start the wheel
        u = self.user32 = ctypes.windll.user32
        class POINT(ctypes.Structure): _fields_ = [('x', ctypes.c_long), ('y', ctypes.c_long)]
        self.POINT = POINT
        u.GetAsyncKeyState.argtypes = [ctypes.c_int];u.GetAsyncKeyState.restype = ctypes.c_short
        u.WindowFromPoint.argtypes = [POINT];u.WindowFromPoint.restype = wintypes.HWND
        u.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT];u.GetAncestor.restype = wintypes.HWND
        u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        k = self.kernel32 = ctypes.windll.kernel32
        k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD];k.OpenProcess.restype = wintypes.HANDLE
        k.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)];k.QueryFullProcessImageNameW.restype = wintypes.BOOL
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        self.button = 0x02 if u.GetSystemMetrics(23) else 0x01  # SM_SWAPBUTTON: physical keys follow the primary button
    def down(self, vk): return bool(self.user32.GetAsyncKeyState(vk) & 0x8000)
    def source_ok(self, pt):
        u = self.user32;hwnd = u.WindowFromPoint(pt)
        if not hwnd: return False
        root = u.GetAncestor(hwnd, 2) or hwnd
        pid = self.wt.DWORD();u.GetWindowThreadProcessId(root, self.ct.byref(pid))
        buf = self.ct.create_unicode_buffer(256);u.GetClassNameW(root, buf, 256)
        return self.allowed(pid.value, buf.value, self.image_of(pid.value))
    def image_of(self, pid):
        """Full path of the program that owns a process, or '' (for example a window of an elevated program we may not open)."""
        handle = self.kernel32.OpenProcess(0x1000, False, pid)         # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle: return ''
        try:
            buf = self.ct.create_unicode_buffer(1024);size = self.wt.DWORD(1024)
            return buf.value if self.kernel32.QueryFullProcessImageNameW(handle, 0, buf, self.ct.byref(size)) else ''
        finally: self.kernel32.CloseHandle(handle)
    def allowed(self, pid, window_class, image):
        """May a drag that starts in this window open the wheel? Never our own windows, never an excluded program."""
        if pid == os.getpid() or prefs.is_excluded(image, self.excluded()): return False
        return True if self.any_app else window_class in SOURCE_CLASSES
    def __call__(self, previously_down):
        pt = self.POINT();self.user32.GetCursorPos(self.ct.byref(pt))
        left = self.down(self.button)
        # Window lookup only on the press edge; the answer is reused for the whole drag.
        ok = self.source_ok(pt) if left and not previously_down else True
        return Sample((pt.x, pt.y), left, self.down(self.VK_SHIFT), ok, self.down(self.VK_MENU), self.down(self.VK_CONTROL))

class DragWatcher(QObject):
    engaged = Signal(QPoint, str)
    mode_changed = Signal(str)
    released = Signal()
    def __init__(self, sampler=None, interval=25, parent=None):
        super().__init__(parent);self.sampler = sampler or WindowsSampler();self.detector = DragDetector();self.was_down = False
        self.timer = QTimer(self);self.timer.setInterval(interval);self.timer.timeout.connect(self.tick)
    def start(self): self.timer.start()
    def stop(self): self.timer.stop();self.detector.reset();self.was_down = False
    def set_any_app(self, value):
        if hasattr(self.sampler, 'any_app'): self.sampler.any_app = bool(value)
    def tick(self):
        s = self.sampler(self.was_down);self.was_down = s.left
        event = self.detector.update(s)
        if not event: return
        name, mode = event
        if name == 'engage': self.engaged.emit(QCursor.pos(), mode)
        elif name == 'mode': self.mode_changed.emit(mode)
        else: self.released.emit()

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
def startup_command():
    """Command line Windows runs at login: straight into the tray, no window."""
    if getattr(sys, 'frozen', False): return f'"{sys.executable}" --background'
    exe = Path(sys.executable);exe = exe.with_name('pythonw.exe') if exe.with_name('pythonw.exe').exists() else exe
    return f'"{exe}" "{Path(__file__).with_name("app.py")}" --background'
def startup_enabled():
    if os.name != 'nt': return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k: return winreg.QueryValueEx(k, 'OpenTangerine')[0] == startup_command()
    except OSError: return False
def set_startup(on):
    if os.name != 'nt': return
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on: winreg.SetValueEx(k, 'OpenTangerine', 0, winreg.REG_SZ, startup_command())
        else:
            try: winreg.DeleteValue(k, 'OpenTangerine')
            except OSError: pass

class WheelController(QObject):
    """Owns the watcher, wheel, notch, system-tray icon, tool windows and the work started from the wheel."""
    quit_requested = Signal()
    show_window = Signal()
    def __init__(self, settings, icon=None, parent=None):
        super().__init__(parent);self.settings = settings;self.batch = None;self.statuses = [];self.tool_windows = [];self.action_worker = None
        self.overlay = WheelOverlay();self.notch = Notch(settings);self.watcher = DragWatcher(WindowsSampler(excluded=lambda: prefs.excluded_names(self.settings)), parent=self)
        self.watcher.engaged.connect(self.engage);self.watcher.mode_changed.connect(self.overlay.set_mode);self.watcher.released.connect(self.overlay.dismiss_soon)
        self.overlay.chosen.connect(self.dispatch)
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(icon or QIcon(), self);self.tray.setToolTip('Open Tangerine · drag wheel');menu = QMenu()
            menu.addAction('Open Open Tangerine').triggered.connect(self.show_window.emit);menu.addSeparator()
            for mode, label in (('convert', 'Convert files…'), ('tools', 'Tools for files…'), ('actions', 'File actions…')): menu.addAction(label).triggered.connect(lambda _=False, m=mode: self.pick_files(m))
            menu.addSeparator()
            self.enable_action = menu.addAction('Drag wheel (Shift, Alt, Ctrl+Shift)');self.enable_action.setCheckable(True);self.enable_action.toggled.connect(self.set_enabled)
            self.any_action = menu.addAction('Also trigger from other apps');self.any_action.setCheckable(True);self.any_action.toggled.connect(self.set_any_app)
            if os.name == 'nt': self.startup_action = menu.addAction('Start with Windows');self.startup_action.setCheckable(True);self.startup_action.setChecked(startup_enabled());self.startup_action.toggled.connect(set_startup)
            menu.addSeparator();menu.addAction('Quit').triggered.connect(self.quit_requested.emit)
            self.tray.setContextMenu(menu);self.tray.activated.connect(lambda r: self.show_window.emit() if r == QSystemTrayIcon.Trigger else None);self._menu = menu
    @property
    def enabled(self): return self.settings.value('wheel/enabled', False, type=bool)        # opt-in, as in 0.2.2
    def start(self):
        if self.tray:
            self.refresh_menu();self.tray.show()
        self.watcher.set_any_app(self.settings.value('wheel/any_app', False, type=bool))
        if self.enabled: self.watcher.start()
    def refresh_menu(self):
        """Make the tray menu's checkmarks match the saved settings (they can change in the settings window)."""
        if not self.tray: return
        states = [(self.enable_action, self.enabled), (self.any_action, self.settings.value('wheel/any_app', False, type=bool))]
        if os.name == 'nt': states.append((self.startup_action, startup_enabled()))
        for action, on in states: action.blockSignals(True);action.setChecked(on);action.blockSignals(False)
    def set_enabled(self, on):
        self.settings.setValue('wheel/enabled', bool(on))
        if on: self.watcher.start()
        else: self.watcher.stop();self.overlay.dismiss()
        if self.tray and self.enable_action.isChecked() != bool(on): self.enable_action.setChecked(bool(on))
    def set_any_app(self, on): self.settings.setValue('wheel/any_app', bool(on));self.watcher.set_any_app(on)
    # --- entry points ---------------------------------------------------------------
    def engage(self, pos, mode): self.overlay.look = prefs.wheel_theme(self.settings);self.overlay.present(pos, mode)
    def pick_files(self, mode='convert', paths=None):
        """Menu fallback for people whose drag does not trigger the wheel: choose files, then click a tile."""
        if not paths: paths = QFileDialog.getOpenFileNames(None, 'Choose files')[0]
        if not paths: return
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        self.overlay.look = prefs.wheel_theme(self.settings);self.overlay.present(screen.availableGeometry().center(), mode, [str(Path(p)) for p in paths], interactive=True)
    def dispatch(self, paths, kind, key):
        if kind == 'convert': self.convert(paths, key)
        elif kind == 'tool': self.open_tool(key, paths)
        else: self.run_action(key, paths)
    # --- tools ----------------------------------------------------------------------
    def open_tool(self, key, paths):
        import toolwin
        tool = toolops.TOOLS.get(key)
        if tool is None: self.notch.show_message('Unknown tool', 'error', seconds=4);return
        window = toolwin.ToolWindow(tool, paths, self.settings);self.tool_windows.append(window)
        window.finished.connect(lambda _=0, w=window: self.tool_windows.remove(w) if w in self.tool_windows else None)
        window.show();window.raise_();window.activateWindow()
    # --- file actions ---------------------------------------------------------------
    def run_action(self, key, paths):
        noun = actions.plural(len(paths), 'file')
        if key == 'reveal': actions.reveal(paths);self.notch.show_message('Showing in Explorer', 'ok', seconds=2.2, detail=noun)
        elif key == 'copy_files': actions.copy_files(paths);self.notch.show_message('Copied ' + noun, 'ok', seconds=3, detail='Paste with Ctrl+V in any folder')
        elif key == 'copy_paths': actions.copy_paths(paths);self.notch.show_message('Copied ' + actions.plural(len(paths), 'path'), 'ok', seconds=3, detail='Ready to paste as text')
        else:
            if self.action_worker and self.action_worker.isRunning(): self.notch.show_message('Still busy with the previous action', 'error', seconds=3);return
            self.notch.show_message('Duplicating…' if key == 'duplicate' else 'Computing SHA-256…', 'info', detail=noun)
            self.action_worker = actions.ActionWorker(key, paths);self.action_worker.done.connect(self.action_done);self.action_worker.start()
    def action_done(self, kind, title, detail, text):
        if text: QApplication.clipboard().setText(text)
        self.notch.show_message(title, kind, seconds=3.2 if kind == 'ok' else 9, detail=detail)
    # --- conversions ----------------------------------------------------------------
    def convert(self, paths, target):
        if self.batch and self.batch.isRunning(): self.notch.show_message('Still busy with the previous drop', 'error', seconds=3);return
        s = self.settings
        options = {'output': prefs.output_folder(s), 'width': 0, 'rotation': 0, 'ffmpeg': s.value('ffmpeg', ''), 'tesseract': s.value('tesseract', ''), 'soffice': s.value('soffice', ''), 'ocr_lang': s.value('ocr_lang', 'eng')}
        self.statuses = [];self.outputs = [];self.total = 1 if target in COMBINED_TARGETS else len(paths);self.noun = f'{len(paths)} file{"s" if len(paths) != 1 else ""}';self.target = target
        self.name = short_label(target) if target not in IMAGE_OUTPUTS and target not in MEDIA_OUTPUTS else target
        self.notch.show_message(TITLES.get(target, 'Converting to ' + self.name), 'info', detail=self.noun, fraction=0)
        self.batch = Batch(list(paths), target, options);self.batch.result.connect(self.result);self.batch.progress.connect(self.advance);self.batch.finished.connect(self.finished);self.batch.start()
    def advance(self, n, total): self.notch.show_message(TITLES.get(self.target, 'Converting to ' + self.name), 'info', detail=f'{n} of {total} done · {self.noun}', fraction=n / total)
    def result(self, index, status, outputs): self.statuses.append(status);self.outputs.extend(outputs)
    def finished(self):
        failed = [x for x in self.statuses if x != 'Done'];done = len(self.statuses) - len(failed)
        folder = str(Path(self.outputs[-1]).parent) if self.outputs else None
        where = 'saved to ' + Path(folder).name if prefs.output_folder(self.settings) and folder else 'saved next to the originals'
        if folder and prefs.reveal_results(self.settings): actions.reveal(self.outputs[-1:])
        if not failed and done: self.notch.show_message(DONE.get(self.target, 'Converted to ' + self.name), 'ok', folder=folder, seconds=3.2, detail=f'{self.noun} · {where}')
        elif done: self.notch.show_message(f'{done} converted · {len(failed)} failed', 'error', folder=folder, seconds=9, detail=failed[0])
        else: self.notch.show_message("Couldn't convert", 'error', seconds=9, detail=failed[0] if failed else 'Nothing was converted')
    def shutdown(self):
        self.watcher.stop();self.overlay.dismiss();self.notch.hide()
        for w in list(self.tool_windows): w.close()
        if self.tray: self.tray.hide()
        for worker in (self.batch, self.action_worker):
            if worker and worker.isRunning():
                if hasattr(worker, 'cancel'): worker.cancel.set()
                worker.wait(5000)

def supported(): return sys.platform == 'win32'
