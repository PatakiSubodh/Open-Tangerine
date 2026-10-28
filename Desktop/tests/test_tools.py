import os, re, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import toolops
from engine import convert, ConversionError
from runner import run_job
from PIL import Image
from pypdf import PdfReader, PdfWriter

FFMPEG = os.environ.get('OT_FFMPEG') or shutil.which('ffmpeg')

def duration(path):
    text = subprocess.run([FFMPEG, '-hide_banner', '-i', str(path)], capture_output=True, text=True).stderr
    m = re.search(r'Duration: (\d+):(\d+):(\d+\.\d+)', text);return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])

def size_of(path):
    text = subprocess.run([FFMPEG, '-hide_banner', '-i', str(path)], capture_output=True, text=True).stderr
    m = re.search(r'Video:.*?[\s,](\d{2,5})x(\d{2,5})', text);return int(m[1]), int(m[2])

class ToolBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.root = Path(self.tmp.name).resolve()
        self.photo = self.root / 'photo.jpg';Image.new('RGB', (80, 60), (200, 100, 50)).save(self.photo, quality=95)
    def tearDown(self): self.tmp.cleanup()
    def run_tool(self, tool, paths=None, **params):
        return convert({'target': 'tool:' + tool, 'paths': [str(p) for p in (paths or [self.photo])], 'output': str(self.root), 'params': params, 'ffmpeg': FFMPEG or ''})
    def pdf(self, name='doc.pdf', pages=3):
        p = self.root / name;w = PdfWriter()
        for i in range(pages): w.add_blank_page(100 + i * 10, 100)
        with p.open('wb') as f: w.write(f)
        return p
    def png(self, name, size=(40, 30), colour='red'):
        p = self.root / name;Image.new('RGB', size, colour).save(p);return p

class ImageToolTests(ToolBase):
    def test_edit_brightness_and_name(self):
        out = Path(self.run_tool('edit_image', brightness=.8)[0]);self.assertTrue(out.name.endswith('-edited.jpg'))
        with Image.open(out) as im, Image.open(self.photo) as src: self.assertGreater(sum(im.getpixel((5, 5))), sum(src.getpixel((5, 5))))
    def test_edit_rejects_out_of_range(self):
        with self.assertRaises(ConversionError): self.run_tool('edit_image', brightness=5)
        with self.assertRaises(ConversionError): self.run_tool('edit_image', contrast='abc')
        with self.assertRaises(ConversionError): self.run_tool('edit_image', contrast=float('nan'))
    def test_frame_square_colour_and_blur(self):
        with Image.open(self.run_tool('frame_image', padding=10, aspect='1:1', color='#0000ff')[0]) as im:
            self.assertEqual(im.size[0], im.size[1]);self.assertGreater(im.size[0], 80);r, g, b = im.convert('RGB').getpixel((0, 0));self.assertGreater(b, 150);self.assertLess(r, 90)
        with Image.open(self.run_tool('frame_image', padding=20, aspect='16:9', blur=True)[0]) as im: self.assertAlmostEqual(im.size[0] / im.size[1], 16 / 9, delta=.05)
        with self.assertRaises(ConversionError): self.run_tool('frame_image', color='red')
    def test_crop(self):
        with Image.open(self.run_tool('crop_image', rect=[[.25, .5, .5, .5]])[0]) as im: self.assertEqual(im.size, (40, 30))
        for bad in ([[.8, .8, .5, .5]], [[0, 0, 0, 1]], [], 'x', [[-.1, 0, .5, .5]]):
            with self.assertRaises(ConversionError): self.run_tool('crop_image', rect=bad)
    def test_redact_styles(self):
        for style in ('black', 'blur', 'pixelate'):
            with self.subTest(style=style), Image.open(self.run_tool('redact_image', rects=[[0, 0, .5, .5]], style=style)[0]) as im:
                inside, outside = im.convert('RGB').getpixel((10, 10)), im.convert('RGB').getpixel((70, 50))
                if style == 'black': self.assertLess(sum(inside), 30)
                self.assertGreater(sum(outside), 200)
        with self.assertRaises(ConversionError): self.run_tool('redact_image', rects=[[0, 0, 2, 2]])
        with self.assertRaises(ConversionError): self.run_tool('redact_image', rects=[[0, 0, .1, .1]] * 51)
    def test_resize_modes_and_batch(self):
        for params, size in (({'mode': 'percent', 'percent': 50}, (40, 30)), ({'mode': 'width', 'width': 160}, (160, 120)), ({'mode': 'height', 'height': 30}, (40, 30)), ({'mode': 'fit', 'width': 40, 'height': 40}, (40, 30))):
            with self.subTest(params=params), Image.open(self.run_tool('resize_image', **params)[0]) as im: self.assertEqual(im.size, size)
        with self.assertRaises(ConversionError): self.run_tool('resize_image', mode='width', width=20001)
    def test_rotate_flip(self):
        marked = self.root / 'm.png';im = Image.new('RGB', (4, 2), 'white');im.putpixel((0, 0), (255, 0, 0));im.save(marked)
        with Image.open(self.run_tool('rotate_image', [marked], rotation=90)[0]) as out: self.assertEqual(out.size, (2, 4));self.assertEqual(out.convert('RGB').getpixel((1, 0)), (255, 0, 0))
        with Image.open(self.run_tool('rotate_image', [marked], flip_h=True)[0]) as out: self.assertEqual(out.convert('RGB').getpixel((3, 0)), (255, 0, 0))
        with self.assertRaises(ConversionError): self.run_tool('rotate_image', [marked], rotation=45)
    def test_create_pdf_from_many_images(self):
        a, b, c = self.png('a.png'), self.png('b.png', (30, 60)), self.png('c.png')
        pages = PdfReader(self.run_tool('create_pdf', [a, b, c])[0]).pages;self.assertEqual(len(pages), 3);self.assertAlmostEqual(float(pages[0].mediabox.width), 595.2, delta=1)       # default is A4
        fit = PdfReader(self.run_tool('create_pdf', [b], page='fit')[0]).pages;self.assertLess(float(fit[0].mediabox.width), 100)
        a4 = PdfReader(self.run_tool('create_pdf', [a, b], page='a4')[0]).pages;self.assertEqual(len(a4), 2);self.assertAlmostEqual(float(a4[0].mediabox.height) / float(a4[0].mediabox.width), 1.414, delta=.02)
    def test_collage(self):
        files = [self.png(f'{i}.png', colour=c) for i, c in enumerate(('red', 'green', 'blue', 'white'))]
        with Image.open(self.run_tool('collage', files, cell=100, spacing=10, columns=2, color='#000000')[0]) as im:
            self.assertEqual(im.size, (230, 230));self.assertEqual(im.getpixel((5, 5)), (0, 0, 0));self.assertEqual(im.getpixel((60, 60)), (255, 0, 0))
        with self.assertRaises(ConversionError): self.run_tool('collage', [files[0]])
    def test_compress_images(self):
        noisy = self.root / 'noisy.jpg';import random;random.seed(1);im = Image.new('RGB', (200, 200));im.putdata([(random.randrange(256),) * 3 for _ in range(40000)]);im.save(noisy, quality=98)
        out = Path(self.run_tool('compress', [noisy], level='strong')[0]);self.assertLess(out.stat().st_size, noisy.stat().st_size);self.assertTrue(out.name.endswith('-compressed.jpg'))
        small = self.root / 's.jpg';im.save(small, quality=15)  # re-encoding this at 88 can only make it bigger
        with self.assertRaisesRegex(ConversionError, 'already well compressed'): self.run_tool('compress', [small], level='light')
    def test_metadata_gps_and_all(self):
        from PIL import Image as I
        exif = I.Exif();exif[0x010F] = 'Camera Co';exif[0x8825] = {1: 'N'};src = self.root / 'gps.jpg';I.new('RGB', (16, 16)).save(src, exif=exif)
        with I.open(src) as im: self.assertIn(0x010F, im.getexif())
        with I.open(self.run_tool('metadata', [src], mode='all')[0]) as im: self.assertEqual(dict(im.getexif()), {})
        with I.open(self.run_tool('metadata', [src], mode='gps')[0]) as im: self.assertIn(0x010F, im.getexif());self.assertNotIn(0x8825, im.getexif())
    def test_originals_untouched_and_never_overwritten(self):
        before = self.photo.read_bytes();a = self.run_tool('rotate_image', rotation=90)[0];b = self.run_tool('rotate_image', rotation=90)[0]
        self.assertNotEqual(a, b);self.assertEqual(before, self.photo.read_bytes())

class PdfToolTests(ToolBase):
    def test_merge_order(self):
        a, b = self.pdf('a.pdf', 1), self.pdf('b.pdf', 2);out = PdfReader(self.run_tool('merge_pdf', [b, a])[0]);self.assertEqual(len(out.pages), 3);self.assertEqual(float(out.pages[0].mediabox.width), 100)
        with self.assertRaises(ConversionError): self.run_tool('merge_pdf', [a])
    def test_organize_reorder_delete_rotate(self):
        p = self.pdf(pages=3)
        out = PdfReader(self.run_tool('organize_pdf', [p], pages=[{'page': 2, 'rotate': 0}, {'page': 0, 'rotate': 90}])[0])
        self.assertEqual(len(out.pages), 2);self.assertEqual(float(out.pages[0].mediabox.width), 120);self.assertEqual(out.pages[1].get('/Rotate'), 90)
        for bad in ([], [{'page': 9}], [{'page': 0, 'rotate': 45}], 'x', [{'rotate': 90}]):
            with self.assertRaises(ConversionError): self.run_tool('organize_pdf', [p], pages=bad)
    def test_split_each_and_ranges(self):
        p = self.pdf(pages=5)
        self.assertEqual(len(self.run_tool('split_pdf', [p], mode='each')), 5)
        out = self.run_tool('split_pdf', [p], mode='ranges', ranges='1-2, 4, 5-');self.assertEqual([len(PdfReader(o).pages) for o in out], [2, 1, 1])
        for bad in ('0-2', '3-9', 'abc', '', '4-2'):
            with self.assertRaises(ConversionError): self.run_tool('split_pdf', [p], mode='ranges', ranges=bad)
    def test_pdf_compress_and_metadata(self):
        w = PdfWriter();w.add_blank_page(200, 200);p = self.root / 'meta.pdf'
        with p.open('wb') as f: w.write(f)
        out = PdfReader(self.run_tool('metadata', [p], title='Hello', author='Me')[0]);self.assertEqual(out.metadata.title, 'Hello');self.assertEqual(out.metadata.author, 'Me')
        bloated = self.root / 'big.pdf';w = PdfWriter()
        for _ in range(30):
            pg = w.add_blank_page(300, 300)
        with bloated.open('wb') as f: w.write(f)
        try: self.run_tool('compress', [bloated], level='strong')
        except ConversionError as e: self.assertIn('already well compressed', str(e))

class ApplicabilityTests(ToolBase):
    def names(self, files): return [t.id for t in toolops.tools_for([str(f) for f in files])]
    def test_single_image(self):
        n = self.names([self.photo]);self.assertIn('crop_image', n);self.assertIn('create_pdf', n);self.assertNotIn('collage', n);self.assertNotIn('trim', n);self.assertLessEqual(len(n), 12)
    def test_two_images(self):
        n = self.names([self.photo, self.png('b.png')]);self.assertIn('collage', n);self.assertNotIn('crop_image', n);self.assertIn('resize_image', n)
    def test_pdfs(self):
        self.assertEqual(self.names([self.pdf()]), ['compress', 'metadata', 'organize_pdf', 'split_pdf']);self.assertIn('merge_pdf', self.names([self.pdf('a.pdf'), self.pdf('b.pdf')]))
    def test_media_and_mixed(self):
        self.assertIn('trim', self.names(['a.mp4']));self.assertIn('join_videos', self.names(['a.mp4', 'b.mov']));self.assertIn('audio_channels', self.names(['a.wav']));self.assertNotIn('audio_channels', self.names(['a.mp4']))
        self.assertEqual(self.names([self.photo, self.pdf()]), []);self.assertEqual(self.names(['a.xyz']), []);self.assertEqual(self.names([]), [])
    def test_wheel_never_has_more_than_twelve_tools(self):
        for files in (['a.png'], ['a.mp4'], ['a.wav'], ['a.pdf'], ['a.png', 'b.png'], ['a.pdf', 'b.pdf'], ['a.mp4', 'b.mp4']): self.assertLessEqual(len(self.names(files)), 12, files)
    def test_every_tool_declares_labels(self):
        for t in toolops.TOOLS.values(): self.assertTrue(t.label and t.caption and t.title and t.progress, t.id)

class ToolSafetyTests(ToolBase):
    def test_unknown_or_misapplied_tool(self):
        with self.assertRaises(ConversionError): self.run_tool('nope')
        with self.assertRaises(ConversionError): self.run_tool('crop_image', [self.photo, self.png('x.png')], rect=[[0, 0, .5, .5]])
        with self.assertRaises(ConversionError): self.run_tool('trim', [self.photo])
    def test_worker_protocol(self):
        out = run_job({'target': 'tool:rotate_image', 'paths': [str(self.photo)], 'output': str(self.root), 'params': {'rotation': 180}})
        with Image.open(out[0]) as im: self.assertEqual(im.size, (80, 60))
    def test_missing_ffmpeg_message(self):
        clip = self.root / 'a.mp4';clip.write_bytes(b'x')
        with self.assertRaisesRegex(ConversionError, 'FFmpeg'): convert({'target': 'tool:trim', 'paths': [str(clip)], 'output': str(self.root), 'params': {}})
    def test_no_stray_work_folders_after_failure(self):
        with self.assertRaises(ConversionError): self.run_tool('crop_image', rect=[[2, 2, 1, 1]])
        self.assertEqual([p.name for p in self.root.iterdir() if p.name.startswith('.opentangerine')], [])

@unittest.skipUnless(FFMPEG, 'FFmpeg not installed (set OT_FFMPEG)')
class MediaToolTests(ToolBase):
    def setUp(self):
        super().setUp()
        def make(name, size, seconds, tone=440):
            p = self.root / name
            subprocess.run([FFMPEG, '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', f'color=c=orange:s={size}:r=15', '-f', 'lavfi', '-i', f'sine=frequency={tone}:sample_rate=24000', '-t', str(seconds), '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(p)], check=True);return p
        self.video = make('clip.mp4', '128x72', 4);self.video2 = make('other.mp4', '64x64', 2, 880)
        self.audio = self.root / 'tone.wav';subprocess.run([FFMPEG, '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=24000', '-t', '3', '-ac', '2', str(self.audio)], check=True)
    def test_trim_video_and_audio(self):
        out = self.run_tool('trim', [self.video], start=1, end=3)[0];self.assertAlmostEqual(duration(out), 2, delta=.4)
        out = self.run_tool('trim', [self.audio], start=1)[0];self.assertTrue(out.endswith('.wav'));self.assertAlmostEqual(duration(out), 2, delta=.2)
        for bad in ({'start': 9}, {'start': 2, 'end': 1}, {'start': -1}):
            with self.assertRaises(ConversionError): self.run_tool('trim', [self.video], **bad)
    def test_split_parts_and_times(self):
        parts = self.run_tool('split_media', [self.video], mode='parts', parts=2);self.assertEqual(len(parts), 2);self.assertAlmostEqual(sum(duration(p) for p in parts), 4, delta=.6)
        self.assertEqual(len(self.run_tool('split_media', [self.video], mode='at', times='1, 2.5')), 3)
        with self.assertRaises(ConversionError): self.run_tool('split_media', [self.video], mode='at', times='0, 99')
    def test_crop_video_square(self):
        w, h = size_of(self.run_tool('crop_video', [self.video], shape='1:1')[0]);self.assertEqual((w, h), (72, 72))
    def test_speed(self):
        self.assertAlmostEqual(duration(self.run_tool('speed_video', [self.video], factor=2)[0]), 2, delta=.5)
        self.assertAlmostEqual(duration(self.run_tool('speed_video', [self.video], factor=.5)[0]), 8, delta=.8)
        with self.assertRaises(ConversionError): self.run_tool('speed_video', [self.video], factor=10)
    def test_join_different_sizes(self):
        out = self.run_tool('join_videos', [self.video, self.video2])[0];self.assertAlmostEqual(duration(out), 6, delta=.7);self.assertEqual(size_of(out), (128, 72))
    def test_frames_into_new_folder(self):
        out = self.run_tool('video_frames', [self.video], mode='count', count=4, format='jpg');self.assertTrue(3 <= len(out) <= 5);self.assertTrue(all(Path(p).parent.name.endswith('-frames') for p in out))
        again = self.run_tool('video_frames', [self.video], mode='interval', seconds=1);self.assertNotEqual(Path(again[0]).parent, Path(out[0]).parent)
    def test_normalize_channels_visualizer(self):
        self.assertTrue(self.run_tool('normalize_audio', [self.audio], target=-20)[0].endswith('.wav'))
        mono = self.run_tool('audio_channels', [self.audio], mode='mono')[0];text = subprocess.run([FFMPEG, '-hide_banner', '-i', mono], capture_output=True, text=True).stderr;self.assertIn('mono', text)
        for mode in ('left', 'right', 'swap', 'stereo'): self.assertTrue(Path(self.run_tool('audio_channels', [self.audio], mode=mode)[0]).is_file())
        self.assertEqual(size_of(self.run_tool('audio_visualizer', [self.audio], color='#00ff00')[0]), (1280, 720))
        with self.assertRaises(ConversionError): self.run_tool('audio_visualizer', [self.audio], color='green')
    def test_compress_and_metadata_media(self):
        self.assertTrue(Path(self.run_tool('compress', [self.audio], level='strong')[0]).name.endswith('.mp3'))
        out = self.run_tool('metadata', [self.video], title='Secret')[0];self.assertTrue(Path(out).is_file())
        text = subprocess.run([FFMPEG, '-hide_banner', '-i', out], capture_output=True, text=True).stderr;self.assertIn('Secret', text)

if __name__ == '__main__': unittest.main()
