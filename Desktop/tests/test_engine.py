from unittest import mock
import concurrent.futures, hashlib, json, os, shutil, subprocess, sys, tempfile, threading, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import convert, source_file, publish, ConversionError, MAX_BYTES
from runner import run_job, Cancelled
from PIL import Image
from pypdf import PdfReader, PdfWriter

class ConversionTests(unittest.TestCase):
    def setUp(self):
        # Tests must not pick up helper programs installed on the developer's machine.
        patcher=mock.patch('engine.find_tool',return_value=None);patcher.start();self.addCleanup(patcher.stop)
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve();self.src=self.root/'源 image ; $danger.png';Image.new('RGBA',(32,24),(255,0,0,128)).save(self.src)
    def tearDown(self):self.tmp.cleanup()
    def job(self,target,paths=None,**kw):return dict(paths=[str(p) for p in (paths or [self.src])],target=target,output=str(self.root),**kw)
    def pdf(self,name='input.pdf',pages=2):
        p=self.root/name;w=PdfWriter()
        for _ in range(pages):w.add_blank_page(100,100)
        with p.open('wb') as f:w.write(f)
        return p
    def test_all_image_outputs(self):
        for target in ('PNG','JPEG','WEBP','TIFF','BMP'):
            with self.subTest(target=target):
                p=Path(convert(self.job(target))[0]);im=Image.open(p);im.load();self.assertEqual(im.size,(32,24));im.close()
    def test_jpeg_alpha_white(self):
        p=convert(self.job('JPEG'))[0]
        with Image.open(p) as im:self.assertGreater(im.getpixel((0,0))[1],100)
    def test_resize_rotate(self):
        p=convert(self.job('PNG',width=16,rotation=90))[0]
        with Image.open(p) as im:self.assertEqual(im.size,(12,16))
    def test_original_unchanged(self):
        before=self.src.read_bytes();convert(self.job('JPEG'));self.assertEqual(before,self.src.read_bytes())
    def test_never_overwrite(self):
        a=Path(convert(self.job('JPEG'))[0]);before=a.read_bytes();b=convert(self.job('JPEG'))[0];self.assertNotEqual(str(a),b);self.assertEqual(a.read_bytes(),before)
    def test_parallel_publication(self):
        stage=self.root/'stage';stage.write_bytes(b'safe')
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:out=list(pool.map(lambda _:publish(stage,self.root,'same','txt'),range(20)))
        self.assertEqual(len(set(out)),20);self.assertTrue(all(Path(p).read_bytes()==b'safe' for p in out))
    def test_image_pdf(self):self.assertEqual(len(PdfReader(convert(self.job('Image → PDF'))[0]).pages),1)
    def test_image_pdf_is_a4(self):
        page=PdfReader(convert(self.job('Image → PDF'))[0]).pages[0];self.assertAlmostEqual(float(page.mediabox.width),595.2,delta=1);self.assertAlmostEqual(float(page.mediabox.height),842.0,delta=1)
    def test_pdf_merge_split_text(self):
        a=self.pdf();b=self.pdf('two.pdf',1);merged=convert(self.job('Merge PDFs',[a,b]))[0];self.assertEqual(len(PdfReader(merged).pages),3)
        pages=convert(self.job('Split PDF',[a]));self.assertEqual(len(pages),2);self.assertTrue(all(len(PdfReader(p).pages)==1 for p in pages))
        text=convert(self.job('PDF → Text',[a]))[0];self.assertTrue(Path(text).exists())
    def test_encrypted_pdf(self):
        p=self.root/'locked.pdf';w=PdfWriter();w.add_blank_page(100,100);w.encrypt('password')
        with p.open('wb') as f:w.write(f)
        with self.assertRaisesRegex(ConversionError,'Password'):convert(self.job('PDF → Text',[p]))
    def test_pdf_page_limit(self):
        with self.assertRaisesRegex(ConversionError,'200'):convert(self.job('Split PDF',[self.pdf(pages=201)]))
    def test_subtitle_roundtrip(self):
        p=self.root/'字幕.srt';p.write_text('1\n00:00:01,000 --> 00:00:02,000\nHello\n',encoding='utf8');vtt=Path(convert(self.job('SRT → VTT',[p]))[0]);srt=Path(convert(self.job('VTT → SRT',[vtt]))[0]);self.assertIn('00:00:01,000 --> 00:00:02,000',srt.read_text())
    def test_reject_vtt_cue_settings(self):
        p=self.root/'cue.vtt';p.write_text('WEBVTT\n\n00:00:01.000 --> 00:00:02.000 align:start\nhi')
        with self.assertRaises(ConversionError):convert(self.job('VTT → SRT',[p]))
    def test_hash(self):
        p=Path(convert(self.job('SHA-256'))[0]);self.assertTrue(p.read_text(encoding='utf8').startswith(hashlib.sha256(self.src.read_bytes()).hexdigest()))
    def test_corrupt_image(self):
        self.src.write_text('not an image')
        with self.assertRaises(Exception):convert(self.job('JPEG'))
        self.assertFalse(list(self.root.glob('*converted*')))
    def test_unsupported_svg(self):
        p=self.root/'bad.svg';p.write_text('<svg/>')
        with self.assertRaises(ConversionError):convert(self.job('PNG',[p]))
    def test_symlink_input(self):
        p=self.root/'link.png'
        try:p.symlink_to(self.src)
        except OSError:self.skipTest('Account cannot create symbolic links')
        with self.assertRaises(ConversionError):source_file(p)
    def test_symlink_destination_not_followed(self):
        stage=self.root/'stage';stage.write_bytes(b'converted');victim=self.root/'victim';victim.write_bytes(b'original');link=self.root/'output.txt'
        try:link.symlink_to(victim)
        except OSError:self.skipTest('Account cannot create symbolic links')
        dest=publish(stage,self.root,'output','txt');self.assertNotEqual(dest,str(link));self.assertEqual(victim.read_bytes(),b'original')
    def test_empty_large_directory_relative(self):
        p=self.root/'empty';p.touch()
        for path in (p,self.root,Path('relative.png')):
            with self.assertRaises(Exception):source_file(path)
        with p.open('wb') as f:f.truncate(MAX_BYTES+1)
        with self.assertRaises(ConversionError):source_file(p)
    def test_image_bomb_limit(self):
        # Header-only PNG with excessive dimensions fails before allocating pixels.
        import struct,zlib
        data=struct.pack('>IIBBBBB',10000,10000,8,2,0,0,0);crc=zlib.crc32(b'IHDR'+data)
        self.src.write_bytes(b'\x89PNG\r\n\x1a\n'+struct.pack('>I',13)+b'IHDR'+data+struct.pack('>I',crc))
        with self.assertRaises(Exception):convert(self.job('PNG'))
    def test_bad_target_and_options(self):
        for target,opts in [('evil',{}),('JPEG',{'rotation':13}),('JPEG',{'width':999999})]:
            with self.assertRaises(ConversionError):convert(self.job(target,**opts))
    def test_missing_ffmpeg(self):
        with self.assertRaisesRegex(ConversionError,'FFmpeg'):convert(self.job('MP3'))
    def test_subprocess_worker(self):
        result=run_job(self.job('JPEG'));self.assertTrue(Path(result[0]).is_file())
    def test_worker_failure_then_success(self):
        bad=self.root/'bad.png';bad.write_bytes(b'broken')
        with self.assertRaises(ValueError):run_job(self.job('JPEG',[bad]))
        self.assertTrue(run_job(self.job('JPEG')))
    def test_timeout(self):
        with self.assertRaises(TimeoutError):run_job({},timeout=.15,command=[sys.executable,'-c','import time;time.sleep(30)'])
    def test_cancellation(self):
        event=threading.Event();event.set()
        with self.assertRaises(Cancelled):run_job({},cancel=event,command=[sys.executable,'-c','import time;time.sleep(30)'])
    def test_media_wav_to_flac(self):
        ff=shutil.which('ffmpeg') or ('/opt/homebrew/bin/ffmpeg' if Path('/opt/homebrew/bin/ffmpeg').exists() else None)
        if not ff:self.skipTest('FFmpeg not installed')
        import wave
        p=self.root/'sample.wav'
        with wave.open(str(p),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000);w.writeframes(b'\0\0'*8000)
        out=run_job(self.job('FLAC',[p],ffmpeg=ff));self.assertEqual(Path(out[0]).read_bytes()[:4],b'fLaC')
    def test_all_media_outputs(self):
        ff=shutil.which('ffmpeg') or ('/opt/homebrew/bin/ffmpeg' if Path('/opt/homebrew/bin/ffmpeg').exists() else None)
        if not ff:self.skipTest('FFmpeg not installed')
        p=self.root/'video.mp4'
        subprocess.run([ff,'-nostdin','-v','error','-f','lavfi','-i','color=c=orange:s=64x64:r=12','-f','lavfi','-i','sine=frequency=440:sample_rate=24000','-t','0.5','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(p)],check=True)
        for target in ('MP4','WEBM','MP3','WAV','FLAC','OGG'):
            with self.subTest(target=target):
                output=run_job(self.job(target,[p],ffmpeg=ff))[0]
                subprocess.run([ff,'-nostdin','-v','error','-xerror','-i',output,'-f','null','-'],check=True)
    def test_animated_image_rejected(self):
        p=self.root/'animated.webp'
        a=Image.new('RGB',(8,8),'red');b=Image.new('RGB',(8,8),'blue');a.save(p,save_all=True,append_images=[b],duration=100,loop=0)
        with self.assertRaisesRegex(ConversionError,'Animated'):convert(self.job('JPEG',[p]))
    def test_batch_limit(self):
        with self.assertRaises(ConversionError):convert(self.job('Merge PDFs',[self.src]*101))
    def tool(self,name,body):
        """Stand-in for a user-installed helper: a launcher that runs a Python script with the exact arguments."""
        script=self.root/(name+'.py');script.write_text(body,encoding='utf8')
        if os.name=='nt':launcher=self.root/(name+'.bat');launcher.write_text(f'@"{sys.executable}" "{script}" %*\r\n')
        else:launcher=self.root/name;launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n');launcher.chmod(0o755)
        return str(launcher)
    def test_heic_roundtrip(self):
        heic=Path(convert(self.job('HEIC'))[0]);self.assertEqual(heic.suffix,'.heic')
        back=Path(convert(self.job('PNG',[heic]))[0])
        with Image.open(back) as im:self.assertEqual(im.size,(32,24))
    def test_heic_corrupt(self):
        p=self.root/'bad.heic';p.write_bytes(b'not heic at all')
        with self.assertRaises(Exception):convert(self.job('PNG',[p]))
        self.assertFalse(list(self.root.glob('*converted*')))
    def svg(self,body='<rect width="40" height="20" fill="#ff0000"/>',size='width="40" height="20"'):
        p=self.root/'drawing.svg';p.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" {size}>{body}</svg>');return p
    def test_svg_to_png_pdf_and_size(self):
        p=self.svg()
        with Image.open(convert(self.job('PNG',[p]))[0]) as im:self.assertEqual(im.size,(40,20));self.assertEqual(im.convert('RGBA').getpixel((5,5)),(255,0,0,255))
        with Image.open(convert(self.job('PNG',[p],width=80))[0]) as im:self.assertEqual(im.size,(80,40))
        self.assertEqual(len(PdfReader(convert(self.job('Image → PDF',[p]))[0]).pages),1)
    def test_svg_transparent_background_and_jpeg_white(self):
        p=self.svg('<rect width="10" height="20" fill="#00f"/>')
        with Image.open(convert(self.job('PNG',[p]))[0]) as im:self.assertEqual(im.convert('RGBA').getpixel((30,10))[3],0)
        with Image.open(convert(self.job('JPEG',[p]))[0]) as im:self.assertGreater(min(im.getpixel((30,10))),240)
    def test_svg_limits(self):
        with self.assertRaisesRegex(ConversionError,'40 megapixels'):convert(self.job('PNG',[self.svg(size='width="20000" height="20000"')]))
        p=self.svg();p.write_text(p.read_text()+'<!--'+'x'*(5*1024*1024)+'-->')
        with self.assertRaisesRegex(ConversionError,'5 MiB'):convert(self.job('PNG',[p]))
    def test_ocr_image_and_pdf(self):
        ocr=self.tool('fake-tesseract',"import sys\nassert sys.argv[3:7]==['-l','eng','--psm','3'] and '--dpi' in sys.argv,sys.argv\nopen(sys.argv[2]+'.txt','w').write('Hello OCR\\n')\n")
        out=Path(convert(self.job('OCR → Text',[self.src],tesseract=ocr))[0]);self.assertEqual(out.read_text(encoding='utf8'),'Hello OCR\n')
        out=Path(convert(self.job('OCR → Text',[self.pdf()],tesseract=ocr))[0]);self.assertEqual(out.read_text(encoding='utf8').count('Hello OCR'),2)
    def test_ocr_validation(self):
        with mock.patch('engine.find_tool',return_value=None),self.assertRaisesRegex(ConversionError,'Tesseract.*not found'):convert(self.job('OCR → Text'))
        ocr=self.tool('fake-tesseract','')
        with self.assertRaisesRegex(ConversionError,'language'):convert(self.job('OCR → Text',tesseract=ocr,ocr_lang='eng; calc'))
        with self.assertRaisesRegex(ConversionError,'could not read'):convert(self.job('OCR → Text',tesseract=ocr))
        with self.assertRaisesRegex(ConversionError,'50 pages'):convert(self.job('OCR → Text',[self.pdf(pages=51)],tesseract=ocr))
        self.assertFalse(list(self.root.glob('*converted*')))
    def test_ocr_finds_installed_tesseract_without_settings(self):
        ocr=self.tool('fake-tesseract',"import sys\nopen(sys.argv[2]+'.txt','w').write('found it\\n')\n")
        with mock.patch('engine.find_tool',return_value=Path(ocr)):
            self.assertEqual(Path(convert(self.job('OCR → Text'))[0]).read_text(encoding='utf8'),'found it\n')
    def test_ocr_retries_sparse_layouts_when_page_analysis_finds_nothing(self):
        ocr=self.tool('fake-tesseract',"import sys\nopen(sys.argv[2]+'.txt','w').write('word\\n' if sys.argv[6]=='11' else '')\n")
        self.assertEqual(Path(convert(self.job('OCR → Text',tesseract=ocr))[0]).read_text(encoding='utf8'),'word\n')
    def test_ocr_explains_missing_language_data(self):
        ocr=self.tool('fake-tesseract',"import sys\nprint('Failed loading language deu')\nsys.exit(1)\n")
        with self.assertRaisesRegex(ConversionError,'no data for language "deu"'):convert(self.job('OCR → Text',tesseract=ocr,ocr_lang='deu'))
    def test_ocr_searchable_pdf(self):
        body="import sys\nfrom pypdf import PdfWriter\nw=PdfWriter();w.add_blank_page(100,100)\nw.write(sys.argv[2]+'.pdf')\n"
        ocr=self.tool('fake-tesseract',body)
        out=Path(convert(self.job('OCR → Searchable PDF',[self.pdf(pages=2)],tesseract=ocr))[0])
        self.assertTrue(out.name.endswith('-searchable.pdf'));self.assertEqual(len(PdfReader(str(out)).pages),2)
    def test_tool_detection_ignores_relative_path_entries(self):
        import engine
        with mock.patch.dict(os.environ,{'PATH':'relative-dir'}),mock.patch('engine._tool_dirs',return_value=[]):self.assertIsNone(engine.find_tool('ffmpeg'))
    def test_ocr_no_text(self):
        ocr=self.tool('fake-tesseract',"import sys\nopen(sys.argv[2]+'.txt','w').write(' \\n')\n")
        with self.assertRaisesRegex(ConversionError,'No text'):convert(self.job('OCR → Text',tesseract=ocr))
    def test_office_to_pdf(self):
        body=("import sys\nfrom pathlib import Path\nfrom pypdf import PdfWriter\na=sys.argv\n"
              "assert '--headless' in a and any(x.startswith('-env:UserInstallation=file:///') for x in a),a\n"
              "out=Path(a[a.index('--outdir')+1]);src=Path(a[-1]);assert src.name=='input.docx'\n"
              "w=PdfWriter();w.add_blank_page(100,100);w.write(out/'input.pdf')\n")
        soffice=self.tool('fake-soffice',body);doc=self.root/'报告 final.docx';doc.write_bytes(b'PK-not-really');before=doc.read_bytes()
        out=Path(convert(self.job('Office → PDF',[doc],soffice=soffice))[0]);self.assertEqual(out.suffix,'.pdf');self.assertEqual(len(PdfReader(out).pages),1)
        self.assertEqual(doc.read_bytes(),before);self.assertFalse([p for p in self.root.glob('*.lock*')]);self.assertFalse([p for p in self.root.iterdir() if p.name.startswith('.opentangerine')])
    def test_office_validation(self):
        doc=self.root/'a.docx';doc.write_bytes(b'x')
        with self.assertRaisesRegex(ConversionError,'LibreOffice'):convert(self.job('Office → PDF',[doc]))
        failing=self.tool('fake-soffice','import sys\nsys.exit(3)\n')
        with self.assertRaisesRegex(ConversionError,'could not convert'):convert(self.job('Office → PDF',[doc],soffice=failing))
        with self.assertRaisesRegex(ConversionError,'Word, Excel'):convert(self.job('Office → PDF',[self.src],soffice=failing))
        junk=self.tool('fake-soffice-junk',"import sys\nfrom pathlib import Path\nPath(sys.argv[sys.argv.index('--outdir')+1],'input.pdf').write_bytes(b'not a pdf')\n")
        with self.assertRaises(Exception):convert(self.job('Office → PDF',[doc],soffice=junk))
        self.assertFalse(list(self.root.glob('*converted*')))
    def test_external_tool_deadline(self):
        from engine import run_external
        import time
        start=time.monotonic()
        with self.assertRaises(ConversionError):run_external([sys.executable,'-c','import time;time.sleep(30)'],time.monotonic()+.3)
        self.assertLess(time.monotonic()-start,10)
if __name__=='__main__':unittest.main()
