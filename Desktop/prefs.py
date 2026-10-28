"""Saved preferences read by the settings window, the main window, the tool windows and the drag wheel.

All of them share one QSettings object, so a change made in the settings window applies to the wheel on its next drag with no restart."""
import json
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

CARD_POSITIONS = (('top-left', 'Top left'), ('top-center', 'Top centre'), ('top-right', 'Top right'), ('bottom-left', 'Bottom left'), ('bottom-right', 'Bottom right'))
def card_position(settings):
    """Screen corner of the progress card shown for drag-wheel work."""
    value = settings.value('card/position', 'top-center')
    return value if value in dict(CARD_POSITIONS) else 'top-center'

# --- applications whose drags never open the wheel ------------------------------------------------
def image_name(image):
    """Lower-case file name of a program path ("C:\\Apps\\CorelDRAW.exe" -> "coreldraw.exe"), or ''."""
    return str(image or '').replace('\\', '/').rsplit('/', 1)[-1].strip().lower()

def excluded(settings):
    """{file name: display name}, kept as JSON so the registry holds one plain string."""
    try: data = json.loads(settings.value('wheel/excluded', '') or '{}')
    except (TypeError, ValueError): return {}
    return {image_name(k): str(v) for k, v in data.items() if image_name(k)} if isinstance(data, dict) else {}

def excluded_names(settings): return frozenset(excluded(settings))

def save_excluded(settings, mapping): settings.setValue('wheel/excluded', json.dumps(dict(sorted(mapping.items()))))

def add_excluded(settings, path):
    """Exclude the program at `path`. Returns its file name, or None if it is not an .exe."""
    name = image_name(path)
    if not name.endswith('.exe'): return None
    mapping = excluded(settings);mapping[name] = Path(str(path).replace('\\', '/')).stem;save_excluded(settings, mapping);return name

def remove_excluded(settings, name):
    mapping = excluded(settings);mapping.pop(image_name(name), None);save_excluded(settings, mapping)

def is_excluded(image, names): return bool(image_name(image)) and image_name(image) in names
