import concurrent.futures, hashlib, json, os, shutil, subprocess, sys, tempfile, threading, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import convert, source_file, publish, ConversionError, MAX_BYTES
from runner import run_job, Cancelled
from PIL import Image
from pypdf import PdfReader, PdfWriter

class ConversionTests(unittest.TestCase):
    def setUp(self):
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
        p=Path(convert(self.job('SHA-256'))[0]);self.assertTrue(p.read_text().startswith(hashlib.sha256(self.src.read_bytes()).hexdigest()))
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
if __name__=='__main__':unittest.main()
