"""Saved preferences read by the settings window and the main window, which share one QSettings object."""
from pathlib import Path

OUTPUT_MODES = (('beside', 'Next to the original'), ('downloads', 'Downloads'), ('desktop', 'Desktop'), ('custom', 'A folder I choose'))

def known_folder(name):
    from PySide6.QtCore import QStandardPaths
    where = {'downloads': QStandardPaths.DownloadLocation, 'desktop': QStandardPaths.DesktopLocation}[name]
    return QStandardPaths.writableLocation(where)

def output_mode(settings):
    mode = settings.value('output/mode', 'beside')
    return mode if mode in dict(OUTPUT_MODES) else 'beside'

def custom_folder(settings): return str(settings.value('output/folder', '') or '')

def output_folder(settings):
    """Folder results go to, or '' for "next to each original". A folder that no longer exists falls back to next to the original."""
    mode = output_mode(settings)
    folder = '' if mode == 'beside' else custom_folder(settings) if mode == 'custom' else known_folder(mode)
    return str(Path(folder)) if folder and Path(folder).is_absolute() and Path(folder).is_dir() else ''

def reveal_results(settings): return settings.value('output/reveal', False, type=bool)

WHEEL_THEMES = (('light', 'Light (frosted glass)'), ('dark', 'Dark (charcoal and Tangerine)'))
def wheel_theme(settings):
    """Look of the drag wheel; saved, so it stays until changed in Settings."""
    value = settings.value('wheel/theme', 'light')
    return value if value in dict(WHEEL_THEMES) else 'light'

