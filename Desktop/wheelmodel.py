"""Qt-free logic of the Shift/Alt/Ctrl wheel: which items to offer and how modifier keys map to modes."""
import math
from dataclasses import dataclass
from pathlib import Path
from engine import PDF_INPUTS, DOCX_INPUTS, IMAGE_INPUTS, OFFICE_INPUTS, MEDIA_INPUTS, AUDIO_INPUTS, TEXT_INPUTS, VIDEO_TARGETS, AUDIO_TARGETS, GIF_TARGETS

SLOTS = 12
MODES = ('convert', 'tools', 'actions')
MODE_TITLES = {'convert': 'Convert', 'tools': 'Tools', 'actions': 'Actions'}
MODE_KEYS = {'convert': 'Shift', 'tools': 'Alt', 'actions': 'Ctrl+Shift'}
SHORT = {'Files → PDF': 'PDF', 'Files → DOCX': 'DOCX', 'Combine → PDF': 'PDF', 'Combine → DOCX': 'DOCX', 'Image → PDF': 'PDF', 'OCR → Text': 'OCR', 'OCR → Searchable PDF': 'Search PDF', 'PDF → Text': 'Text', 'Split PDF': 'Split', 'Merge PDFs': 'Merge', 'Office → PDF': 'PDF', 'SRT → VTT': 'VTT', 'VTT → SRT': 'SRT', 'SHA-256': 'SHA-256', 'Image → DOCX': 'DOCX', 'PDF → PNG': 'PNG', 'PDF → JPEG': 'JPEG', 'PDF → DOCX': 'DOCX', 'Text → PDF': 'PDF', 'Text → PNG': 'PNG', 'Text → JPEG': 'JPEG', 'Text → SRT': 'SRT', 'Text → VTT': 'VTT', 'Subtitle → Text': 'Text'}
CAPTIONS = {'Files → PDF': 'Document', 'Files → DOCX': 'Word', 'PNG': 'Lossless', 'JPEG': 'Small', 'WEBP': 'Web', 'HEIC': 'Photos', 'TIFF': 'Archive', 'BMP': 'Bitmap', 'Image → PDF': 'Document', 'OCR → Text': 'Read text', 'OCR → Searchable PDF': 'Selectable text', 'PDF → Text': 'Extract', 'Split PDF': 'Pages', 'Merge PDFs': 'Combine',
            'Office → PDF': 'Document', 'SRT → VTT': 'Subtitles', 'VTT → SRT': 'Subtitles', 'SHA-256': 'Checksum', 'MP4': 'Video', 'WEBM': 'Video', 'MP3': 'Audio', 'WAV': 'Audio', 'FLAC': 'Lossless', 'OGG': 'Audio',
            'AVIF': 'Modern', 'Image → DOCX': 'Word', 'PDF → PNG': 'Pages', 'PDF → JPEG': 'Pages', 'PDF → DOCX': 'Word', 'Text → PDF': 'Document', 'Text → PNG': 'Picture', 'Text → JPEG': 'Picture', 'Text → SRT': 'Subtitles', 'Text → VTT': 'Subtitles', 'Subtitle → Text': 'Plain text',
            'GIF': 'Animated', 'MOV': 'QuickTime', 'MKV': 'Matroska', 'AVI': 'Classic', 'WMV': 'Windows', 'M4A': 'Apple audio', 'OPUS': 'Small', 'AIFF': 'Lossless', 'WMA': 'Windows'}
TITLES = {'Combine → PDF': 'Combining into one PDF', 'Combine → DOCX': 'Combining into one Word file', 'Files → PDF': 'Creating PDFs', 'Files → DOCX': 'Creating Word files', 'OCR → Text': 'Reading text', 'OCR → Searchable PDF': 'Making searchable PDF', 'PDF → Text': 'Extracting text', 'Split PDF': 'Splitting PDF', 'Merge PDFs': 'Merging PDFs', 'SHA-256': 'Computing SHA-256', 'Image → DOCX': 'Creating Word file', 'PDF → DOCX': 'Creating Word file', 'PDF → PNG': 'Rendering pages', 'PDF → JPEG': 'Rendering pages', 'Text → PDF': 'Creating PDF', 'Subtitle → Text': 'Extracting text'}
DONE = {'Combine → PDF': 'Combined PDF saved', 'Combine → DOCX': 'Combined Word file saved', 'Files → PDF': 'PDFs created', 'Files → DOCX': 'Word files created', 'OCR → Text': 'Text recognized', 'OCR → Searchable PDF': 'Searchable PDF saved', 'PDF → Text': 'Text extracted', 'Split PDF': 'PDF split', 'Merge PDFs': 'PDFs merged', 'SHA-256': 'Checksum saved', 'Image → DOCX': 'Word file created', 'PDF → DOCX': 'Word file created', 'PDF → PNG': 'Pages saved', 'PDF → JPEG': 'Pages saved', 'Text → PDF': 'PDF created', 'Subtitle → Text': 'Text extracted'}
FILE_ACTIONS = (('reveal', 'Reveal', 'In Explorer'), ('copy_files', 'Copy files', 'To clipboard'), ('copy_paths', 'Copy paths', 'As text'), ('duplicate', 'Duplicate', 'Next to it'), ('hash', 'SHA-256', 'To clipboard'))
DEFAULT_TARGETS = ['PNG', 'JPEG', 'WEBP', 'HEIC', 'Image → PDF', 'OCR → Text', 'TIFF', 'SHA-256']
EMPTY = {'convert': 'No conversions for this selection', 'tools': 'No tools for this selection', 'actions': 'No file actions'}
PROMPT = {'convert': 'Release on a format', 'tools': 'Release on a tool', 'actions': 'Release on an action'}
# With several files these tiles split in two while hovered: the inner half converts each file, the outer half makes one file.
COMBINE_FOR = {'Image → PDF': 'Combine → PDF', 'Text → PDF': 'Combine → PDF', 'Office → PDF': 'Combine → PDF', 'Files → PDF': 'Combine → PDF',
               'Image → DOCX': 'Combine → DOCX', 'PDF → DOCX': 'Combine → DOCX', 'Files → DOCX': 'Combine → DOCX'}

def short_label(target): return SHORT.get(target, target)

def combine_target(target, paths):
    """The one-file version of `target` for this selection, or None when there is nothing to combine."""
    return COMBINE_FOR.get(target) if len(paths) > 1 else None

@dataclass(frozen=True)
class Item:
    kind: str       # convert, tool, action
    key: str
    label: str
    caption: str = ''

def targets_for(paths, limit=SLOTS):
    """Conversions that make sense for every dropped file, in wheel order."""
    if not paths: return []
    common = None
    for raw in paths:
        s = Path(raw).suffix.lower()
        if s in IMAGE_INPUTS: t = ['PNG', 'JPEG', 'WEBP', 'HEIC', 'AVIF', 'TIFF', 'BMP', 'Image → PDF', 'Image → DOCX', 'OCR → Text', 'OCR → Searchable PDF']
        elif s == '.pdf': t = ['PDF → Text', 'PDF → PNG', 'PDF → JPEG', 'PDF → DOCX', 'OCR → Text', 'OCR → Searchable PDF', 'Split PDF', 'Merge PDFs']
        elif s in OFFICE_INPUTS: t = ['Office → PDF']
        elif s == '.gif': t = list(GIF_TARGETS)
        elif s in AUDIO_INPUTS: t = list(AUDIO_TARGETS)
        elif s in MEDIA_INPUTS: t = list(VIDEO_TARGETS)
        elif s in TEXT_INPUTS: t = ['Text → PDF', 'Text → PNG', 'Text → JPEG', 'Text → SRT', 'Text → VTT']
        elif s == '.srt': t = ['SRT → VTT', 'Subtitle → Text']
        elif s == '.vtt': t = ['VTT → SRT', 'Subtitle → Text']
        else: t = []
        t = t + ['SHA-256']
        common = t if common is None else [x for x in common if x in t]
    if len(paths) < 2 and common: common = [x for x in common if x != 'Merge PDFs']
    # A mix of kinds (say photos, a Word file and a PDF) has no shared PDF or DOCX conversion, so offer the per-file route.
    suffixes = {Path(raw).suffix.lower() for raw in paths}
    if len(paths) > 1 and common is not None and not any(t in COMBINE_FOR for t in common) and suffixes != {'.pdf'}:
        common = [t for t, kinds in (('Files → PDF', PDF_INPUTS), ('Files → DOCX', DOCX_INPUTS)) if suffixes <= kinds] + common
    if limit and common and 'SHA-256' in common and len(common) > limit: common = common[:limit - 1] + ['SHA-256']
    return common[:limit] if limit else common

def items_for(mode, paths):
    if not paths: return []
    if mode == 'tools':
        import toolops          # only the Tools mode needs the editing tools
        return [Item('tool', t.id, t.label, t.caption) for t in toolops.tools_for(paths)][:SLOTS]
    if mode == 'actions': return [Item('action', k, label, caption) for k, label, caption in FILE_ACTIONS]
    return [Item('convert', t, short_label(t), CAPTIONS.get(t, '')) for t in targets_for(paths)]

def default_items():
    return [Item('convert', t, short_label(t), CAPTIONS.get(t, '')) for t in DEFAULT_TARGETS]

def mode_of(shift, alt, ctrl):
    """Ctrl+Shift = file actions, Alt = tools, Shift = convert. Ctrl alone is left to Explorer (it means copy)."""
    if ctrl and shift: return 'actions'
    if alt: return 'tools'
    if shift: return 'convert'
    return None

@dataclass
class Sample:
    pos: tuple
    left: bool
    shift: bool
    source_ok: bool
    alt: bool = False
    ctrl: bool = False

class DragDetector:
    """Pure state machine: (button, modifiers, position) samples in, ('engage'|'mode'|'release', mode) events out.
    Once the wheel is up it stays until the button is released, even if the keys are let go; that is what lets the
    on-screen tabs replace the keyboard."""
    THRESHOLD = 8
    def __init__(self): self.reset()
    def reset(self): self.state = 'idle';self.start = (0, 0);self.engaged = False;self.mode = None
    def update(self, s):
        if self.state == 'idle':
            if s.left: self.start = s.pos;self.state = 'pressed' if s.source_ok else 'ignored'
            return None
        if not s.left:
            was = self.engaged;self.reset()
            return ('release', None) if was else None
        if self.state == 'pressed' and math.dist(s.pos, self.start) >= self.THRESHOLD: self.state = 'dragging'
        if self.state == 'dragging':
            m = mode_of(s.shift, s.alt, s.ctrl)
            if m and not self.engaged: self.engaged = True;self.mode = m;return ('engage', m)
            if m and m != self.mode: self.mode = m;return ('mode', m)
        return None
