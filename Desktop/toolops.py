"""Editing tools behind the Tools wheel (Windows/Linux counterpart of the Mac tool windows).

Every tool runs inside the same isolated worker as conversions, so the input, pixel, page and output limits
and the never-overwrite publishing rules apply unchanged. Parameters arrive as JSON and are validated here."""
from __future__ import annotations
import math, os, re, shutil, tempfile, time
from dataclasses import dataclass, field
from pathlib import Path
import engine, photoadjust
from engine import ConversionError, MAX_PIXELS, MAX_OUTPUT, IMAGE_INPUTS, MEDIA_INPUTS, publish, open_image, read_pdf, tool_path, run_external

VIDEO_EXT = {'.mp4', '.mov', '.m4v', '.mkv', '.webm'}
AUDIO_EXT = {'.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac'}
IMAGE_SAME_EXT = {'.png': 'png', '.jpg': 'jpg', '.jpeg': 'jpg', '.webp': 'webp', '.tif': 'tiff', '.tiff': 'tiff', '.bmp': 'bmp', '.heic': 'heic', '.heif': 'heic'}
IMAGE_FORMAT = {'png': 'PNG', 'jpg': 'JPEG', 'webp': 'WEBP', 'tiff': 'TIFF', 'bmp': 'BMP', 'heic': 'HEIF'}
AUDIO_OUT = {'.mp3': ('mp3', ['-c:a', 'libmp3lame', '-q:a', '2']), '.wav': ('wav', ['-c:a', 'pcm_s16le']), '.flac': ('flac', ['-c:a', 'flac']),
             '.ogg': ('ogg', ['-c:a', 'libvorbis', '-q:a', '5']), '.m4a': ('ipod', ['-c:a', 'aac', '-b:a', '192k']), '.aac': ('adts', ['-c:a', 'aac', '-b:a', '192k'])}
VIDEO_ENC = ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '21', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k', '-movflags', '+faststart']
TOOL_DEADLINE = 1500

def needs_ffmpeg(tool, paths):
    """Compress and metadata only need FFmpeg for audio and video files."""
    return tool.ffmpeg or (tool.id in ('compress', 'metadata') and any(category(p) in ('video', 'audio') for p in paths))

def category(path):
    s = Path(path).suffix.lower()
    if s in IMAGE_INPUTS: return 'image'
    if s in VIDEO_EXT: return 'video'
    if s in AUDIO_EXT: return 'audio'
    if s == '.pdf': return 'pdf'
    return None

@dataclass
class Field:
    """Declarative option, rendered as a form row by the tool window."""
    key: str
    label: str
    kind: str                      # int, float, choice, bool, color, text
    default: object = None
    lo: float = 0
    hi: float = 100
    options: tuple = ()            # for choice: ((value, label), ...)
    suffix: str = ''
    hint: str = ''
    when: tuple = ()               # (other_key, value or tuple of values): only shown/used then
    group: str = ''                # heading the row sits under; a float with a group is shown as a slider

@dataclass
class Tool:
    id: str
    title: str
    progress: str
    label: str
    caption: str
    categories: frozenset
    arity: str = 'single'          # single, multiple (two or more), any
    combined: bool = False         # one job over all files (merge, join, collage, PDF from images)
    ffmpeg: bool = False
    ui: str = ''                   # hint for a special panel: crop, redact, pages, order, preview
    fields: tuple = ()
    run: object = None

TOOLS = {}

def register(**kw):
    def wrap(fn):
        kw.setdefault('categories', frozenset())
        TOOLS[kw['id']] = Tool(run=fn, **{**kw, 'categories': frozenset(kw['categories'])})
        return fn
    return wrap

def tools_for(paths):
    """Tools that apply to every selected file, in wheel order."""
    kinds = {category(p) for p in paths}
    if not paths or None in kinds or len(kinds) != 1: return []
    kind = kinds.pop();n = len(paths)
    return [t for t in TOOLS.values() if kind in t.categories and (n == 1 if t.arity == 'single' else n >= 2 if t.arity == 'multiple' else True)]

# ---------------------------------------------------------------------------------------------- parameters
class P:
    def __init__(self, raw): self.d = raw if isinstance(raw, dict) else {}
    def num(self, key, lo, hi, default, integer=False):
        try: v = float(self.d.get(key, default))
        except (TypeError, ValueError): raise ConversionError(f'Invalid value for {key}.')
        if not math.isfinite(v) or not lo <= v <= hi: raise ConversionError(f'{key} must be between {lo} and {hi}.')
        return int(round(v)) if integer else v
    def choice(self, key, options, default):
        v = self.d.get(key, default)
        if v not in options: raise ConversionError(f'Invalid choice for {key}.')
        return v
    def flag(self, key, default=False): return bool(self.d.get(key, default))
    def color(self, key, default):
        v = self.d.get(key, default)
        if not isinstance(v, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', v): raise ConversionError('Colours must look like #rrggbb.')
        return v
    def text(self, key, default='', maxlen=200):
        v = self.d.get(key, default)
        if not isinstance(v, str) or len(v) > maxlen: raise ConversionError(f'{key} is too long.')
        return v
    def rects(self, key, maxn=50):
        v = self.d.get(key, [])
        if not isinstance(v, list) or not 1 <= len(v) <= maxn: raise ConversionError('Select at least one area.')
        out = []
        for r in v:
            try: x, y, w, h = (float(t) for t in r)
            except (TypeError, ValueError): raise ConversionError('Invalid area.')
            if not all(math.isfinite(t) for t in (x, y, w, h)) or x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > 1.0001 or y + h > 1.0001: raise ConversionError('The selected area is outside the picture.')
            out.append((x, y, min(w, 1 - x), min(h, 1 - y)))
        return out

    def time_ranges(self, key, maxn=50, open_end=False):
        """[(start, end)] in seconds. With open_end, an end of 0 means until the end of the file (returned as None)."""
        v = self.d.get(key, [])
        if not isinstance(v, list) or not 1 <= len(v) <= maxn: raise ConversionError('Add at least one time range.')
        out = []
        for r in v:
            try: a, b = (float(t) for t in r)
            except (TypeError, ValueError): raise ConversionError('Invalid time range.')
            if not (math.isfinite(a) and math.isfinite(b)) or a < 0 or b < 0 or a > 86400 or b > 86400: raise ConversionError('Times must be between 0 and 86400 seconds.')
            if open_end and b == 0: out.append((a, None));continue
            if b <= a: raise ConversionError('Each range must end after it starts.')
            out.append((a, b))
        return out
    def timed_boxes(self, key, maxn=50):
        """[((x, y, w, h), (start, end|None))]: boxes as 0-1 fractions, each hidden between its start and end (end 0 = to the end)."""
        v = self.d.get(key, [])
        if not isinstance(v, list) or not 1 <= len(v) <= maxn: raise ConversionError('Select at least one area.')
        rects = self.rects_of([r[:4] for r in v if isinstance(r, (list, tuple)) and len(r) == 6]);times = self.time_ranges_of([r[4:] for r in v if isinstance(r, (list, tuple)) and len(r) == 6])
        if len(rects) != len(v): raise ConversionError('Invalid area.')
        return list(zip(rects, times))
    def rects_of(self, raw): return P({'r': raw}).rects('r')
    def time_ranges_of(self, raw): return P({'t': raw}).time_ranges('t', open_end=True)

class Ctx:
    def __init__(self, job, paths, work, folder):
        self.params = P(job.get('params'));self.paths = paths;self.work = Path(work);self.folder = folder;self.ffmpeg = job.get('ffmpeg', '')
        self.results = [];self.count = 0;self.deadline = time.monotonic() + TOOL_DEADLINE
    def stage(self):
        self.count += 1;return self.work / f'stage-{self.count}'
    def publish(self, stage, stem, ext):
        path = publish(stage, self.folder, stem, ext);self.results.append(path);return path

def run_tool(job):
    tool = TOOLS.get(str(job.get('target', ''))[5:])
    if tool is None: raise ConversionError('Unsupported tool.')
    raws = job.get('paths', [])
    if not isinstance(raws, list) or not 1 <= len(raws) <= 100: raise ConversionError('Select 1–100 files.')
    paths = [engine.source_file(p) for p in raws]
    if not tools_for_one(tool, paths): raise ConversionError(f'{tool.title} does not apply to this selection.')
    if not tool.combined and len(paths) != 1: raise ConversionError('Each job accepts one input; use the queue.')
    folder, work_root = engine.job_folders(job, paths[0])
    with tempfile.TemporaryDirectory(prefix='.opentangerine-', dir=work_root) as work:
        ctx = Ctx(job, paths, work, folder);tool.run(ctx)
    if not ctx.results: raise ConversionError('The tool produced no output.')
    return ctx.results

def tools_for_one(tool, paths): return tool in tools_for(paths)

# ---------------------------------------------------------------------------------------------- images
def flatten(im, colour='white'):
    from PIL import Image
    rgba = im.convert('RGBA');base = Image.new('RGB', rgba.size, colour);base.paste(rgba, mask=rgba.getchannel('A'));return base

def image_ext(p): return IMAGE_SAME_EXT.get(Path(p).suffix.lower(), 'png')

def save_image(im, stage, ext, quality=92):
    if ext in ('jpg', 'bmp'): im = flatten(im)
    elif im.mode not in (('RGB', 'RGBA', 'L') if ext == 'heic' else ('RGB', 'RGBA', 'L', 'LA')): im = im.convert('RGBA')
    if ext == 'heic':
        import pillow_heif;pillow_heif.register_heif_opener()
    im.info.clear();im.save(stage, format=IMAGE_FORMAT[ext], quality=quality)

def checked_size(w, h):
    if w < 1 or h < 1 or w * h > MAX_PIXELS or max(w, h) > 20000: raise ConversionError('The result would exceed 40 megapixels.')
    return int(w), int(h)

def edit_values(p):
    """Validated Edit photo parameters (see photoadjust.LIMITS); missing ones are neutral."""
    P_ = p if isinstance(p, P) else P(p)
    values = {k: P_.num(k, lo, hi, default) for k, (lo, hi, default) in photoadjust.LIMITS.items()};values['monochrome'] = P_.flag('monochrome');return values

def apply_edit(im, p):
    values = edit_values(p)
    if im.mode not in ('RGBA', 'LA', 'PA') and 'transparency' not in im.info: return photoadjust.adjust(im if im.mode == 'RGB' else im.convert('RGB'), values)   # no alpha to carry: skip the RGBA copies
    rgba = im.convert('RGBA');alpha = rgba.getchannel('A');out = photoadjust.adjust(rgba.convert('RGB'), values)
    out = out.convert('RGBA');out.putalpha(alpha);return out

ASPECTS = {'original': None, '1:1': 1.0, '4:3': 4 / 3, '3:4': 3 / 4, '16:9': 16 / 9, '9:16': 9 / 16}

def apply_frame(im, p):
    from PIL import Image, ImageFilter, ImageOps
    P_ = p if isinstance(p, P) else P(p)
    pad = P_.num('padding', 0, 50, 10);aspect = P_.choice('aspect', tuple(ASPECTS), 'original');colour = P_.color('color', '#ffffff');blur = P_.flag('blur')
    w, h = im.size;margin = round(max(w, h) * pad / 100);cw, ch = w + 2 * margin, h + 2 * margin
    ratio = ASPECTS[aspect]
    if ratio:
        if cw / ch < ratio: cw = math.ceil(ch * ratio)
        else: ch = math.ceil(cw / ratio)
    cw, ch = checked_size(cw, ch);rgba = im.convert('RGBA')
    if blur: canvas = ImageOps.fit(rgba, (cw, ch)).filter(ImageFilter.GaussianBlur(max(cw, ch) / 40)).convert('RGBA')
    else: canvas = Image.new('RGBA', (cw, ch), colour)
    canvas.alpha_composite(rgba, ((cw - w) // 2, (ch - h) // 2));return canvas

def apply_crop(im, p):
    P_ = p if isinstance(p, P) else P(p)
    x, y, w, h = P_.rects('rect', 1)[0];W, H = im.size
    box = (round(x * W), round(y * H), max(round((x + w) * W), round(x * W) + 1), max(round((y + h) * H), round(y * H) + 1))
    return im.crop((box[0], box[1], min(box[2], W), min(box[3], H)))

def apply_redact(im, p):
    from PIL import Image, ImageFilter
    P_ = p if isinstance(p, P) else P(p)
    style = P_.choice('style', ('black', 'blur', 'pixelate'), 'black');W, H = im.size;out = im.convert('RGBA')
    for x, y, w, h in P_.rects('rects'):
        box = (round(x * W), round(y * H), min(W, max(round((x + w) * W), round(x * W) + 1)), min(H, max(round((y + h) * H), round(y * H) + 1)))
        region = out.crop(box)
        if style == 'black': region = Image.new('RGBA', region.size, (0, 0, 0, 255))
        elif style == 'blur': region = region.filter(ImageFilter.GaussianBlur(max(region.size) / 5 + 4))
        else:
            small = region.resize((max(1, region.width // 14), max(1, region.height // 14)), Image.Resampling.BILINEAR);region = small.resize(region.size, Image.Resampling.NEAREST)
        out.paste(region, box[:2])
    return out

def resize_target(size, p):
    P_ = p if isinstance(p, P) else P(p)
    mode = P_.choice('mode', ('percent', 'width', 'height', 'fit'), 'percent');w, h = size
    if mode == 'percent': f = P_.num('percent', 1, 400, 50) / 100;nw, nh = w * f, h * f
    elif mode == 'width': nw = P_.num('width', 1, 10000, 1280, True);nh = h * nw / w
    elif mode == 'height': nh = P_.num('height', 1, 10000, 720, True);nw = w * nh / h
    else:
        bw, bh = P_.num('width', 1, 10000, 1280, True), P_.num('height', 1, 10000, 720, True);f = min(bw / w, bh / h);nw, nh = w * f, h * f
    return checked_size(max(1, round(nw)), max(1, round(nh)))

def apply_resize(im, p):
    from PIL import Image
    return im.resize(resize_target(im.size, p), Image.Resampling.LANCZOS)

def apply_rotate(im, p):
    from PIL import Image
    P_ = p if isinstance(p, P) else P(p)
    turn = P_.choice('rotation', (0, 90, 180, 270), 0);out = im
    if turn: out = out.rotate(-turn, expand=True)
    if P_.flag('flip_h'): out = out.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if P_.flag('flip_v'): out = out.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    return out

PIXEL_OPS = {'edit_image': apply_edit, 'frame_image': apply_frame, 'crop_image': apply_crop, 'redact_image': apply_redact, 'resize_image': apply_resize, 'rotate_image': apply_rotate}

def per_image(ctx, name, suffix):
    p = ctx.paths[0];im = open_image(p);out = None
    try:
        out = PIXEL_OPS[name](im, ctx.params);ext = image_ext(p);stage = ctx.stage();save_image(out, stage, ext, ctx.params.num('quality', 1, 100, 92, True));ctx.publish(stage, p.stem + '-' + suffix, ext)
    finally:
        im.close()
        if out is not None and out is not im: out.close()

IMG = ('image',)
@register(id='edit_image', title='Edit photo', progress='Editing photo', label='Edit', caption='Adjust', categories=IMG, ui='preview', fields=(
    Field('exposure', 'Exposure', 'float', 0, -2, 2, group='Light', hint='Stops of light, like a camera'), Field('brightness', 'Brightness', 'float', 0, -1, 1, group='Light'), Field('contrast', 'Contrast', 'float', 0, -1, 1, group='Light'),
    Field('highlights', 'Highlights', 'float', 0, -1, 1, group='Light', hint='Negative recovers bright areas'), Field('shadows', 'Shadows', 'float', 0, -1, 1, group='Light', hint='Positive lifts dark areas'),
    Field('saturation', 'Colour', 'float', 0, -1, 1, group='Colour'), Field('vibrance', 'Vibrance', 'float', 0, -1, 1, group='Colour', hint='Colour boost that spares already vivid tones'),
    Field('temperature', 'Temperature', 'float', 0, -1, 1, group='Colour', hint='Cooler (blue) to warmer (orange)'), Field('tint', 'Tint', 'float', 0, -1, 1, group='Colour', hint='Green to magenta'),
    Field('sepia', 'Sepia', 'float', 0, 0, 1, group='Colour'), Field('monochrome', 'Black and white', 'bool', False, group='Colour'),
    Field('sharpness', 'Sharpness', 'float', 0, -1, 1, group='Detail'), Field('clarity', 'Clarity', 'float', 0, 0, 1, group='Detail', hint='Mid-tone punch'),
    Field('dehaze', 'Dehaze', 'float', 0, 0, 1, group='Detail'), Field('noise', 'Noise reduction', 'float', 0, 0, 1, group='Detail'),
    Field('grain', 'Grain', 'float', 0, 0, 1, group='Effects'), Field('vignette', 'Vignette', 'float', 0, 0, 1, group='Effects')))
def _edit(ctx): per_image(ctx, 'edit_image', 'edited')

@register(id='frame_image', title='Add a background', progress='Adding background', label='Background', caption='Border', categories=IMG, ui='preview', fields=(
    Field('padding', 'Padding', 'float', 10, 0, 50, suffix=' %'), Field('aspect', 'Shape', 'choice', 'original', options=tuple((k, k.capitalize() if k == 'original' else k) for k in ASPECTS)),
    Field('color', 'Colour', 'color', '#ffffff'), Field('blur', 'Blurred photo as background', 'bool', False)))
def _frame(ctx): per_image(ctx, 'frame_image', 'framed')

@register(id='crop_image', title='Crop image', progress='Cropping', label='Crop', caption='Cut out', categories=IMG, ui='crop')
def _crop(ctx): per_image(ctx, 'crop_image', 'cropped')

@register(id='redact_image', title='Redact photo', progress='Redacting', label='Redact', caption='Hide parts', categories=IMG, ui='redact', fields=(
    Field('style', 'Style', 'choice', 'black', options=(('black', 'Black box (cannot be undone)'), ('blur', 'Blur'), ('pixelate', 'Pixelate')), hint='Blur and pixelate can sometimes be reversed; use black for sensitive data.'),))
def _redact(ctx): per_image(ctx, 'redact_image', 'redacted')

@register(id='resize_image', title='Resize images', progress='Resizing', label='Resize', caption='New size', categories=IMG, arity='any', ui='preview', fields=(
    Field('mode', 'Resize by', 'choice', 'percent', options=(('percent', 'Percent'), ('width', 'Width'), ('height', 'Height'), ('fit', 'Fit inside box'))),
    Field('percent', 'Percent', 'float', 50, 1, 400, suffix=' %', when=('mode', 'percent')), Field('width', 'Width', 'int', 1280, 1, 10000, suffix=' px', when=('mode', ('width', 'fit'))), Field('height', 'Height', 'int', 720, 1, 10000, suffix=' px', when=('mode', ('height', 'fit')))))
def _resize(ctx): per_image(ctx, 'resize_image', 'resized')

@register(id='rotate_image', title='Rotate & flip', progress='Rotating', label='Rotate', caption='Flip', categories=IMG, arity='any', ui='preview', fields=(
    Field('rotation', 'Rotate', 'choice', 0, options=((0, 'No rotation'), (90, '90° clockwise'), (180, '180°'), (270, '270° clockwise'))), Field('flip_h', 'Flip horizontally', 'bool', False), Field('flip_v', 'Flip vertically', 'bool', False)))
def _rotate(ctx): per_image(ctx, 'rotate_image', 'rotated')

@register(id='create_pdf', title='Create a PDF', progress='Creating PDF', label='PDF', caption='From images', categories=IMG, arity='any', combined=True, ui='order', fields=(
    Field('page', 'Page size', 'choice', 'a4', options=(('a4', 'A4'), ('letter', 'US Letter'), ('fit', 'Same as each image'))),))
def _create_pdf(ctx):
    from PIL import Image
    from pypdf import PdfWriter, PdfReader
    if len(ctx.paths) > 200: raise ConversionError('A PDF cannot exceed 200 pages.')
    page = ctx.params.choice('page', ('fit', 'a4', 'letter'), 'a4');size = engine.PAGE_PIXELS.get(page);pieces = []
    for i, p in enumerate(ctx.paths):
        im = open_image(p)
        try:
            img = flatten(im)
            if size:
                img = engine.on_page(img, size)
            piece = ctx.work / f'p{i}.pdf';img.save(piece, format='PDF', resolution=150);pieces.append(piece)
        finally: im.close()
    writer = PdfWriter()
    for piece in pieces:
        for pg in PdfReader(str(piece)).pages: writer.add_page(pg)
    stage = ctx.stage()
    with stage.open('wb') as f: writer.write(f)
    ctx.publish(stage, ctx.paths[0].stem + ('-images' if len(ctx.paths) > 1 else ''), 'pdf')

@register(id='collage', title='Create a collage', progress='Creating collage', label='Collage', caption='Grid', categories=IMG, arity='multiple', combined=True, ui='order', fields=(
    Field('columns', 'Columns', 'int', 0, 0, 10, hint='0 chooses automatically'), Field('cell', 'Cell size', 'int', 600, 100, 2000, suffix=' px'), Field('spacing', 'Spacing', 'int', 12, 0, 100, suffix=' px'),
    Field('fit', 'Fit', 'choice', 'cover', options=(('cover', 'Fill the cell'), ('contain', 'Show the whole photo'))), Field('color', 'Background', 'color', '#ffffff')))
def _collage(ctx):
    from PIL import Image, ImageOps
    n = len(ctx.paths)
    if n > 30: raise ConversionError('A collage can contain up to 30 photos.')
    p = ctx.params;cols = p.num('columns', 0, 10, 0, True) or math.ceil(math.sqrt(n));cell = p.num('cell', 100, 2000, 600, True);gap = p.num('spacing', 0, 100, 12, True);fit = p.choice('fit', ('cover', 'contain'), 'cover');colour = p.color('color', '#ffffff')
    rows = math.ceil(n / cols);W, H = checked_size(cols * cell + (cols + 1) * gap, rows * cell + (rows + 1) * gap);canvas = Image.new('RGB', (W, H), colour)
    for i, path in enumerate(ctx.paths):
        im = open_image(path)
        try:
            tile = flatten(im);r, c = divmod(i, cols);x = gap + c * (cell + gap);y = gap + r * (cell + gap)
            if fit == 'cover': tile = ImageOps.fit(tile, (cell, cell), Image.Resampling.LANCZOS);canvas.paste(tile, (x, y))
            else: tile.thumbnail((cell, cell), Image.Resampling.LANCZOS);canvas.paste(tile, (x + (cell - tile.width) // 2, y + (cell - tile.height) // 2))
        finally: im.close()
    stage = ctx.stage();canvas.save(stage, format='PNG');ctx.publish(stage, ctx.paths[0].stem + '-collage', 'png')

# ---------------------------------------------------------------------------------------------- PDF
PDF = ('pdf',)
def parse_ranges(text, n):
    out = []
    for part in re.split(r'[,;]', text):
        part = part.strip()
        if not part: continue
        try:
            if '-' in part: a, b = part.split('-', 1);a = int(a) if a.strip() else 1;b = int(b) if b.strip() else n
            else: a = b = int(part)
        except ValueError: raise ConversionError(f'Cannot read the page range "{part}".')
        if not 1 <= a <= b <= n: raise ConversionError(f'Page range {part} is outside 1–{n}.')
        out.append((a, b))
    if not out or len(out) > 100: raise ConversionError('Enter between 1 and 100 page ranges, for example 1-3, 5, 8-.')
    return out

def write_pdf(writer, stage):
    with stage.open('wb') as f: writer.write(f)

@register(id='merge_pdf', title='Merge PDFs', progress='Merging', label='Merge', caption='Combine', categories=PDF, arity='multiple', combined=True, ui='order')
def _merge(ctx):
    from pypdf import PdfWriter
    writer = PdfWriter();total = 0
    for path in ctx.paths:
        pdf = read_pdf(path);total += len(pdf.pages)
        if total > 200: raise ConversionError('Merged PDF cannot exceed 200 pages.')
        for pg in pdf.pages: writer.add_page(pg)
    stage = ctx.stage();write_pdf(writer, stage);ctx.publish(stage, 'merged', 'pdf')

@register(id='organize_pdf', title='Organize PDF pages', progress='Organizing', label='Organize', caption='Reorder', categories=PDF, ui='pages')
def _organize(ctx):
    from pypdf import PdfWriter
    pdf = read_pdf(ctx.paths[0]);plan = ctx.params.d.get('pages')
    if not isinstance(plan, list) or not 1 <= len(plan) <= 200: raise ConversionError('Keep at least one page (up to 200).')
    writer = PdfWriter()
    for item in plan:
        try: index, turn = int(item['page']), int(item.get('rotate', 0))
        except (TypeError, ValueError, KeyError): raise ConversionError('Invalid page plan.')
        if not 0 <= index < len(pdf.pages) or turn not in (0, 90, 180, 270): raise ConversionError('Invalid page plan.')
        pg = writer.add_page(pdf.pages[index])
        if turn: pg.rotate(turn)
    stage = ctx.stage();write_pdf(writer, stage);ctx.publish(stage, ctx.paths[0].stem + '-organized', 'pdf')

@register(id='split_pdf', title='Split PDF', progress='Splitting', label='Split', caption='By pages', categories=PDF, fields=(
    Field('mode', 'Split', 'choice', 'each', options=(('each', 'Every page into its own file'), ('ranges', 'By page ranges'))), Field('ranges', 'Ranges', 'text', '1-3, 4-', hint='Each range becomes one file, for example 1-3, 5, 8-', when=('mode', 'ranges'))))
def _split(ctx):
    from pypdf import PdfWriter
    pdf = read_pdf(ctx.paths[0]);n = len(pdf.pages);p = ctx.paths[0]
    mode = ctx.params.choice('mode', ('each', 'ranges'), 'each')
    spans = [(i, i) for i in range(1, n + 1)] if mode == 'each' else parse_ranges(ctx.params.text('ranges'), n)
    pieces = []
    for a, b in spans:
        writer = PdfWriter()
        for i in range(a - 1, b): writer.add_page(pdf.pages[i])
        stage = ctx.stage();write_pdf(writer, stage);pieces.append((stage, f'{p.stem}-page-{a}' if a == b else f'{p.stem}-pages-{a}-{b}'))
        if sum(s.stat().st_size for s, _ in pieces) > MAX_OUTPUT: raise ConversionError('Split outputs exceed 512 MiB.')
    for stage, stem in pieces: ctx.publish(stage, stem, 'pdf')

# ---------------------------------------------------------------------------------------------- ffmpeg helpers
def ffmpeg_exe(ctx): return tool_path(ctx.ffmpeg, 'FFmpeg', 'ffmpeg')

def probe(ctx, p): return probe_file(ffmpeg_exe(ctx), p, ctx.deadline)

def probe_file(exe, p, deadline):
    """Duration, picture size and audio presence, read from FFmpeg's own banner (no ffprobe needed)."""
    p = Path(p);code, text = run_external([str(exe), '-hide_banner', '-protocol_whitelist', 'file,pipe', '-f', MEDIA_INPUTS[p.suffix.lower()], '-i', str(p)], deadline, tail=65536)
    d = re.search(r'Duration: (\d+):(\d+):(\d+(?:\.\d+)?)', text);v = re.search(r'Video:.*?[\s,](\d{2,5})x(\d{2,5})', text)
    if not d and not v and 'Audio:' not in text: raise ConversionError('FFmpeg could not read this file. Check its codec support.')
    size = (int(v[1]), int(v[2])) if v else None;turn = re.search(r'rotation of (-?\d+(?:\.\d+)?) degrees', text)
    if size and turn and round(abs(float(turn[1]))) % 180 == 90: size = (size[1], size[0])       # FFmpeg turns the picture upright before filters see it
    return {'duration': int(d[1]) * 3600 + int(d[2]) * 60 + float(d[3]) if d else 0.0, 'size': size, 'audio': 'Audio:' in text}

def grab_frame(exe, path, seconds, out, side=720, deadline=20):
    """Write one upright frame at `seconds` as PNG (previews in the Redact video window). Falls back to the first frame past the end."""
    p = Path(path)
    for t in (max(0.0, seconds), 0.0):
        cmd = [str(exe), '-nostdin', '-hide_banner', '-loglevel', 'error', '-y', '-protocol_whitelist', 'file,pipe', '-ss', f'{t:.3f}', '-f', MEDIA_INPUTS[p.suffix.lower()], '-i', str(p),
               '-frames:v', '1', '-vf', f"scale='min({side},iw)':-2", '-f', 'image2', str(out)]
        code, detail = run_external(cmd, time.monotonic() + deadline)
        if not code and Path(out).is_file() and Path(out).stat().st_size: return
        if t == 0.0: raise ConversionError('FFmpeg could not read a picture from this video. ' + detail)

def ffmpeg(ctx, inputs, args, stage, fmt, pre=()):
    cmd = [str(ffmpeg_exe(ctx)), '-nostdin', '-hide_banner', '-loglevel', 'error', '-n', '-protocol_whitelist', 'file,pipe', *pre]
    for p in inputs: cmd += ['-f', MEDIA_INPUTS[p.suffix.lower()], '-i', str(p)]
    cmd += ['-map_metadata', '-1', '-threads', '2', *args, '-fs', str(MAX_OUTPUT), '-f', fmt, str(stage)]
    code, detail = run_external(cmd, ctx.deadline)
    if code or not stage.is_file(): raise ConversionError('FFmpeg could not process this file. ' + detail)

def media_out(ctx, p, args_video=None):
    """(ffmpeg container, codec args, extension) that keeps audio files in their own format and video in MP4."""
    if p.suffix.lower() in AUDIO_EXT:
        fmt, args = AUDIO_OUT[p.suffix.lower()];return fmt, args, p.suffix.lower()[1:]
    return 'mp4', VIDEO_ENC, 'mp4'

def even(v): return max(2, int(v) // 2 * 2)

def encode_segment(ctx, p, start, length, stem):
    fmt, enc, ext = media_out(ctx, p);stage = ctx.stage()
    ffmpeg(ctx, [p], ['-ss', f'{start:.3f}', '-t', f'{length:.3f}', *enc], stage, fmt);ctx.publish(stage, stem, ext)

VID, AUD = ('video',), ('audio',)
@register(id='compress', title='Compress', progress='Compressing', label='Compress', caption='Smaller files', categories=('image', 'video', 'audio', 'pdf'), arity='any', fields=(
    Field('level', 'Strength', 'choice', 'balanced', options=(('light', 'Light, best quality'), ('balanced', 'Balanced'), ('strong', 'Strong, smallest')), hint='Video and audio need FFmpeg. Audio becomes MP3; video becomes MP4.'),))
def _compress(ctx):
    p = ctx.paths[0];level = ctx.params.choice('level', ('light', 'balanced', 'strong'), 'balanced');kind = category(p);stage = ctx.stage()
    if kind == 'image':
        ext = image_ext(p);q = {'light': 88, 'balanced': 75, 'strong': 55}[level];im = open_image(p)
        try:
            if ext == 'png':
                out = im.convert('RGBA').quantize(256, method=2) if level == 'strong' else im
                out.save(stage, format='PNG', optimize=True)
            else:
                if ext in ('jpg', 'bmp'): im = flatten(im)
                if ext == 'bmp': ext = 'jpg'
                im.info.clear()
                if ext == 'heic':
                    import pillow_heif;pillow_heif.register_heif_opener()
                im.save(stage, format=IMAGE_FORMAT[ext], quality=q, **({'optimize': True} if ext == 'jpg' else {}))
        finally: im.close()
        out_ext = ext
    elif kind == 'pdf':
        from pypdf import PdfWriter
        pdf = read_pdf(p);writer = PdfWriter()
        for pg in pdf.pages: writer.add_page(pg)
        for pg in writer.pages: pg.compress_content_streams()
        writer.compress_identical_objects(remove_identicals=True, remove_orphans=True);write_pdf(writer, stage);out_ext = 'pdf'
    elif kind == 'video':
        crf = {'light': '25', 'balanced': '28', 'strong': '33'}[level]
        ffmpeg(ctx, [p], ['-c:v', 'libx264', '-preset', 'medium', '-crf', crf, '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '96k', '-movflags', '+faststart'], stage, 'mp4');out_ext = 'mp4'
    else:
        rate = {'light': '160k', 'balanced': '112k', 'strong': '64k'}[level];ffmpeg(ctx, [p], ['-vn', '-c:a', 'libmp3lame', '-b:a', rate], stage, 'mp3');out_ext = 'mp3'
    if stage.stat().st_size >= p.stat().st_size: raise ConversionError('This file is already well compressed; the result would not be smaller.')
    ctx.publish(stage, p.stem + '-compressed', out_ext)

@register(id='metadata', title='Edit metadata', progress='Editing metadata', label='Metadata', caption='Privacy', categories=('image', 'video', 'audio', 'pdf'), arity='any', fields=(
    Field('mode', 'Remove', 'choice', 'all', options=(('all', 'All metadata'), ('gps', 'Location only (images)'))),
    Field('title', 'Title', 'text', '', hint='Optional: PDF, audio and video'), Field('author', 'Author / artist', 'text', '', hint='Optional: PDF, audio and video')))
def _metadata(ctx):
    p = ctx.paths[0];kind = category(p);stage = ctx.stage();mode = ctx.params.choice('mode', ('all', 'gps'), 'all');title = ctx.params.text('title');author = ctx.params.text('author')
    if kind == 'image':
        ext = image_ext(p);im = open_image(p)
        try:
            if mode == 'gps' and ext in ('jpg', 'tiff', 'webp', 'png', 'heic'):
                from PIL import Image
                with Image.open(p) as raw: exif = raw.getexif()
                exif.pop(0x8825, None);im.info.clear()
                if ext == 'heic':
                    import pillow_heif;pillow_heif.register_heif_opener()
                im.save(stage, format=IMAGE_FORMAT[ext], exif=exif, quality=95)
            else: save_image(im, stage, ext, 95)
        finally: im.close()
        out_ext = ext
    elif kind == 'pdf':
        from pypdf import PdfWriter
        pdf = read_pdf(p);writer = PdfWriter()
        for pg in pdf.pages: writer.add_page(pg)
        meta = {}
        if title: meta['/Title'] = title
        if author: meta['/Author'] = author
        if meta: writer.add_metadata(meta)
        write_pdf(writer, stage);out_ext = 'pdf'
    else:
        fmt, enc, ext = (AUDIO_OUT[p.suffix.lower()][0], ['-c', 'copy'], p.suffix.lower()[1:]) if kind == 'audio' else ({'.mkv': 'matroska', '.webm': 'webm'}.get(p.suffix.lower(), 'mp4'), ['-c', 'copy'], p.suffix.lower()[1:] if p.suffix.lower() in ('.mkv', '.webm') else 'mp4')
        tags = [x for k, v in (('title', title), ('artist', author)) if v for x in ('-metadata', f'{k}={v}')]
        ffmpeg(ctx, [p], [*enc, *tags], stage, fmt);out_ext = ext
    ctx.publish(stage, p.stem + '-clean', out_ext)

@register(id='trim', title='Trim', progress='Trimming', label='Trim', caption='Cut start/end', categories=('video', 'audio'), ffmpeg=True, ui='trim', fields=(
    Field('start', 'Start', 'float', 0, 0, 86400, suffix=' s'), Field('end', 'End (0 = until the end)', 'float', 0, 0, 86400, suffix=' s')))
def _trim(ctx):
    p = ctx.paths[0];info = probe(ctx, p);start = ctx.params.num('start', 0, 86400, 0);end = ctx.params.num('end', 0, 86400, 0)
    stop = end or info['duration']
    if not stop: raise ConversionError('Enter an end time; the length of this file could not be read.')
    if info['duration'] and start >= info['duration']: raise ConversionError('Start is after the end of the file.')
    if end and end <= start: raise ConversionError('End must be after start.')
    encode_segment(ctx, p, start, stop - start, p.stem + '-trimmed')

@register(id='split_media', title='Split video', progress='Splitting', label='Split', caption='Into parts', categories=('video',), ffmpeg=True, fields=(
    Field('mode', 'Split', 'choice', 'parts', options=(('parts', 'Into equal parts'), ('at', 'At specific times'))), Field('parts', 'Parts', 'int', 2, 2, 20, when=('mode', 'parts')), Field('times', 'Cut at (seconds)', 'text', '60, 120', hint='Comma-separated seconds', when=('mode', 'at'))))
def _split_media(ctx):
    p = ctx.paths[0];info = probe(ctx, p);total = info['duration']
    if not total: raise ConversionError('The length of this file could not be read.')
    if ctx.params.choice('mode', ('parts', 'at'), 'parts') == 'parts':
        n = ctx.params.num('parts', 2, 20, 2, True);cuts = [total * i / n for i in range(1, n)]
    else:
        try: cuts = sorted({float(x) for x in re.split(r'[,;\s]+', ctx.params.text('times').strip()) if x})
        except ValueError: raise ConversionError('Enter cut times as numbers of seconds.')
        if not cuts or len(cuts) > 19 or cuts[0] <= 0 or cuts[-1] >= total: raise ConversionError('Cut times must be between 0 and the length of the file (at most 19).')
    marks = [0.0, *cuts, total]
    for i in range(len(marks) - 1): encode_segment(ctx, p, marks[i], marks[i + 1] - marks[i], f'{p.stem}-part-{i + 1}')

@register(id='crop_video', title='Crop video', progress='Cropping', label='Crop', caption='Cut out', categories=('video',), ffmpeg=True, fields=(
    Field('shape', 'Crop to', 'choice', '1:1', options=(('1:1', 'Square 1:1'), ('16:9', 'Wide 16:9'), ('9:16', 'Vertical 9:16'), ('4:3', 'Classic 4:3'), ('3:4', 'Portrait 3:4'))),
    Field('anchor', 'Keep', 'choice', 'center', options=(('center', 'Centre'), ('start', 'Left / top'), ('end', 'Right / bottom')))))
def _crop_video(ctx):
    p = ctx.paths[0];info = probe(ctx, p)
    if not info['size']: raise ConversionError('This file has no picture to crop.')
    W, H = info['size'];a, b = (int(x) for x in ctx.params.choice('shape', ('1:1', '16:9', '9:16', '4:3', '3:4'), '1:1').split(':'));ratio = a / b
    if W / H > ratio: cw, ch = even(H * ratio), even(H)
    else: cw, ch = even(W), even(W / ratio)
    frac = {'start': 0, 'center': .5, 'end': 1}[ctx.params.choice('anchor', ('center', 'start', 'end'), 'center')];x = even((W - cw) * frac) if W > cw else 0;y = even((H - ch) * frac) if H > ch else 0
    stage = ctx.stage();ffmpeg(ctx, [p], ['-vf', f'crop={cw}:{ch}:{x}:{y}', *VIDEO_ENC], stage, 'mp4');ctx.publish(stage, p.stem + '-cropped', 'mp4')

@register(id='speed_video', title='Change video speed', progress='Changing speed', label='Speed', caption='Faster / slower', categories=('video',), ffmpeg=True, fields=(
    Field('factor', 'Speed', 'float', 2, .25, 4, suffix=' ×'),))
def _speed(ctx):
    p = ctx.paths[0];f = ctx.params.num('factor', .25, 4, 2);info = probe(ctx, p);chain = [];rest = f
    while rest > 2.0: chain.append(2.0);rest /= 2.0
    while rest < .5: chain.append(.5);rest /= .5
    chain.append(rest);atempo = ','.join(f'atempo={x:.4f}' for x in chain)
    args = ['-filter:v', f'setpts=PTS/{f:.4f}'] + (['-filter:a', atempo] if info['audio'] else ['-an']);stage = ctx.stage()
    ffmpeg(ctx, [p], [*args, *VIDEO_ENC], stage, 'mp4');ctx.publish(stage, p.stem + f'-{f:g}x', 'mp4')

@register(id='join_videos', title='Join videos', progress='Joining', label='Join', caption='One video', categories=('video',), arity='multiple', combined=True, ffmpeg=True, ui='order')
def _join(ctx):
    n = len(ctx.paths)
    if n > 20: raise ConversionError('Join up to 20 videos at a time.')
    infos = [probe(ctx, p) for p in ctx.paths]
    if any(not i['size'] for i in infos): raise ConversionError('Every file must contain video.')
    W, H = (even(v) for v in infos[0]['size']);audio = all(i['audio'] for i in infos);parts = []
    for i in range(n):
        parts.append(f'[{i}:v]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p[v{i}]')
        if audio: parts.append(f'[{i}:a]aresample=48000,aformat=channel_layouts=stereo[a{i}]')
    graph = ';'.join(parts) + ';' + ''.join(f'[v{i}]' + (f'[a{i}]' if audio else '') for i in range(n)) + f'concat=n={n}:v=1:a={1 if audio else 0}[v]' + ('[a]' if audio else '')
    stage = ctx.stage();ffmpeg(ctx, ctx.paths, ['-filter_complex', graph, '-map', '[v]', *(['-map', '[a]'] if audio else []), *VIDEO_ENC], stage, 'mp4')
    ctx.publish(stage, ctx.paths[0].stem + '-joined', 'mp4')

@register(id='video_frames', title='Save video frames', progress='Saving frames', label='Frames', caption='Stills', categories=('video',), ffmpeg=True, fields=(
    Field('mode', 'Save', 'choice', 'count', options=(('count', 'A number of evenly spaced frames'), ('interval', 'One frame every N seconds'))), Field('count', 'Frames', 'int', 12, 1, 200, when=('mode', 'count')), Field('seconds', 'Every', 'float', 5, .1, 3600, suffix=' s', when=('mode', 'interval')),
    Field('format', 'Format', 'choice', 'png', options=(('png', 'PNG'), ('jpg', 'JPEG')))))
def _frames(ctx):
    p = ctx.paths[0];info = probe(ctx, p);total = info['duration']
    if not total: raise ConversionError('The length of this file could not be read.')
    fmt = ctx.params.choice('format', ('png', 'jpg'), 'png')
    if ctx.params.choice('mode', ('count', 'interval'), 'count') == 'count': rate = ctx.params.num('count', 1, 200, 12, True) / total
    else: rate = 1 / ctx.params.num('seconds', .1, 3600, 5)
    cap = 200;cmd = [str(ffmpeg_exe(ctx)), '-nostdin', '-hide_banner', '-loglevel', 'error', '-n', '-protocol_whitelist', 'file,pipe', '-f', MEDIA_INPUTS[p.suffix.lower()], '-i', str(p), '-an', '-vf', f'fps={rate:.6f}', '-frames:v', str(cap), '-threads', '2', str(ctx.work / f'frame-%04d.{fmt}')]
    code, detail = run_external(cmd, ctx.deadline)
    frames = sorted(ctx.work.glob(f'frame-*.{fmt}'))
    if code or not frames: raise ConversionError('FFmpeg could not extract frames. ' + detail)
    folder = new_folder(ctx.folder, p.stem + '-frames')
    for f in frames: ctx.results.append(publish(f, folder, f.stem, fmt))

def new_folder(parent, stem):
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', stem).rstrip('. ')[:100] or 'frames'
    for n in range(1, 10001):
        d = parent / (stem + ('-' + str(n) if n > 1 else ''))
        try: d.mkdir();return d
        except FileExistsError: continue
    raise ConversionError('Too many existing folders; choose another location.')

@register(id='normalize_audio', title='Normalize volume', progress='Normalizing', label='Normalize', caption='Even volume', categories=('audio', 'video'), ffmpeg=True, fields=(
    Field('target', 'Target loudness', 'float', -16, -30, -5, suffix=' LUFS', hint='-16 suits music and video; -23 is broadcast'),))
def _normalize(ctx):
    p = ctx.paths[0];target = ctx.params.num('target', -30, -5, -16);info = probe(ctx, p)
    if not info['audio']: raise ConversionError('This file has no audio.')
    fmt, enc, ext = media_out(ctx, p);stage = ctx.stage();ffmpeg(ctx, [p], ['-af', f'loudnorm=I={target:g}:TP=-1.5:LRA=11', *enc], stage, fmt);ctx.publish(stage, p.stem + '-normalized', ext)

@register(id='audio_channels', title='Audio channels', progress='Converting channels', label='Channels', caption='Mono / stereo', categories=('audio',), ffmpeg=True, fields=(
    Field('mode', 'Channels', 'choice', 'mono', options=(('mono', 'Mix to mono'), ('stereo', 'Stereo'), ('left', 'Left channel only'), ('right', 'Right channel only'), ('swap', 'Swap left and right'))),))
def _channels(ctx):
    p = ctx.paths[0];mode = ctx.params.choice('mode', ('mono', 'stereo', 'left', 'right', 'swap'), 'mono')
    flt = {'mono': ['-ac', '1'], 'stereo': ['-ac', '2'], 'left': ['-af', 'pan=mono|c0=c0'], 'right': ['-af', 'pan=mono|c0=c1'], 'swap': ['-af', 'pan=stereo|c0=c1|c1=c0']}[mode]
    fmt, enc, ext = media_out(ctx, p);stage = ctx.stage();ffmpeg(ctx, [p], [*flt, *enc], stage, fmt);ctx.publish(stage, p.stem + '-' + mode, ext)

@register(id='audio_visualizer', title='Audio visualizer', progress='Creating visualizer', label='Visualize', caption='Waveform video', categories=('audio',), ffmpeg=True, fields=(
    Field('style', 'Style', 'choice', 'cline', options=(('cline', 'Centred line'), ('line', 'Line'), ('p2p', 'Point to point'))), Field('color', 'Colour', 'color', '#ff610a')))
def _visualizer(ctx):
    p = ctx.paths[0];style = ctx.params.choice('style', ('cline', 'line', 'p2p'), 'cline');colour = '0x' + ctx.params.color('color', '#ff610a')[1:]
    graph = f'[0:a]showwaves=s=1280x720:mode={style}:colors={colour}:rate=30,format=yuv420p[v]';stage = ctx.stage()
    ffmpeg(ctx, [p], ['-filter_complex', graph, '-map', '[v]', '-map', '0:a', *VIDEO_ENC], stage, 'mp4');ctx.publish(stage, p.stem + '-visualizer', 'mp4')

# ---------------------------------------------------------------------------------------------- redact video and bleep audio
def when(a, b): return f'between(t,{a:.3f},{b:.3f})' if b else f'gte(t,{a:.3f})'

def px_box(rect, W, H):
    """Fractions to an even-aligned pixel box that fully covers the selection."""
    x, y, w, h = rect;x0 = int(x * W) // 2 * 2;y0 = int(y * H) // 2 * 2;x1 = min(W, math.ceil((x + w) * W));y1 = min(H, math.ceil((y + h) * H))
    x1 += x1 % 2 if x1 < W else 0;y1 += y1 % 2 if y1 < H else 0
    return x0, y0, max(2, min(W, x1) - x0), max(2, min(H, y1) - y0)

@register(id='redact_video', title='Redact video', progress='Redacting', label='Redact', caption='Hide parts', categories=VID, ffmpeg=True, ui='redact_video', fields=(
    Field('style', 'Style', 'choice', 'black', options=(('black', 'Black box (cannot be undone)'), ('blur', 'Blur'), ('pixelate', 'Pixelate')), hint='Blur and pixelate can sometimes be reversed; use black for sensitive data.'),))
def _redact_video(ctx):
    p = ctx.paths[0];info = probe(ctx, p);style = ctx.params.choice('style', ('black', 'blur', 'pixelate'), 'black')
    if not info['size']: raise ConversionError('The picture size of this video could not be read.')
    W, H = info['size'];boxes = ctx.params.timed_boxes('boxes');cur = '0:v';parts = []
    for i, (rect, (a, b)) in enumerate(boxes):
        if info['duration'] and a >= info['duration']: raise ConversionError(f'Area {i + 1} starts after the end of the video.')
        x, y, w, h = px_box(rect, W, H);on = f"enable='{when(a, b)}'";out = f'v{i}'
        if style == 'black': parts.append(f'[{cur}]drawbox=x={x}:y={y}:w={w}:h={h}:color=black:t=fill:{on}[{out}]')
        else:
            fx = f'gblur=sigma={max(4, min(w, h) // 4)}' if style == 'blur' else f'scale={math.ceil(w / 14)}:{math.ceil(h / 14)}:flags=area,scale={w}:{h}:flags=neighbor'
            parts.append(f'[{cur}]split[m{i}][s{i}];[s{i}]crop={w}:{h}:{x}:{y},{fx}[p{i}];[m{i}][p{i}]overlay={x}:{y}:{on}[{out}]')
        cur = out
    stage = ctx.stage();ffmpeg(ctx, [p], ['-filter_complex', ';'.join(parts), '-map', f'[{cur}]', '-map', '0:a?', *VIDEO_ENC], stage, 'mp4');ctx.publish(stage, p.stem + '-redacted', 'mp4')

@register(id='bleep_audio', title='Bleep audio', progress='Bleeping', label='Bleep', caption='Cover words', categories=AUD, ffmpeg=True, ui='bleep', fields=(
    Field('mode', 'Cover with', 'choice', 'bleep', options=(('bleep', 'A bleep tone'), ('silence', 'Silence'))),
    Field('frequency', 'Tone pitch', 'int', 1000, 200, 4000, suffix=' Hz', when=('mode', 'bleep'))))
def _bleep(ctx):
    p = ctx.paths[0];info = probe(ctx, p);mode = ctx.params.choice('mode', ('bleep', 'silence'), 'bleep');freq = ctx.params.num('frequency', 200, 4000, 1000, True)
    ranges = ctx.params.time_ranges('ranges')
    if not info['audio']: raise ConversionError('This file has no audio.')
    if info['duration'] and ranges[0][0] >= info['duration'] and all(a >= info['duration'] for a, _ in ranges): raise ConversionError('Every range starts after the end of the file.')
    cond = '+'.join(when(a, b) for a, b in ranges)
    if mode == 'silence': flt = f"volume=volume='1-gt({cond},0)':eval=frame"
    else: flt = f"aeval='val(ch)*(1-gt({cond},0))+0.3*sin(2*PI*{freq}*t)*gt({cond},0)':c=same"
    fmt, enc, ext = media_out(ctx, p);stage = ctx.stage();ffmpeg(ctx, [p], ['-af', flt, *enc], stage, fmt);ctx.publish(stage, p.stem + '-bleeped', ext)

# Wheel order: the ones people reach for first come first.
ORDER = ['compress', 'edit_image', 'crop_image', 'resize_image', 'rotate_image', 'frame_image', 'redact_image', 'create_pdf', 'collage', 'metadata', 'merge_pdf', 'organize_pdf', 'split_pdf', 'trim', 'speed_video', 'crop_video', 'join_videos', 'split_media', 'video_frames', 'redact_video', 'normalize_audio', 'audio_channels', 'audio_visualizer', 'bleep_audio']
TOOLS = {k: TOOLS[k] for k in ORDER if k in TOOLS} | {k: v for k, v in TOOLS.items() if k not in ORDER}
