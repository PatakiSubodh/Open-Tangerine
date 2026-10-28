# PyInstaller: GUI entry point without a console, plus a piped conversion worker.
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], ['PySide6.QtSvg', 'docops', 'toolops', 'toolwin', 'mediaui']
for package in ('pypdf', 'pillow_heif', 'pypdfium2'):
    d, b, h = collect_all(package)
    datas += d; binaries += b; hiddenimports += h
a = Analysis(['app.py'], pathex=[], binaries=binaries,
             datas=[('icon.png', '.')] + datas, hiddenimports=hiddenimports)
pyz = PYZ(a.pure)
gui = EXE(pyz, a.scripts, [], exclude_binaries=True,
          name='OpenTangerine', console=False, icon='build/icon.ico')
worker = EXE(pyz, a.scripts, [], exclude_binaries=True,
             name='OpenTangerineWorker', console=True, icon='build/icon.ico')
COLLECT(gui, worker, a.binaries, a.datas, name='OpenTangerine')
