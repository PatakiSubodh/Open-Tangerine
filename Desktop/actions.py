"""File actions of the Ctrl+Shift wheel (the Windows counterpart of the Mac Control wheel):
Reveal, Copy files, Copy paths, Duplicate and SHA-256. Nothing here deletes, moves or overwrites a file."""
import hashlib, os, shutil, struct, subprocess, sys
from pathlib import Path
from PySide6.QtCore import QMimeData, QThread, QUrl, Signal
from PySide6.QtWidgets import QApplication
import engine

def plural(n, word): return f'{n} {word}' + ('' if n == 1 else 's')

def reveal(paths):
    """Open Explorer with the files selected, one window per containing folder (at most five)."""
    folders = {}
    for p in paths: folders.setdefault(str(Path(p).parent), []).append(str(p))
    for folder, files in list(folders.items())[:5]:
        if not select_in_explorer(folder, files): subprocess.Popen(['explorer.exe', f'/select,{files[0]}'])
    return len(paths)

def select_in_explorer(folder, files):
    if sys.platform != 'win32': return False
    import ctypes
    from ctypes import wintypes
    shell32, ole32 = ctypes.windll.shell32, ctypes.windll.ole32
    parse = shell32.SHParseDisplayName;parse.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), wintypes.ULONG, ctypes.POINTER(wintypes.ULONG)];parse.restype = ctypes.c_long
    select = shell32.SHOpenFolderAndSelectItems;select.argtypes = [ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p), wintypes.DWORD];select.restype = ctypes.c_long
    free = ole32.CoTaskMemFree;free.argtypes = [ctypes.c_void_p]
    pidls = []
    try:
        parent = ctypes.c_void_p()
        if parse(folder, None, ctypes.byref(parent), 0, None) != 0: return False
        pidls.append(parent)
        children = []
        for f in files:
            child = ctypes.c_void_p()
            if parse(f, None, ctypes.byref(child), 0, None) == 0: pidls.append(child);children.append(child.value)
        if not children: return False
        array = (ctypes.c_void_p * len(children))(*children)
        return select(parent, len(children), array, 0) == 0
    except OSError: return False
    finally:
        for pidl in pidls:
            if pidl.value: free(pidl)

def copy_files(paths):
    """Put the files on the clipboard so Ctrl+V in Explorer copies them (never moves)."""
    mime = QMimeData();mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    mime.setData('application/x-qt-windows-mime;value="Preferred DropEffect"', struct.pack('<I', 1))
    QApplication.clipboard().setMimeData(mime);return len(paths)

def copy_paths(paths):
    QApplication.clipboard().setText('\n'.join(str(Path(p)) for p in paths));return len(paths)

def duplicate_one(source):
    """Copy next to the original as 'name - copy.ext', 'name - copy 2.ext'... created exclusively, so nothing is overwritten."""
    p = engine.source_file(source)
    for n in range(1, 10001):
        target = p.with_name(f'{p.stem} - copy' + ('' if n == 1 else f' {n}') + p.suffix)
        try: out = target.open('xb')
        except FileExistsError: continue
        with out, p.open('rb') as src: shutil.copyfileobj(src, out, 1024 * 1024)
        shutil.copystat(p, target);return target
    raise engine.ConversionError('Too many existing copies; rename some first.')

def hash_report(paths):
    lines = []
    for raw in paths:
        p = engine.source_file(raw);h = hashlib.sha256()
        with p.open('rb') as f:
            for block in iter(lambda: f.read(1024 * 1024), b''): h.update(block)
        lines.append(f'{h.hexdigest()}  {p.name}')
    return '\n'.join(lines)

class ActionWorker(QThread):
    """Duplicate and hashing touch the disk, so they run off the interface thread."""
    done = Signal(str, str, str, str)       # kind (ok/error), title, detail, text for the clipboard
    def __init__(self, key, paths): super().__init__();self.key = key;self.paths = list(paths)
    def run(self):
        try:
            if self.key == 'duplicate':
                made = [duplicate_one(p) for p in self.paths];self.done.emit('ok', f'Duplicated {plural(len(made), "file")}', made[0].name if len(made) == 1 else 'Saved next to the originals', '')
            else:
                report = hash_report(self.paths);first = report.splitlines()[0].split()[0]
                self.done.emit('ok', 'SHA-256 copied', first[:20] + '…' if len(self.paths) == 1 else f'{plural(len(self.paths), "checksum")} on the clipboard', report)
        except Exception as e: self.done.emit('error', "Couldn't finish", str(e)[:300] or type(e).__name__, '')
