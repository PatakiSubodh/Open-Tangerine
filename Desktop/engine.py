"""Local conversion engine. No shell, network clients, deletion of inputs or archive extraction."""
from __future__ import annotations
import errno, hashlib, json, os, re, shutil, stat, subprocess, tempfile, time, warnings
from pathlib import Path

VERSION = '0.2.2'
MAX_BYTES = 100 * 1024 * 1024
MAX_PIXELS = 40_000_000
MAX_OUTPUT = 512 * 1024 * 1024
MAX_SVG = 5 * 1024 * 1024
OCR_PAGES = 50
OCR_SECONDS = 900
HEIC_INPUTS = {'.heic', '.heif'}
SVG_INPUTS = {'.svg'}
OFFICE_INPUTS = {'.doc', '.docx', '.odt', '.rtf', '.xls', '.xlsx', '.ods', '.ppt', '.pptx', '.odp'}
IMAGE_INPUTS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tif', '.tiff', '.avif'} | HEIC_INPUTS | SVG_INPUTS
IMAGE_OUTPUTS = {'PNG': 'png', 'JPEG': 'jpg', 'WEBP': 'webp', 'TIFF': 'tiff', 'BMP': 'bmp', 'HEIC': 'heic', 'AVIF': 'avif'}
MEDIA_INPUTS = {'.mp4': 'mov', '.mov': 'mov', '.m4v': 'mov', '.mkv': 'matroska', '.webm': 'matroska', '.mp3': 'mp3', '.wav': 'wav', '.flac': 'flac', '.ogg': 'ogg', '.m4a': 'mov', '.aac': 'aac',
               '.gif': 'gif', '.avi': 'avi', '.wmv': 'asf', '.wma': 'asf', '.opus': 'ogg', '.aiff': 'aiff', '.aif': 'aiff'}
MEDIA_OUTPUTS = {'MP4': ('mp4', ['-c:v','libx264','-preset','fast','-crf','23','-c:a','aac','-movflags','+faststart']), 'WEBM': ('webm',['-c:v','libvpx-vp9','-deadline','realtime','-cpu-used','6','-c:a','libopus']), 'MP3': ('mp3',['-vn','-c:a','libmp3lame','-b:a','192k']), 'WAV': ('wav',['-vn','-c:a','pcm_s16le']), 'FLAC': ('flac',['-vn','-c:a','flac']), 'OGG': ('ogg',['-vn','-c:a','libvorbis']),
               'GIF': ('gif',['-an','-t','15','-loop','0','-vf',"fps=12,scale='min(480,iw)':-2:flags=lanczos,split[s0][s1];[s0]palettegen=stats_mode=diff[p];[s1][p]paletteuse"]),
               'MOV': ('mov',['-c:v','libx264','-preset','fast','-crf','23','-pix_fmt','yuv420p','-c:a','aac']),
               'MKV': ('mkv',['-c:v','libx264','-preset','fast','-crf','23','-pix_fmt','yuv420p','-c:a','aac'],'matroska'),
               'AVI': ('avi',['-c:v','mpeg4','-q:v','4','-c:a','libmp3lame','-b:a','192k']),
               'WMV': ('wmv',['-c:v','wmv2','-b:v','2M','-c:a','wmav2','-b:a','192k'],'asf'),
               'M4A': ('m4a',['-vn','-c:a','aac','-b:a','192k'],'ipod'),
               'OPUS': ('opus',['-vn','-c:a','libopus','-b:a','128k']),
               'AIFF': ('aiff',['-vn','-c:a','pcm_s16be']),
               'WMA': ('wma',['-vn','-c:a','wmav2','-b:a','192k'],'asf')}
TEXT_INPUTS = {'.txt', '.md', '.log', '.text'}
DOC_OPERATIONS = ['Image → DOCX', 'PDF → PNG', 'PDF → JPEG', 'PDF → DOCX', 'Text → PDF', 'Text → PNG', 'Text → JPEG', 'Text → SRT', 'Text → VTT', 'Subtitle → Text']
PAGE_PIXELS = {'a4': (1240, 1754)}          # 150 dpi

def on_page(img, size):
    """Centre an RGB image on a white page of `size` pixels, shrinking it to leave a margin."""
    from PIL import Image
    img.thumbnail((size[0] - 120, size[1] - 120), Image.Resampling.LANCZOS);sheet = Image.new('RGB', size, 'white');sheet.paste(img, ((size[0] - img.width) // 2, (size[1] - img.height) // 2));return sheet

OPERATIONS = list(IMAGE_OUTPUTS) + ['Image → PDF', 'PDF → Text', 'OCR → Text', 'OCR → Searchable PDF', 'Merge PDFs', 'Split PDF', 'Office → PDF', 'SRT → VTT', 'VTT → SRT', 'SHA-256'] + list(MEDIA_OUTPUTS) + DOC_OPERATIONS
class ConversionError(ValueError): pass
MEMORY_MESSAGE='This file needs more memory than a conversion is allowed to use. Try a smaller file or a smaller output size.'

def source_file(raw):
    p=Path(raw).expanduser()
    # Reject devices, symlinks, Windows reparse points and remote UNC paths.
    if not p.is_absolute(): raise ConversionError('Select an absolute local file path.')
    if os.name=='nt' and (str(p).startswith('\\\\') or str(p).startswith('//')): raise ConversionError('Network paths are not supported.')
    s=p.lstat()
    if not stat.S_ISREG(s.st_mode) or p.is_symlink() or getattr(s,'st_file_attributes',0)&0x400:
        raise ConversionError('Select a regular file, not a folder, shortcut or device.')
    if s.st_size==0 or s.st_size>MAX_BYTES: raise ConversionError('Files must be nonempty and no larger than 100 MiB.')
    return checked_resolve(p, s)

def checked_resolve(path, before):
    """Detect replacement during canonicalization; not a filesystem sandbox."""
    resolved=path.resolve(strict=True)
    after=path.lstat();actual=resolved.stat()
    if (before.st_dev,before.st_ino)!=(after.st_dev,after.st_ino) or (before.st_dev,before.st_ino)!=(actual.st_dev,actual.st_ino) or stat.S_ISLNK(after.st_mode) or getattr(after,'st_file_attributes',0)&0x400:
        raise ConversionError('Path changed while being checked; select it again.')
    return resolved

def output_folder(raw):
    folder=Path(raw)
    if not folder.is_absolute():raise ConversionError('Choose an absolute local output folder.')
    info=folder.lstat()
    if not stat.S_ISDIR(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:
        raise ConversionError('Choose a real local output folder; symbolic links and shortcuts are not supported.')
    return checked_resolve(folder,info)

def publish(stage, folder, stem, suffix):
    """Never overwrite. Prefer atomic hardlink; exclusive copy supports removable disks."""
    if not stage.is_file() or not 0<stage.stat().st_size<=MAX_OUTPUT: raise ConversionError('Empty or oversized output.')
    stem=re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', stem).rstrip('. ')[:100] or 'converted'
    if stem.upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}: stem='file-'+stem
    for n in range(1,10001):
        target=folder/(stem+('-'+str(n) if n>1 else '')+'.'+suffix)
        try:
            os.link(stage,target)
            return str(target)
        except FileExistsError: continue
        except OSError as e:
            if e.errno not in (errno.EPERM,errno.EOPNOTSUPP,errno.EXDEV,errno.ENOSYS):
                raise ConversionError('Cannot write to the output folder. Check permissions and free space.') from e
            try:
                fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_BINARY',0),0o600)
            except FileExistsError:continue
            identity=os.fstat(fd)
            try:
                with os.fdopen(fd,'wb') as out, stage.open('rb') as source:
                    shutil.copyfileobj(source,out,1024*1024)
                    out.flush();os.fsync(out.fileno())
                return str(target)
            except BaseException:
                # Remove only the incomplete file this call created, never a replacement.
                try:
                    current=target.lstat()
                    if (current.st_dev,current.st_ino)==(identity.st_dev,identity.st_ino):target.unlink()
                except OSError:pass
                raise
    raise ConversionError('Too many existing output names; choose another folder.')

def render_svg(p, width=0):
    """Rasterize with Qt's SVG renderer; it fetches no network resources."""
    if p.stat().st_size>MAX_SVG: raise ConversionError('SVG files must be under 5 MiB.')
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtCore import QByteArray
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QApplication
    from PySide6.QtSvg import QSvgRenderer
    from PIL import Image
    QApplication.instance() or QApplication([])
    renderer=QSvgRenderer(QByteArray(p.read_bytes()))
    size=renderer.defaultSize()
    if not renderer.isValid() or size.width()<=0 or size.height()<=0: raise ConversionError('Invalid SVG, or it has no width/height or viewBox.')
    w,h=size.width(),size.height()
    if width: scale=width/max(w,h);w,h=max(1,round(w*scale)),max(1,round(h*scale))
    if w*h>MAX_PIXELS: raise ConversionError('SVG would exceed 40 megapixels; choose a smaller maximum side.')
    canvas=QImage(w,h,QImage.Format_ARGB32_Premultiplied);canvas.fill(0)
    painter=QPainter(canvas);renderer.render(painter);painter.end()
    canvas=canvas.convertToFormat(QImage.Format_RGBA8888)
    return Image.frombuffer('RGBA',(w,h),bytes(canvas.constBits()),'raw','RGBA',canvas.bytesPerLine(),1).copy()

def open_image(p, width=0):
    from PIL import Image, ImageOps
    suffix=p.suffix.lower()
    if suffix in SVG_INPUTS: return render_svg(p,width)
    if suffix in HEIC_INPUTS:
        import pillow_heif
        pillow_heif.register_heif_opener()
    Image.MAX_IMAGE_PIXELS=MAX_PIXELS
    warnings.simplefilter('error', Image.DecompressionBombWarning)
    with Image.open(p) as im:
        if im.width*im.height>MAX_PIXELS: raise ConversionError('Image exceeds 40 megapixels.')
        # HEIC may bundle extra images (bursts, depth); only the primary image is converted.
        if suffix not in HEIC_INPUTS and getattr(im,'n_frames',1)!=1: raise ConversionError('Animated or multipage images are not supported; use a single-frame image.')
        im.load()
        result=ImageOps.exif_transpose(im).copy()
    return result

TOOLS = {  # settings key -> (display name, executable names, install hint)
    'ffmpeg': ('FFmpeg', ['ffmpeg'], 'winget install Gyan.FFmpeg'),
    'tesseract': ('Tesseract OCR', ['tesseract'], 'winget install UB-Mannheim.TesseractOCR'),
    'soffice': ('LibreOffice', ['soffice', 'libreoffice'], 'winget install TheDocumentFoundation.LibreOffice')}

def _tool_dirs(key):
    """Standard install folders. PATH is searched separately, and only through absolute entries (never the current folder)."""
    env=os.environ.get;pf=[env('ProgramFiles',r'C:\Program Files'),env('ProgramFiles(x86)',r'C:\Program Files (x86)')];local=env('LOCALAPPDATA','')
    if os.name=='nt':
        if key=='tesseract': return [Path(d)/'Tesseract-OCR' for d in pf]+[Path(local)/'Programs'/'Tesseract-OCR']
        if key=='soffice': return [Path(d)/'LibreOffice'/'program' for d in pf]
        winget=Path(local)/'Microsoft'/'WinGet'
        found=[winget/'Links']+[b for pkg in sorted((winget/'Packages').glob('*FFmpeg*')) for b in pkg.glob('**/bin')]
        return found+[Path(d)/'ffmpeg'/'bin' for d in pf]+[Path(r'C:\ffmpeg\bin'),Path(env('ProgramData',r'C:\ProgramData'))/'chocolatey'/'bin']
    return [Path(d) for d in ('/usr/bin','/usr/local/bin','/opt/homebrew/bin','/snap/bin','/opt/libreoffice/program','/Applications/LibreOffice.app/Contents/MacOS')]

def find_tool(key):
    """Locate a helper on PATH or in its usual install folder. Returns a resolved absolute Path or None."""
    exts=['.exe','.bat','.cmd'] if os.name=='nt' else ['']
    path_dirs=[Path(d) for d in os.environ.get('PATH','').split(os.pathsep) if d and Path(d).is_absolute()]
    for folder in path_dirs+_tool_dirs(key):
        for name in TOOLS[key][1]:
            for ext in exts:
                try:
                    candidate=folder/(name+ext)
                    # Shims such as WinGet's Links folder are symlinks; follow them once, then validate the real file.
                    if candidate.is_file() and os.access(candidate,os.X_OK): return candidate.resolve(strict=True)
                except OSError: continue
    return None

def tool_path(raw, name, key=None):
    """A user-chosen executable wins; otherwise fall back to an installed copy if one can be found."""
    if not raw and key:
        found=find_tool(key)
        if found: return found
    if not raw:
        hint=TOOLS[key][2] if key in TOOLS else ''
        raise ConversionError(f'{name} was not found. Install it'+(f' (for example: {hint})' if hint and os.name=='nt' else '')+', then pick it in Settings if it is not detected automatically.')
    exe=Path(raw)
    if not exe.is_absolute() or not exe.is_file() or exe.is_symlink(): raise ConversionError(f'{name} must be an existing absolute executable path.')
    return exe

def run_external(cmd, deadline, cwd=None, tail=500):
    """Run a user-selected helper without a shell; the whole process tree dies at the deadline."""
    from runner import stop
    kwargs={'start_new_session':True} if os.name!='nt' else {'creationflags':subprocess.CREATE_NO_WINDOW}
    with tempfile.TemporaryFile() as log:
        proc=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=log,stderr=log,cwd=cwd,**kwargs)
        try:
            while proc.poll() is None:
                if time.monotonic()>deadline or log.tell()>65536: raise ConversionError('External tool exceeded its time or diagnostic limit.')
                time.sleep(.05)
            log.seek(0)
            return proc.returncode,log.read(65536).decode('utf8','replace')[-tail:]
        finally: stop(proc)

def tesseract_languages(exe):
    """Installed OCR language codes, or [] if the helper cannot list them."""
    try:
        kw={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
        r=subprocess.run([str(exe),'--list-langs'],stdin=subprocess.DEVNULL,capture_output=True,timeout=15,**kw)
        return [l.strip() for l in (r.stdout+r.stderr).decode('utf8','replace').splitlines()[1:] if re.fullmatch(r'[A-Za-z_]{3,16}',l.strip())]
    except Exception: return []

def prepare_ocr_image(im):
    """Flatten transparency, enlarge small images (screenshots) towards ~300 dpi text, fix dark-on-light polarity and stretch contrast.
    Returns (image, dpi); the dpi keeps a searchable PDF page at its original physical size."""
    from PIL import Image, ImageOps, ImageStat
    rgba=im.convert('RGBA');base=Image.new('RGB',rgba.size,'white');base.paste(rgba,mask=rgba.getchannel('A'))
    longest=max(base.size);factor=1.0
    if longest<2400: factor=min(3.0,2400/longest,(25_000_000/(base.width*base.height))**.5)
    if factor>1.05: base=base.resize((round(base.width*factor),round(base.height*factor)),Image.Resampling.LANCZOS)
    else: factor=1.0
    gray=ImageOps.autocontrast(base.convert('L'),cutoff=1)
    # Tesseract reads dark text on a light page; light-on-dark (dark-mode screenshots) is inverted first.
    if ImageStat.Stat(gray).mean[0]<110: gray=ImageOps.invert(gray)
    return gray,round(300*factor)

def ocr_text(p, work, stage, tesseract, lang, searchable=False):
    exe=tool_path(tesseract,'Tesseract','tesseract')
    if not re.fullmatch(r'[A-Za-z_]{3,16}(\+[A-Za-z_]{3,16}){0,2}',lang): raise ConversionError('Invalid OCR language code (for example eng or eng+deu).')
    work=Path(work);texts=[];pdfs=[]
    def recognize(image,n,dpi,deadline):
        png=work/f'ocr-{n}.png';image.save(png,dpi=(dpi,dpi))
        # Text mode retries sparse layouts (a single block, then scattered words) when the page layout guess finds nothing.
        for psm in (('3',) if searchable else ('3','6','11')):
            base=work/f'text-{n}-{psm}'
            code,detail=run_external([str(exe),str(png),str(base),'-l',lang,'--psm',psm,'--dpi',str(dpi),'-c','preserve_interword_spaces=1',*(['pdf'] if searchable else [])],deadline,cwd=work)
            out=work/(base.name+('.pdf' if searchable else '.txt'))
            if code or not out.is_file():
                if re.search(r'Failed loading language|Error opening data file|Could not initialize tesseract',detail):
                    have=', '.join(l for l in tesseract_languages(exe) if l!='osd') or 'none found'
                    raise ConversionError(f'Tesseract has no data for language "{lang}". Installed: {have}. Add the .traineddata file to the Tesseract tessdata folder, or change the OCR language.')
                raise ConversionError('Tesseract could not read this file. Check the language data is installed. '+detail)
            if searchable: pdfs.append(out);return
            text=out.read_text(encoding='utf8',errors='replace').rstrip()
            text=re.sub(r'[\x00-\x08\x0b-\x1f]','',text)  # Tesseract ends each page with a form feed
            if text.strip(): texts.append(text);return
        texts.append('')
    if p.suffix.lower()=='.pdf':
        import pypdfium2 as pdfium
        pages=len(read_pdf(p).pages)
        if pages>OCR_PAGES: raise ConversionError(f'OCR is limited to {OCR_PAGES} pages per PDF.')
        deadline=time.monotonic()+min(OCR_SECONDS-30,60+25*pages)
        doc=pdfium.PdfDocument(str(p))
        try:
            for i in range(pages):
                page=doc[i];w,h=page.get_size()
                # 300 dpi, shrunk if the page would exceed the pixel budget.
                scale=min(300/72,(MAX_PIXELS/max(w*h,1))**.5)
                image,_=prepare_ocr_image(page.render(scale=scale).to_pil());page.close()
                recognize(image,i,round(72*scale),deadline)
        finally: doc.close()
    elif p.suffix.lower() in IMAGE_INPUTS:
        im=open_image(p)
        try: image,dpi=prepare_ocr_image(im)
        finally: im.close()
        recognize(image,0,dpi,time.monotonic()+120)
    else: raise ConversionError('OCR requires a PDF or an image.')
    if searchable:
        from pypdf import PdfWriter
        writer=PdfWriter()
        for part in pdfs:
            for page in read_pdf(part).pages: writer.add_page(page)
        with stage.open('wb') as f: writer.write(f)
        return
    text='\n\n'.join(t for t in texts if t)
    if not text.strip(): raise ConversionError('No text was recognized. Try a sharper or larger image, or check the OCR language.')
    stage.write_text(text+'\n',encoding='utf8')

def office_pdf(p, work, stage, soffice):
    exe=tool_path(soffice,'LibreOffice','soffice')
    if p.suffix.lower() not in OFFICE_INPUTS: raise ConversionError('Select a Word, Excel, PowerPoint or OpenDocument file.')
    work=Path(work);src=work/'in';out=work/'out';src.mkdir();out.mkdir()
    # Neutral name, private copy and throwaway profile: the original's folder is never touched.
    local=src/('input'+p.suffix.lower());shutil.copyfile(p,local)
    cmd=[str(exe),'--headless','--norestore','--nolockcheck','--nologo','--nofirststartwizard',f'-env:UserInstallation={(work/"profile").as_uri()}','--convert-to','pdf','--outdir',str(out),str(local)]
    code,detail=run_external(cmd,time.monotonic()+150,cwd=work)
    result=out/'input.pdf'
    if code or not result.is_file(): raise ConversionError('LibreOffice could not convert this file. '+detail)
    read_pdf(result);os.replace(result,stage)

def read_pdf(p):
    from pypdf import PdfReader
    pdf=PdfReader(str(p),strict=False)
    if pdf.is_encrypted: raise ConversionError('Password-protected PDFs are not supported.')
    if not 0<len(pdf.pages)<=200: raise ConversionError('PDFs must contain 1–200 pages.')
    return pdf

def media(p, stage, target, ffmpeg):
    exe=tool_path(ffmpeg,'FFmpeg','ffmpeg')
    if p.suffix.lower() not in MEDIA_INPUTS: raise ConversionError('Unsupported media input; playlists and URLs are not accepted.')
    ext,args,*rest=MEDIA_OUTPUTS[target];muxer=rest[0] if rest else ext
    if p.suffix.lower()=='.gif' and ext!='gif': args=['-vf','scale=trunc(iw/2)*2:trunc(ih/2)*2','-pix_fmt','yuv420p',*args]
    # Input demuxer selected explicitly; network protocols unavailable to the job.
    cmd=[str(exe),'-nostdin','-hide_banner','-loglevel','error','-n','-protocol_whitelist','file,pipe','-threads','1','-filter_threads','1','-filter_complex_threads','1','-f',MEDIA_INPUTS[p.suffix.lower()],'-i',str(p),'-map_metadata','-1','-threads','1',*args,'-fs',str(MAX_OUTPUT),'-f',muxer,str(stage)]
    with tempfile.TemporaryFile() as log:
        proc=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=log)
        start=time.monotonic()
        try:
            while proc.poll() is None:
                if time.monotonic()-start>150 or log.tell()>65536 or (stage.exists() and stage.stat().st_size>=MAX_OUTPUT):
                    raise ConversionError('Media job exceeded its time, output or diagnostic limit.')
                time.sleep(.05)
            if proc.returncode:
                log.seek(0);detail=log.read(2000).decode('utf8','replace')
                raise ConversionError(('FFmpeg reached a memory/thread resource limit. Try a smaller file. ' if 'pthread_create' in detail or 'Cannot allocate memory' in detail else 'FFmpeg could not convert this file; check the file and installed codecs. ')+detail[-500:])
        finally:
            if proc.poll() is None: proc.kill()
            proc.wait()
    if stage.stat().st_size>=MAX_OUTPUT: raise ConversionError('Output exceeded 512 MiB; no partial file was published.')

def convert(job):
    target=job.get('target')
    if target not in OPERATIONS: raise ConversionError('Unsupported operation.')
    raws=job.get('paths',[])
    if not isinstance(raws,list) or not 1<=len(raws)<=100: raise ConversionError('Select 1–100 files.')
    paths=[source_file(p) for p in raws]
    if target!='Merge PDFs' and len(paths)!=1: raise ConversionError('Each conversion job accepts one input; use the batch queue.')
    folder=output_folder(job.get('output') or paths[0].parent)
    work_root=folder
    if job.get('_work_root'):
        work_root=output_folder(job['_work_root'])
        if work_root.parent!=folder or not work_root.name.startswith('.opentangerine-job-'):
            raise ConversionError('Invalid job staging folder.')
    p=paths[0]; stem=p.stem+'-converted';results=[]
    with tempfile.TemporaryDirectory(prefix='.opentangerine-',dir=work_root) as work:
        stage=Path(work)/'output'
        if target in IMAGE_OUTPUTS or target=='Image → PDF':
            if p.suffix.lower() not in IMAGE_INPUTS: raise ConversionError('This operation requires a supported image.')
            from PIL import Image
            width=int(job.get('width',0));rotation=int(job.get('rotation',0));quality=int(job.get('quality',90))
            if not 0<=width<=10000 or rotation not in (0,90,180,270) or not 1<=quality<=100: raise ConversionError('Invalid image options.')
            im=open_image(p,width)
            try:
                if width: im.thumbnail((width,width),Image.Resampling.LANCZOS)
                if rotation: im=im.rotate(-rotation,expand=True)
                if target in ('JPEG','BMP','Image → PDF'):
                    rgba=im.convert('RGBA');base=Image.new('RGB',rgba.size,'white');base.paste(rgba,mask=rgba.getchannel('A'));im=base
                elif im.mode not in (('RGB','RGBA','L') if target in ('HEIC','AVIF') else ('RGB','RGBA','L','LA')): im=im.convert('RGBA')
                if target in ('HEIC','AVIF'):
                    import pillow_heif
                    pillow_heif.register_heif_opener()
                # Drop ancillary metadata; this is not a certified anonymizer.
                im.info.clear()
                if target=='Image → PDF': im=on_page(im,PAGE_PIXELS['a4'])
                fmt='PDF' if target=='Image → PDF' else 'HEIF' if target=='HEIC' else target
                im.save(stage,format=fmt,quality=quality,**({'resolution':150} if fmt=='PDF' else {}))
                ext='pdf' if fmt=='PDF' else IMAGE_OUTPUTS[target]
                results.append(publish(stage,folder,stem,ext))
            finally: im.close()
        elif target in ('PDF → Text','Merge PDFs','Split PDF'):
            if any(x.suffix.lower()!='.pdf' for x in paths): raise ConversionError('Select only PDF files.')
            from pypdf import PdfWriter
            if target=='Merge PDFs':
                writer=PdfWriter();total=0
                for path in paths:
                    pdf=read_pdf(path);total+=len(pdf.pages)
                    if total>200: raise ConversionError('Merged PDF cannot exceed 200 pages.')
                    for page in pdf.pages: writer.add_page(page)
                with stage.open('wb') as f: writer.write(f)
                results.append(publish(stage,folder,'merged','pdf'))
            else:
                pdf=read_pdf(p)
                if target=='PDF → Text':
                    with stage.open('w',encoding='utf8') as f:
                        for page in pdf.pages:
                            f.write(page.extract_text() or '');f.write('\n')
                            if f.tell()>MAX_OUTPUT: raise ConversionError('Extracted text is too large.')
                    results.append(publish(stage,folder,stem,'txt'))
                else:
                    # Prepare all pages before publishing; no output before parser success.
                    pieces=[]
                    for i,page in enumerate(pdf.pages):
                        item=Path(work)/str(i);w=PdfWriter();w.add_page(page)
                        with item.open('wb') as f:w.write(f)
                        pieces.append(item)
                        if sum(x.stat().st_size for x in pieces)>MAX_OUTPUT: raise ConversionError('Split outputs exceed 512 MiB.')
                    for i,item in enumerate(pieces):results.append(publish(item,folder,f'{p.stem}-page-{i+1}','pdf'))
        elif target in DOC_OPERATIONS:
            import docops
            results.extend(docops.dispatch(target,p,work,stage,folder,stem))
        elif target in ('OCR → Text','OCR → Searchable PDF'):
            searchable=target.endswith('PDF');ocr_text(p,work,stage,job.get('tesseract',''),job.get('ocr_lang') or 'eng',searchable);results.append(publish(stage,folder,stem+('-searchable' if searchable else ''),'pdf' if searchable else 'txt'))
        elif target=='Office → PDF':
            office_pdf(p,work,stage,job.get('soffice',''));results.append(publish(stage,folder,stem,'pdf'))
        elif target in MEDIA_OUTPUTS:
            media(p,stage,target,job.get('ffmpeg',''));results.append(publish(stage,folder,stem,MEDIA_OUTPUTS[target][0]))
        elif target=='SHA-256':
            h=hashlib.sha256()
            with p.open('rb') as f:
                for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
            if any(c in p.name for c in ('\n','\r','\\')):
                raise ConversionError('Rename this file without newlines or backslashes before creating a checksum.')
            stage.write_text(h.hexdigest()+'  '+p.name+'\n',encoding='utf8')
            results.append(publish(stage,folder,p.stem,'sha256'))
        else:
            expected='.srt' if target=='SRT → VTT' else '.vtt'
            if p.suffix.lower()!=expected or p.stat().st_size>5*1024*1024: raise ConversionError('Select a matching subtitle file under 5 MiB.')
            value=p.read_text(encoding='utf-8-sig');value=value.replace('\r\n','\n')
            if target=='SRT → VTT':
                if '-->' not in value: raise ConversionError('No subtitle timestamps found.')
                lines=value.splitlines()
                for i,line in enumerate(lines):
                    if '-->' not in line:continue
                    m=re.fullmatch(r'((?:\d{2,}:)?\d{2}:\d{2}),([0-9]{3}) --> ((?:\d{2,}:)?\d{2}:\d{2}),([0-9]{3})',line)
                    if not m:raise ConversionError('Only simple SRT timestamps are supported.')
                    times=[]
                    for t,ms in ((m[1],m[2]),(m[3],m[4])):
                        if any(int(v)>59 for v in t.split(':')[-2:]):raise ConversionError('Invalid subtitle timestamp.')
                        times.append(('00:'+t if t.count(':')==1 else t)+'.'+ms)
                    lines[i]=' --> '.join(times)
                value='\n'.join(lines)+'\n'
                value='WEBVTT\n\n'+value;ext='vtt'
            else:
                if not value.startswith('WEBVTT') or '-->' not in value: raise ConversionError('Invalid WebVTT file.')
                blocks=value.split('\n\n')[1:];out=[]
                for block in blocks:
                    lines=block.strip().splitlines();stamp=next((i for i,l in enumerate(lines) if '-->' in l),None)
                    if stamp is None: continue
                    timing=lines[stamp]
                    # Cue settings/styles are deliberately not silently discarded.
                    m=re.fullmatch(r'((?:\d{2}:)?\d{2}:\d{2}\.\d{3}) --> ((?:\d{2}:)?\d{2}:\d{2}\.\d{3})',timing)
                    if not m: raise ConversionError('Only simple WebVTT cues without positioning settings are supported.')
                    times=[('00:'+v if v.count(':')==1 else v).replace('.',',') for v in m.groups()]
                    out.append(str(len(out)+1)+'\n'+' --> '.join(times)+'\n'+'\n'.join(lines[stamp+1:]))
                if not out: raise ConversionError('No supported subtitle cues.')
                value='\n\n'.join(out)+'\n';ext='srt'
            stage.write_text(value,encoding='utf8');results.append(publish(stage,folder,stem,ext))
    return results

def worker_main():
    import sys
    try:
        if sys.platform.startswith('linux'):
            import resource
            resource.setrlimit(resource.RLIMIT_AS,(1536*1024*1024,1536*1024*1024))
            resource.setrlimit(resource.RLIMIT_FSIZE,(MAX_OUTPUT,MAX_OUTPUT))
            resource.setrlimit(resource.RLIMIT_CPU,(160,160))
        raw=sys.stdin.buffer.read(65537)
        if len(raw)>65536: raise ConversionError('Job request too large.')
        result={'ok':True,'outputs':convert(json.loads(raw))}
    except MemoryError: result={'ok':False,'error':MEMORY_MESSAGE}
    except Exception as e: result={'ok':False,'error':str(e)[:1000] or type(e).__name__}
    print(json.dumps(result,ensure_ascii=True),flush=True)
    return 0 if result['ok'] else 1
