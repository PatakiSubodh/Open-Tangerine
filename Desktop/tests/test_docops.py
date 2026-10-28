import os, shutil, subprocess, sys, tempfile, unittest, xml.etree.ElementTree as ET, zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import convert, ConversionError, OPERATIONS
import docops
from PIL import Image
from pypdf import PdfReader, PdfWriter

def find_ffmpeg():
    p=os.environ.get('OT_FFMPEG') or os.environ.get('OT_TEST_FFMPEG') or shutil.which('ffmpeg')
    return p if p and Path(p).is_file() else None
FF=find_ffmpeg()

class Base(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
    def tearDown(self):self.tmp.cleanup()
    def job(self,target,path,**kw):return dict(paths=[str(path)],target=target,output=str(self.root),**kw)
    def png(self,name='in.png',size=(40,30)):
        p=self.root/name;Image.new('RGBA',size,(255,0,0,128)).save(p);return p
    def pdf(self,name='in.pdf',pages=2):
        p=self.root/name;w=PdfWriter()
        for _ in range(pages):w.add_blank_page(100,100)
        with p.open('wb') as f:w.write(f)
        return p
    def text(self,body,name='note.txt'):
        p=self.root/name;p.write_text(body,encoding='utf8');return p

class ImageTests(Base):
    def test_avif_round_trip(self):
        import pillow_heif;pillow_heif.register_heif_opener()
        out=convert(self.job('AVIF',self.png()))[0];self.assertTrue(out.endswith('.avif'))
        with Image.open(out) as im:self.assertEqual(im.size,(40,30))
    def test_image_to_docx(self):
        out=convert(self.job('Image → DOCX',self.png()))[0]
        with zipfile.ZipFile(out) as z:
            self.assertIsNone(z.testzip());self.assertIn('word/media/image1.png',z.namelist())
            for n in ('word/document.xml','[Content_Types].xml','word/_rels/document.xml.rels'):ET.fromstring(z.read(n))
            self.assertIn(b'w:w="11906" w:h="16838"',z.read('word/document.xml'))       # A4, not Letter
    def test_image_to_docx_rejects_non_image(self):
        with self.assertRaises(ConversionError):convert(self.job('Image → DOCX',self.text('x')))
    def test_second_run_does_not_overwrite(self):
        a=convert(self.job('AVIF',self.png()))[0];b=convert(self.job('AVIF',self.png()))[0];self.assertNotEqual(a,b);self.assertTrue(Path(a).exists())

class PdfTests(Base):
    def test_pdf_to_png_multi_and_single(self):
        outs=convert(self.job('PDF → PNG',self.pdf()));self.assertEqual([Path(o).name for o in outs],['in-page-1.png','in-page-2.png'])
        with Image.open(outs[0]) as im:self.assertEqual(im.size,(417,417))   # 100 pt at 300 dpi
        one=convert(self.job('PDF → JPEG',self.pdf('one.pdf',1)));self.assertEqual(Path(one[0]).name,'one-converted.jpg')
    def test_pdf_to_images_rejects_non_pdf(self):
        with self.assertRaises(ConversionError):convert(self.job('PDF → PNG',self.png()))
    def test_pdf_to_docx_text_and_scan(self):
        src=self.root/'t.pdf';docops.text_to_pdf('Hello Tangerine\nsecond line',src);docx=convert(self.job('PDF → DOCX',src))[0]
        with zipfile.ZipFile(docx) as z:self.assertIn('Hello Tangerine',z.read('word/document.xml').decode())
        with zipfile.ZipFile(convert(self.job('PDF → DOCX',self.pdf('blank.pdf',1)))[0]) as z:self.assertIn('word/media/image1.png',z.namelist())
    def test_corrupt_pdf(self):
        bad=self.root/'bad.pdf';bad.write_bytes(b'%PDF-1.4 nonsense')
        with self.assertRaises(Exception):convert(self.job('PDF → PNG',bad))
        self.assertEqual([p.name for p in self.root.iterdir() if p.name.startswith('bad-')],[])

class TextTests(Base):
    def test_text_to_pdf_vector_text(self):
        out=convert(self.job('Text → PDF',self.text('Hello (world) \\ back\nline two')))[0]
        r=PdfReader(out);self.assertEqual(len(r.pages),1);t=r.pages[0].extract_text();self.assertIn('Hello (world)',t);self.assertIn('line two',t)
    def test_text_to_pdf_is_a4(self):
        page=PdfReader(convert(self.job('Text → PDF',self.text('hi')))[0]).pages[0];self.assertEqual((round(float(page.mediabox.width)),round(float(page.mediabox.height))),(595,842))
    def test_text_to_pdf_paginates(self):
        out=convert(self.job('Text → PDF',self.text('\n'.join(f'line {i}' for i in range(120)))))[0];self.assertEqual(len(PdfReader(out).pages),3)
    def test_text_to_pdf_wraps_long_lines(self):
        pages=docops.layout('word '*400);self.assertGreater(sum(len(p) for p in pages),5)
    @unittest.skipUnless(docops.font_path(),'no system font')
    def test_text_to_pdf_non_latin_falls_back_to_image_pdf(self):
        out=convert(self.job('Text → PDF',self.text('Привет 你好')))[0];self.assertEqual(len(PdfReader(out).pages),1)
    def test_text_to_pdf_page_limit(self):
        with self.assertRaisesRegex(ConversionError,'200 pages'):convert(self.job('Text → PDF',self.text('x\n'*20000)))
    def test_text_to_images(self):
        png=convert(self.job('Text → PNG',self.text('hi\nthere')))[0]
        with Image.open(png) as im:self.assertEqual(im.size,(1240,1754))
        self.assertTrue(convert(self.job('Text → JPEG',self.text('hi','b.md')))[0].endswith('.jpg'))
    def test_text_too_long_for_one_image(self):
        with self.assertRaisesRegex(ConversionError,'too long'):convert(self.job('Text → PNG',self.text('x\n'*2000)))
    def test_text_rejects_big_and_wrong_type(self):
        big=self.root/'big.txt';big.write_bytes(b'a'*(5*1024*1024+1))
        with self.assertRaisesRegex(ConversionError,'5 MiB'):convert(self.job('Text → PDF',big))
        with self.assertRaises(ConversionError):convert(self.job('Text → PDF',self.png()))
    def test_text_to_srt_vtt_invents_timings(self):
        srt=Path(convert(self.job('Text → SRT',self.text('First cue\n\nSecond cue here')))[0]).read_text(encoding='utf8')
        self.assertTrue(srt.startswith('1\n00:00:00,000 --> 00:00:01,500\nFirst cue'));self.assertIn('2\n00:00:01,500 --> 00:00:03,000\nSecond cue here',srt)
        vtt=Path(convert(self.job('Text → VTT',self.text('Only one')))[0]).read_text(encoding='utf8');self.assertTrue(vtt.startswith('WEBVTT\n\n00:00:00.000 --> 00:00:01.500'))
    def test_subtitle_to_text(self):
        srt=self.root/'a.srt';srt.write_text('1\n00:00:01,000 --> 00:00:02,000\n<i>Hello</i>\n\n2\n00:00:03,000 --> 00:00:04,000\nWorld\n',encoding='utf8')
        self.assertEqual(Path(convert(self.job('Subtitle → Text',srt))[0]).read_text(encoding='utf8'),'Hello\n\nWorld\n')
        vtt=self.root/'a.vtt';vtt.write_text('WEBVTT\n\n00:01.000 --> 00:02.000 align:start\n{\\an8}Top\n',encoding='utf8')
        self.assertEqual(Path(convert(self.job('Subtitle → Text',vtt))[0]).read_text(encoding='utf8'),'Top\n')
    def test_subtitle_to_text_requires_timestamps(self):
        bad=self.root/'b.srt';bad.write_text('no times here',encoding='utf8')
        with self.assertRaisesRegex(ConversionError,'timestamps'):convert(self.job('Subtitle → Text',bad))
    def test_cp1252_and_utf16_text(self):
        p=self.root/'w.txt';p.write_bytes('café'.encode('cp1252'));self.assertEqual(docops.read_text(p),'café')
        p.write_bytes('héllo'.encode('utf-16'));self.assertEqual(docops.read_text(p),'héllo')

@unittest.skipUnless(FF,'FFmpeg not installed (set OT_TEST_FFMPEG to test media routes)')
class MediaRouteTests(Base):
    def make(self,args,name):
        out=self.root/name;subprocess.run([FF,'-hide_banner','-loglevel','error','-y',*args,str(out)],check=True);return out
    def clip(self):return self.make(['-f','lavfi','-i','testsrc=size=160x120:rate=10:duration=1','-f','lavfi','-i','sine=frequency=440:duration=1','-pix_fmt','yuv420p','-shortest'],'clip.mp4')
    def tone(self):return self.make(['-f','lavfi','-i','sine=frequency=440:duration=1'],'tone.wav')
    def run_to(self,target,src):return Path(convert(self.job(target,src,ffmpeg=FF))[0])
    def test_video_targets(self):
        c=self.clip()
        self.assertEqual(self.run_to('GIF',c).read_bytes()[:6],b'GIF89a')
        self.assertEqual(self.run_to('AVI',c).read_bytes()[:4],b'RIFF')
        self.assertEqual(self.run_to('WMV',c).read_bytes()[:4],bytes.fromhex('3026b275'))
        self.assertEqual(self.run_to('MOV',c).read_bytes()[4:8],b'ftyp');self.assertEqual(self.run_to('MKV',c).read_bytes()[:4],bytes.fromhex('1a45dfa3'))
    def test_audio_targets(self):
        t=self.tone()
        self.assertEqual(self.run_to('OPUS',t).read_bytes()[:4],b'OggS');self.assertEqual(self.run_to('AIFF',t).read_bytes()[:4],b'FORM')
        self.assertEqual(self.run_to('WMA',t).read_bytes()[:4],bytes.fromhex('3026b275'));self.assertEqual(self.run_to('M4A',t).read_bytes()[4:8],b'ftyp')
    def test_new_audio_inputs_round_trip(self):
        t=self.tone();opus=self.run_to('OPUS',t);self.assertEqual(self.run_to('WAV',opus).read_bytes()[:4],b'RIFF')
        self.assertEqual(self.run_to('FLAC',self.run_to('AIFF',t)).read_bytes()[:4],b'fLaC')
    def test_gif_to_video_even_dimensions(self):
        g=self.run_to('GIF',self.clip());out=self.run_to('MP4',g);self.assertEqual(out.read_bytes()[4:8],b'ftyp')
        odd=self.make(['-f','lavfi','-i','testsrc=size=101x75:rate=5:duration=1'],'odd.gif');self.assertEqual(self.run_to('MP4',odd).read_bytes()[4:8],b'ftyp')
    def test_gif_is_capped(self):
        big=self.make(['-f','lavfi','-i','testsrc=size=1280x720:rate=10:duration=1','-pix_fmt','yuv420p'],'big.mp4')
        with Image.open(self.run_to('GIF',big)) as im:self.assertEqual(im.size,(480,270))

class OperationTests(unittest.TestCase):
    def test_all_new_operations_listed(self):
        for x in ('AVIF','GIF','AVI','WMV','M4A','OPUS','AIFF','WMA','PDF → PNG','PDF → JPEG','PDF → DOCX','Image → DOCX','Text → PDF','Text → SRT','Subtitle → Text','MOV','MKV'):self.assertIn(x,OPERATIONS)

if __name__=='__main__':unittest.main()
