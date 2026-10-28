"""Document conversions that need no external program: text to PDF/images/subtitles, PDF to images/DOCX,
image to DOCX and subtitle to text. These mirror the Mac app's DocumentEngine, SubtitleEngine and DocxWriter."""
from __future__ import annotations
import os, re, zipfile
from pathlib import Path
from engine import ConversionError, MAX_PIXELS, MAX_OUTPUT, IMAGE_INPUTS, TEXT_INPUTS, publish, open_image, read_pdf

MAX_TEXT = 5 * 1024 * 1024
MAX_PAGES = 200
PAGE_W, PAGE_H, MARGIN, SIZE, LEADING = 595, 842, 54, 11, 13.5          # A4 in points
FONT_CANDIDATES = ('arial.ttf', 'segoeui.ttf', 'Arial.ttf', 'LiberationSans-Regular.ttf', 'DejaVuSans.ttf', 'NotoSans-Regular.ttf', 'Helvetica.ttc')

def read_text(p):
    if p.stat().st_size > MAX_TEXT: raise ConversionError('Text files are limited to 5 MiB.')
    data = p.read_bytes()
    for enc in ('utf-8-sig', 'utf-16') if data[:2] in (b'\xff\xfe', b'\xfe\xff') else ('utf-8-sig', 'cp1252'):
        try: return data.decode(enc).replace('\r\n', '\n').replace('\r', '\n').replace('\t', '    ').replace('\x00', '')
        except UnicodeDecodeError: continue
    return data.decode('latin-1').replace('\r\n', '\n').replace('\r', '\n')

def font_path():
    dirs = [Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts', Path('/usr/share/fonts/truetype/liberation'), Path('/usr/share/fonts/truetype/dejavu'), Path('/usr/share/fonts/truetype/noto'), Path('/usr/share/fonts/TTF'), Path('/Library/Fonts')]
    for d in dirs:
        for name in FONT_CANDIDATES:
            if (d / name).is_file(): return str(d / name)
    return None

def load_font(size):
    from PIL import ImageFont
    path = font_path()
    try: return ImageFont.truetype(path, size) if path else ImageFont.load_default(size)
    except (OSError, TypeError): return ImageFont.load_default()

def layout(text):
    """Greedy word wrap into pages of lines (A4, 54 pt margins, 11 pt)."""
    font = load_font(SIZE * 4);width = (PAGE_W - 2 * MARGIN) * 4
    per_page = int((PAGE_H - 2 * MARGIN) // LEADING);lines = []
    for raw in text.split('\n'):
        if not raw.strip(): lines.append('');continue
        cur = ''
        for word in re.split(r'( +)', raw):
            if not word: continue
            trial = cur + word
            if font.getlength(trial) <= width or not cur.strip(): cur = trial
            else: lines.append(cur.rstrip());cur = word.lstrip()
            while font.getlength(cur) > width and len(cur) > 1:   # one very long word
                cut = len(cur)
                while cut > 1 and font.getlength(cur[:cut]) > width: cut -= 1
                lines.append(cur[:cut]);cur = cur[cut:]
        lines.append(cur.rstrip())
        if len(lines) > per_page * MAX_PAGES: raise ConversionError(f'This text would exceed {MAX_PAGES} pages.')
    pages = [lines[i:i + per_page] for i in range(0, len(lines), per_page)] or [[]]
    if len(pages) > MAX_PAGES: raise ConversionError(f'This text would exceed {MAX_PAGES} pages.')
    return pages

def render_page(lines, scale):
    from PIL import Image, ImageDraw
    im = Image.new('RGB', (round(PAGE_W * scale), round(PAGE_H * scale)), 'white');d = ImageDraw.Draw(im);font = load_font(round(SIZE * scale * 1.0))
    for i, line in enumerate(lines): d.text((MARGIN * scale, (MARGIN + i * LEADING) * scale), line, fill='black', font=font)
    return im

def pdf_escape(s): return s.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')

def text_to_pdf(text, stage):
    pages = layout(text)
    try: [ln.encode('cp1252') for page in pages for ln in page];vector = True
    except UnicodeEncodeError: vector = False
    if vector:
        from pypdf import PdfWriter
        from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
        w = PdfWriter();font = w._add_object(DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica'), NameObject('/Encoding'): NameObject('/WinAnsiEncoding')}))
        for lines in pages:
            page = w.add_blank_page(PAGE_W, PAGE_H);body = [f'BT /F1 {SIZE} Tf {LEADING} TL {MARGIN} {PAGE_H - MARGIN - SIZE} Td']
            for ln in lines: body.append('(' + pdf_escape(ln.encode('cp1252').decode('latin-1')) + ') Tj T*')
            body.append('ET');stream = DecodedStreamObject();stream.set_data('\n'.join(body).encode('latin-1'))
            page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})});page[NameObject('/Contents')] = w._add_object(stream)
        with stage.open('wb') as f: w.write(f)
    else:
        if not font_path(): raise ConversionError('This text needs a system font that could not be found.')
        images = [render_page(p, 150 / 72) for p in pages]
        images[0].save(stage, format='PDF', save_all=True, append_images=images[1:], resolution=150)
    if stage.stat().st_size > MAX_OUTPUT: raise ConversionError('Output exceeded 512 MiB.')

def text_to_image(text, stage, fmt):
    pages = layout(text);scale = 150 / 72;w, h = round(PAGE_W * scale), round(PAGE_H * scale)
    if w * h * len(pages) > MAX_PIXELS: raise ConversionError('This text is too long for one image; convert it to PDF instead.')
    from PIL import Image
    sheet = Image.new('RGB', (w, h * len(pages)), 'white')
    for i, lines in enumerate(pages):
        page = render_page(lines, scale);sheet.paste(page, (0, i * h));page.close()
    sheet.save(stage, format=fmt, **({'quality': 92} if fmt == 'JPEG' else {}));sheet.close()

# ------------------------------------------------------------------------------------------------ subtitles
def stamp(sec):
    ms = int(round(min(max(0, sec), 315_360_000) * 1000));return ms // 3_600_000, ms // 60_000 % 60, ms // 1000 % 60, ms % 1000

def fmt_time(sec, sep): h, m, s, ms = stamp(sec);return f'{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}'

def parse_time(raw):
    parts = raw.strip().replace(',', '.').split(':')
    if not 1 <= len(parts) <= 3: return None
    total = 0.0
    for part in parts:
        try: v = float(part)
        except ValueError: return None
        if v < 0 or v != v or v == float('inf'): return None
        total = total * 60 + v
    return total

def parse_cues(text):
    """Timed cues from SRT/VTT, or one cue per paragraph with invented timings for plain text (as the Mac app does)."""
    lines = text.split('\n')
    if lines and lines[0].lstrip('\ufeff').startswith('WEBVTT'):
        while lines and (lines[0].strip() and '-->' not in lines[0]): lines.pop(0)
    cues = [];i = 0;timed = False
    while i < len(lines):
        line = lines[i].strip()
        if '-->' in line:
            timed = True;a, _, b = line.partition('-->');start = parse_time(a);end = parse_time(b.strip().split(' ')[0]);body = [];i += 1
            while i < len(lines) and lines[i].strip(): body.append(lines[i]);i += 1
            if start is not None and end is not None and end >= start: cues.append((start, end, '\n'.join(body)))
        else: i += 1
    if timed: return cues
    blocks = [b.strip() for b in re.split(r'\n\s*\n', text) if b.strip()];clock = 0.0
    for block in blocks:
        dur = max(1.5, min(8.0, len(block.split()) * .35));cues.append((clock, clock + dur, block));clock += dur
    return cues

def strip_tags(s): return re.sub(r'\{\\[^}]*\}', '', re.sub(r'<[^>]+>', '', s))

def serialize_cues(cues, kind):
    if kind == 'vtt': return 'WEBVTT\n\n' + ''.join(f'{fmt_time(a, ".")} --> {fmt_time(b, ".")}\n{t}\n\n' for a, b, t in cues)
    if kind == 'srt': return ''.join(f'{n}\n{fmt_time(a, ",")} --> {fmt_time(b, ",")}\n{t}\n\n' for n, (a, b, t) in enumerate(cues, 1))
    return '\n\n'.join(strip_tags(t) for _, _, t in cues) + '\n'

def convert_text_subtitle(p, stage, kind):
    text = read_text(p)
    if p.suffix.lower() in ('.srt', '.vtt') and '-->' not in text: raise ConversionError('No subtitle timestamps found.')
    cues = parse_cues(text)
    if not cues: raise ConversionError('No valid subtitle cues were found.')
    stage.write_text(serialize_cues(cues, kind), encoding='utf8')

# ------------------------------------------------------------------------------------------------ PDF to images
def pdf_to_images(p, work, folder, fmt):
    import pypdfium2 as pdfium
    pages = len(read_pdf(p).pages);doc = pdfium.PdfDocument(str(p));staged = [];total = 0
    try:
        for i in range(pages):
            page = doc[i];w, h = page.get_size();scale = min(300 / 72, (MAX_PIXELS / max(w * h, 1)) ** .5)
            im = page.render(scale=scale).to_pil().convert('RGB');page.close();item = Path(work) / f'page-{i}'
            try: im.save(item, format=fmt, **({'quality': 92} if fmt == 'JPEG' else {}))
            finally: im.close()
            total += item.stat().st_size;staged.append(item)
            if total > MAX_OUTPUT: raise ConversionError('Rendered pages exceed 512 MiB.')
    finally: doc.close()
    ext = 'jpg' if fmt == 'JPEG' else 'png'
    if len(staged) == 1: return [publish(staged[0], folder, p.stem + '-converted', ext)]
    return [publish(item, folder, f'{p.stem}-page-{i + 1}', ext) for i, item in enumerate(staged)]

# ------------------------------------------------------------------------------------------------ DOCX
def xml_escape(s): return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
_CTRL = re.compile('[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]')

def drawing(rid, n, name, cx, cy):
    return (f'<w:p><w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/><wp:docPr id="{n}" name="{name}"/>'
            '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            f'<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:nvPicPr><pic:cNvPr id="{n}" name="{name}"/><pic:cNvPicPr/></pic:nvPicPr>'
            f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill><pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>')

def write_docx(blocks, stage):
    """blocks: ('p', text) | ('br',) | ('img', png_path, width_px, height_px). Fixed A4 page, 1-inch margins."""
    body = [];rels = ['<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'];media = []
    for b in blocks:
        if b[0] == 'p': body.append(f'<w:p><w:r><w:t xml:space="preserve">{xml_escape(_CTRL.sub("", b[1]))}</w:t></w:r></w:p>')
        elif b[0] == 'br': body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
        else:
            n = len(media) + 1;name = f'image{n}.png';media.append((name, b[1]));rid = f'rId{n + 9}'
            rels.append(f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{name}"/>')
            cx, cy = max(b[2], 1) * 9525, max(b[3], 1) * 9525;k = min(5_731_510 / cx, 8_863_330 / cy, 1);body.append(drawing(rid, n, name, int(cx * k), int(cy * k)))
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"'
    head = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    with zipfile.ZipFile(stage, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', head + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>')
        z.writestr('_rels/.rels', head + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr('word/document.xml', head + f'<w:document {ns}><w:body>{"".join(body)}<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/></w:sectPr></w:body></w:document>')
        z.writestr('word/styles.xml', head + '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Helvetica" w:hAnsi="Helvetica"/><w:sz w:val="22"/></w:rPr></w:rPrDefault></w:docDefaults><w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style></w:styles>')
        z.writestr('word/_rels/document.xml.rels', head + f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{"".join(rels)}</Relationships>')
        for name, path in media: z.write(path, f'word/media/{name}')
    if stage.stat().st_size > MAX_OUTPUT: raise ConversionError('Output exceeded 512 MiB.')

def image_blocks(p, work):
    from PIL import Image
    im = open_image(p)
    try:
        rgba = im.convert('RGBA');base = Image.new('RGB', rgba.size, 'white');base.paste(rgba, mask=rgba.getchannel('A'));png = Path(work) / 'image.png';base.save(png);size = base.size
    finally: im.close()
    return [('img', png, *size)]

def image_to_docx(p, work, stage): write_docx(image_blocks(p, work), stage)

def pdf_to_docx(p, work, stage): write_docx(pdf_blocks(p, work), stage)

def text_blocks(p): return [('p', ln) for ln in read_text(p).split('\n')]

def file_blocks(p, work):
    """DOCX blocks for an image, PDF or text file; images it renders are written into `work`."""
    suffix = p.suffix.lower()
    if suffix in IMAGE_INPUTS: return image_blocks(p, work)
    if suffix == '.pdf': return pdf_blocks(p, work)
    if suffix in TEXT_INPUTS: return text_blocks(p)
    raise ConversionError('Only images, PDFs and text files can become a Word file.')

def combine_docx(paths, work, stage):
    """One Word file from every input in list order, each starting on a new page."""
    blocks = [];pages = 0
    for i, p in enumerate(paths):
        part = Path(work) / f'part-{i}';part.mkdir()
        try:
            if p.suffix.lower() == '.pdf': pages += len(read_pdf(p).pages)
            if pages > MAX_PAGES: raise ConversionError(f'The combined file cannot exceed {MAX_PAGES} PDF pages.')
            more = file_blocks(p, part)
        except ConversionError as e: raise ConversionError(f'{p.name}: {e}') from e
        blocks += ([('br',)] if blocks else []) + more
    write_docx(blocks, stage)

def pdf_blocks(p, work):
    import pypdfium2 as pdfium
    pdf = read_pdf(p);doc = pdfium.PdfDocument(str(p));blocks = []
    try:
        for i, pg in enumerate(pdf.pages):
            if i: blocks.append(('br',))
            text = (pg.extract_text() or '').strip()
            if text: blocks += [('p', ln.strip()) for ln in text.split('\n')]
            else:
                page = doc[i];w, h = page.get_size();scale = min(150 / 72, (MAX_PIXELS / max(w * h, 1)) ** .5);im = page.render(scale=scale).to_pil().convert('RGB');page.close()
                png = Path(work) / f'page-{i}.png'
                try: im.save(png);blocks.append(('img', png, *im.size))
                finally: im.close()
    finally: doc.close()
    return blocks

# ------------------------------------------------------------------------------------------------ dispatch
def dispatch(target, p, work, stage, folder, stem):
    """Run one document conversion and return the published paths. Called from engine.convert inside the worker."""
    suffix = p.suffix.lower()
    if target == 'Image → DOCX':
        if suffix not in IMAGE_INPUTS: raise ConversionError('This operation requires a supported image.')
        image_to_docx(p, work, stage);return [publish(stage, folder, stem, 'docx')]
    if target in ('PDF → PNG', 'PDF → JPEG', 'PDF → DOCX'):
        if suffix != '.pdf': raise ConversionError('Select a PDF file.')
        if target == 'PDF → DOCX': pdf_to_docx(p, work, stage);return [publish(stage, folder, stem, 'docx')]
        return pdf_to_images(p, work, folder, 'PNG' if target.endswith('PNG') else 'JPEG')
    if target == 'Files → DOCX': write_docx(file_blocks(p, work), stage);return [publish(stage, folder, stem, 'docx')]
    if target == 'Subtitle → Text':
        if suffix not in ('.srt', '.vtt'): raise ConversionError('Select an SRT or VTT file.')
        convert_text_subtitle(p, stage, 'txt');return [publish(stage, folder, stem, 'txt')]
    if suffix not in TEXT_INPUTS: raise ConversionError('Select a plain text file (.txt, .md or .log).')
    if target == 'Text → PDF': text_to_pdf(read_text(p), stage);return [publish(stage, folder, stem, 'pdf')]
    if target in ('Text → PNG', 'Text → JPEG'):
        fmt = 'PNG' if target.endswith('PNG') else 'JPEG';text_to_image(read_text(p), stage, fmt);return [publish(stage, folder, stem, 'png' if fmt == 'PNG' else 'jpg')]
    kind = 'srt' if target == 'Text → SRT' else 'vtt';convert_text_subtitle(p, stage, kind);return [publish(stage, folder, stem, kind)]
