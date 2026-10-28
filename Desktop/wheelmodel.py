"""Which conversions fit a selection of files. The main window offers only these, and its glass wheel shows the first few."""
from pathlib import Path
from engine import IMAGE_INPUTS, OFFICE_INPUTS, MEDIA_INPUTS, AUDIO_INPUTS, TEXT_INPUTS, VIDEO_TARGETS, AUDIO_TARGETS, GIF_TARGETS

SLOTS = 12                     # most targets a wheel shows at once

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
    if limit and common and 'SHA-256' in common and len(common) > limit: common = common[:limit - 1] + ['SHA-256']
    return common[:limit] if limit else common
