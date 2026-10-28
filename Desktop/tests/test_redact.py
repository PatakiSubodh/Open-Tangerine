"""Redact video and Bleep audio. These need an FFmpeg build (set OT_FFMPEG or put ffmpeg on PATH)."""
import array, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import convert, ConversionError
import toolops

FF = os.environ.get('OT_FFMPEG') or os.environ.get('OT_TEST_FFMPEG') or shutil.which('ffmpeg')
FF = FF if FF and Path(FF).is_file() else None

class Applicability(unittest.TestCase):
    def test_wheel_offers_them(self):
        ids = lambda paths: [t.id for t in toolops.tools_for(paths)]
        self.assertIn('redact_video', ids(['a.mp4']));self.assertNotIn('redact_video', ids(['a.mp3']));self.assertNotIn('redact_video', ids(['a.mp4', 'b.mp4']))
        self.assertIn('bleep_audio', ids(['a.wav']));self.assertNotIn('bleep_audio', ids(['a.mp4']))
    def test_parameter_validation(self):
        P = toolops.P
        self.assertEqual(P({'r': [[0, 1.5], [3, 0]]}).time_ranges('r', open_end=True), [(0.0, 1.5), (3.0, None)])
        for bad in ([], [[2, 1]], [[1, 1]], [[-1, 2]], [['a', 2]], [[0, 1, 2]], [[0, 90000]], 'x'):
            with self.assertRaises(ConversionError, msg=str(bad)): P({'r': bad}).time_ranges('r')
        self.assertEqual(P({'b': [[.1, .2, .3, .4, 1, 0]]}).timed_boxes('b'), [((.1, .2, .3, .4), (1.0, None))])
        for bad in ([[0, 0, 2, 2, 0, 0]], [[0, 0, .5, .5, 0]], [[0, 0, .5, .5, 3, 2]], []):
            with self.assertRaises(ConversionError, msg=str(bad)): P({'b': bad}).timed_boxes('b')
    def test_pixel_boxes_cover_the_selection_and_stay_inside(self):
        for rect in ((0, 0, 1, 1), (.1, .1, .33, .27), (.9, .9, .1, .1), (0, 0, .001, .001)):
            x, y, w, h = toolops.px_box(rect, 321, 241)
            self.assertTrue(x % 2 == 0 and y % 2 == 0 and w >= 2 and h >= 2 and x + w <= 321 and y + h <= 241, (rect, x, y, w, h))
            self.assertLessEqual(x, int(rect[0] * 321));self.assertGreaterEqual(x + w, min(321, int((rect[0] + rect[2]) * 321)))

@unittest.skipUnless(FF, 'FFmpeg not installed (set OT_FFMPEG)')
class Base(unittest.TestCase):
    def setUp(self): self.tmp = tempfile.TemporaryDirectory();self.root = Path(self.tmp.name).resolve()
    def tearDown(self): self.tmp.cleanup()
    def ff(self, *args): subprocess.run([FF, '-nostdin', '-hide_banner', '-loglevel', 'error', '-y', *map(str, args)], check=True)
    def run_tool(self, tool, path, **params):
        return convert({'target': 'tool:' + tool, 'paths': [str(path)], 'output': str(self.root), 'params': params, 'ffmpeg': FF})
    def info(self, path): return subprocess.run([FF, '-hide_banner', '-i', str(path)], capture_output=True, text=True).stderr

class RedactVideoTests(Base):
    W, H = 320, 240
    def clip(self, name='clip.mp4', source='color=c=red:s=320x240:r=15', audio=True, seconds=2):
        out = self.root / name;a = ['-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=24000'] if audio else []
        self.ff('-f', 'lavfi', '-i', source, *a, '-t', seconds, '-pix_fmt', 'yuv420p', *(['-c:a', 'aac'] if audio else []), out);return out
    def pixel(self, path, t, x, y):
        raw = subprocess.run([FF, '-nostdin', '-v', 'error', '-ss', str(t), '-i', str(path), '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True).stdout
        w = int(self.W);return tuple(raw[(y * w + x) * 3:(y * w + x) * 3 + 3])
    def region_diff(self, a, b, t, box):
        def grab(p): return subprocess.run([FF, '-nostdin', '-v', 'error', '-ss', str(t), '-i', str(p), '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'gray', '-'], capture_output=True).stdout
        ra, rb = grab(a), grab(b);x0, y0, x1, y1 = box;total = n = 0
        for y in range(y0, y1):
            for x in range(x0, x1): total += abs(ra[y * self.W + x] - rb[y * self.W + x]);n += 1
        return total / n
    def test_black_box_only_inside_its_time_window_and_area(self):
        out = self.run_tool('redact_video', self.clip(), style='black', boxes=[[0, 0, .5, .5, 1, 0]])[0]
        self.assertTrue(out.endswith('-redacted.mp4'))
        before = self.pixel(out, .4, 10, 10);inside = self.pixel(out, 1.5, 10, 10);elsewhere = self.pixel(out, 1.5, 300, 220)
        self.assertGreater(before[0], 180);self.assertLess(before[1], 90)             # still the red source
        self.assertLess(max(inside), 40)                                              # black
        self.assertGreater(elsewhere[0], 180)                                         # outside the box
        self.assertIn('Audio:', self.info(out))                                       # sound is kept
    def test_end_time_closes_the_window(self):
        out = self.run_tool('redact_video', self.clip(seconds=3), style='black', boxes=[[0, 0, 1, 1, .5, 1.2]])[0]
        self.assertLess(max(self.pixel(out, .9, 50, 50)), 40);self.assertGreater(self.pixel(out, 2.2, 50, 50)[0], 180)
    def test_blur_and_pixelate_change_only_the_box(self):
        src = self.clip('pattern.mp4', "color=c=gray:s=320x240:r=15,geq=lum='random(1)*255':cb=128:cr=128", audio=False, seconds=2);box = [[.25, .25, .5, .5, 0, 0]]
        for style in ('blur', 'pixelate'):
            out = self.run_tool('redact_video', src, style=style, boxes=box)[0]
            inside = self.region_diff(src, out, 1, (90, 70, 230, 170));corner = self.region_diff(src, out, 1, (0, 0, 70, 50))
            self.assertGreater(inside, 25, style);self.assertLess(corner, inside / 3, style)       # picture inside is gone; the rest is only re-encode noise
    def test_several_boxes_and_odd_sizes(self):
        src = self.clip('odd.mp4', 'color=c=red:s=322x242:r=15', audio=False);self.W = 322
        out = self.run_tool('redact_video', src, style='black', boxes=[[0, 0, .21, .17, 0, 0], [.7, .6, .3, .4, 0, 0]])[0]
        self.assertLess(max(self.pixel(out, .5, 5, 5)), 40);self.assertLess(max(self.pixel(out, .5, 316, 236)), 40);self.assertGreater(self.pixel(out, .5, 160, 120)[0], 180)
    def test_works_without_an_audio_track(self):
        out = self.run_tool('redact_video', self.clip(audio=False), boxes=[[0, 0, .5, .5, 0, 0]])[0];self.assertNotIn('Audio:', self.info(out))
    def test_rotated_phone_video_boxes_follow_the_upright_picture(self):
        flat = self.clip('flat.mp4', 'color=c=red:s=320x240:r=15', audio=False);turned = self.root / 'turned.mp4'
        self.ff('-display_rotation', '90', '-i', flat, '-c', 'copy', turned)
        if 'rotation of' not in self.info(turned): self.skipTest('this FFmpeg cannot write display rotation')
        self.assertEqual(toolops.probe_file(FF, turned, 1e9 + __import__('time').monotonic())['size'], (240, 320))
        out = self.run_tool('redact_video', turned, boxes=[[0, 0, .5, .25, 0, 0]])[0];self.assertIn('240x320', self.info(out))
    def test_errors_leave_no_output(self):
        clip = self.clip()
        for params, msg in (({'boxes': []}, 'Select at least one'), ({'boxes': [[0, 0, 2, 2, 0, 0]]}, 'outside'), ({'boxes': [[0, 0, .5, .5, 5, 0]]}, 'after the end'),
                            ({'boxes': [[0, 0, .5, .5, 2, 1]]}, 'end after'), ({'style': 'glitter', 'boxes': [[0, 0, .5, .5, 0, 0]]}, 'Invalid choice')):
            with self.assertRaisesRegex(ConversionError, msg): self.run_tool('redact_video', clip, **params)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ['clip.mp4'])
    def test_rejects_images_and_audio(self):
        wav = self.root / 'a.wav';self.ff('-f', 'lavfi', '-i', 'sine=frequency=440:duration=1', wav)
        with self.assertRaisesRegex(ConversionError, 'does not apply'): self.run_tool('redact_video', wav, boxes=[[0, 0, .5, .5, 0, 0]])

class BleepAudioTests(Base):
    RATE = 24000
    def tone(self, seconds=4, channels=2, name='tone.wav'):
        out = self.root / name;self.ff('-f', 'lavfi', '-i', f'sine=frequency=440:sample_rate={self.RATE}', '-t', seconds, '-ac', channels, out);return out
    def samples(self, path, start, length):
        raw = subprocess.run([FF, '-nostdin', '-v', 'error', '-ss', str(start), '-t', str(length), '-i', str(path), '-ac', '1', '-ar', str(self.RATE), '-f', 's16le', '-'], capture_output=True).stdout
        a = array.array('h');a.frombytes(raw[:len(raw) // 2 * 2]);return a
    def hz(self, a): return sum(1 for i in range(1, len(a)) if (a[i - 1] < 0) != (a[i] < 0)) / 2 / (len(a) / self.RATE)
    def peak(self, a): return max(abs(x) for x in a) / 32768
    def test_bleep_replaces_only_the_range_with_a_1000_hz_tone(self):
        out = self.run_tool('bleep_audio', self.tone(), mode='bleep', frequency=1000, ranges=[[1, 2]])[0]
        self.assertTrue(out.endswith('-bleeped.wav'));self.assertIn('stereo', self.info(out))
        before, inside, after = self.samples(out, .2, .6), self.samples(out, 1.2, .6), self.samples(out, 2.5, .6)
        self.assertAlmostEqual(self.hz(before), 440, delta=25);self.assertAlmostEqual(self.hz(inside), 1000, delta=40);self.assertAlmostEqual(self.hz(after), 440, delta=25)
        self.assertGreater(self.peak(inside), .2)                                    # audible bleep
    def test_silence_mode_and_several_ranges(self):
        out = self.run_tool('bleep_audio', self.tone(), mode='silence', ranges=[[.5, 1], [2.5, 3]])[0]
        for start in (.6, 2.6): self.assertLess(self.peak(self.samples(out, start, .3)), .01)
        for start in (0, 1.5, 3.2): self.assertGreater(self.peak(self.samples(out, start + .05, .3)), .05)
    def test_overlapping_ranges_do_not_double_the_tone(self):
        out = self.run_tool('bleep_audio', self.tone(), ranges=[[1, 2], [1.5, 2.5]])[0];self.assertLess(self.peak(self.samples(out, 1.6, .3)), .5)
    def test_range_past_the_end_is_tolerated_but_all_past_the_end_is_not(self):
        t = self.tone(2);self.run_tool('bleep_audio', t, ranges=[[1.5, 50]])
        with self.assertRaisesRegex(ConversionError, 'after the end'): self.run_tool('bleep_audio', t, ranges=[[10, 11]])
    def test_other_audio_formats_keep_their_format(self):
        for ext, magic in (('.mp3', None), ('.flac', b'fLaC'), ('.ogg', b'OggS')):
            src = self.root / f'a{ext}';self.ff('-i', self.tone(1, name='src.wav'), src);out = Path(self.run_tool('bleep_audio', src, ranges=[[.2, .5]])[0])
            self.assertEqual(out.suffix, ext)
            if magic: self.assertEqual(out.read_bytes()[:4], magic)
    def test_errors_leave_no_output(self):
        t = self.tone()
        for params, msg in (({'ranges': []}, 'at least one'), ({'ranges': [[2, 1]]}, 'end after'), ({'ranges': [[-1, 1]]}, 'between 0'), ({'mode': 'x', 'ranges': [[0, 1]]}, 'Invalid choice'), ({'frequency': 10, 'ranges': [[0, 1]]}, 'frequency')):
            with self.assertRaisesRegex(ConversionError, msg): self.run_tool('bleep_audio', t, **params)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ['tone.wav'])
    def test_rejects_video_and_silent_input(self):
        mp4 = self.root / 'v.mp4';self.ff('-f', 'lavfi', '-i', 'color=c=red:s=64x64:r=10', '-t', 1, '-pix_fmt', 'yuv420p', mp4)
        with self.assertRaisesRegex(ConversionError, 'does not apply'): self.run_tool('bleep_audio', mp4, ranges=[[0, 1]])

if __name__ == '__main__': unittest.main()
