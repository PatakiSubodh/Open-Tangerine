"""Edit photo: the 17 adjustments (photoadjust.py), their validation and the tool window."""
import os, statistics, subprocess, sys, tempfile, unittest
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageChops, ImageEnhance
import photoadjust as pa, toolops
from engine import convert, ConversionError

def flat(colour, size=(64, 64)): return Image.new('RGB', size, colour)
def mean(im, band=None): return statistics.fmean((im.getchannel(band) if band is not None else im.convert('L')).getdata())
def spread(im): return statistics.pstdev(im.convert('L').getdata())

def noisy(size=(96, 96)):
    import random
    rng = random.Random(7);im = Image.new('RGB', size)
    im.putdata([tuple(min(255, max(0, 128 + int(rng.gauss(0, 30)))) for _ in range(3)) for _ in range(size[0] * size[1])]);return im

def scene(size=(120, 80)):
    im = Image.new('RGB', size, (90, 130, 200))
    for x in range(size[0]):
        for y in range(size[1] // 2, size[1]): im.putpixel((x, y), (50 + x, 100, 60))
    return im

class Neutral(unittest.TestCase):
    def test_nothing_changes_at_defaults(self):
        im = scene();self.assertIsNone(ImageChops.difference(pa.adjust(im, {}), im).getbbox());self.assertTrue(pa.is_neutral({}))
        self.assertIsNone(ImageChops.difference(pa.adjust(im, {k: v[2] for k, v in pa.LIMITS.items()}), im).getbbox())
    def test_the_original_four_controls_are_unchanged(self):
        im = scene();out = toolops.apply_edit(im.convert('RGBA'), {'brightness': .3, 'contrast': -.2, 'saturation': .5, 'sharpness': .4}).convert('RGB')
        old = ImageEnhance.Brightness(im).enhance(1.3);old = ImageEnhance.Contrast(old).enhance(.8);old = ImageEnhance.Color(old).enhance(1.5);old = ImageEnhance.Sharpness(old).enhance(1.8)
        self.assertIsNone(ImageChops.difference(out, old).getbbox())
    def test_form_and_validator_share_one_table(self):
        fields = {f.key: f for f in toolops.TOOLS['edit_image'].fields}
        for key, (lo, hi, default) in pa.LIMITS.items():
            f = fields[key];self.assertEqual((f.lo, f.hi, f.default), (lo, hi, default), key);self.assertTrue(f.group, key)
        self.assertEqual(set(fields) - set(pa.LIMITS), {'monochrome'});self.assertEqual(fields['monochrome'].kind, 'bool')
        self.assertEqual([f.group for f in fields.values()][0], 'Light');self.assertEqual(len({f.group for f in fields.values()}), 4)

class Direction(unittest.TestCase):
    def test_exposure_brightens_and_darkens_in_stops(self):
        g = flat((100, 100, 100));self.assertGreater(mean(pa.adjust(g, {'exposure': 1})), 130);self.assertLess(mean(pa.adjust(g, {'exposure': -1})), 80)
        self.assertEqual(pa.adjust(flat((255, 255, 255)), {'exposure': 2}).getpixel((0, 0)), (255, 255, 255))
    def test_highlights_and_shadows_move_only_their_own_tones(self):
        dark, bright = flat((30, 30, 30)), flat((235, 235, 235));mid = flat((128, 128, 128))
        self.assertLess(mean(pa.adjust(bright, {'highlights': -1})), 215);self.assertAlmostEqual(mean(pa.adjust(dark, {'highlights': -1})), 30, delta=1);self.assertAlmostEqual(mean(pa.adjust(mid, {'highlights': -1})), 128, delta=8)
        self.assertGreater(mean(pa.adjust(dark, {'shadows': 1})), 50);self.assertAlmostEqual(mean(pa.adjust(bright, {'shadows': 1})), 235, delta=1)
        self.assertLess(mean(pa.adjust(dark, {'shadows': -1})), 28);self.assertGreater(mean(pa.adjust(bright, {'highlights': 1})), 235)
    def test_highlight_recovery_keeps_the_hue_of_a_bright_colour(self):
        r, g, b = pa.adjust(flat((255, 240, 180)), {'highlights': -1}).getpixel((0, 0));self.assertTrue(r >= g >= b and r - b > 30, (r, g, b))
    def test_vibrance_spares_vivid_colours(self):
        muted, vivid = flat((140, 120, 110)), flat((255, 0, 0))
        def sat(im): return im.convert('HSV').getchannel('S').getpixel((0, 0))
        gain_muted = sat(pa.adjust(muted, {'vibrance': 1})) - sat(muted);gain_vivid = sat(pa.adjust(vivid, {'vibrance': 1})) - sat(vivid)
        self.assertGreater(gain_muted, 20);self.assertGreater(gain_muted, gain_vivid)
        self.assertLess(sat(pa.adjust(vivid, {'vibrance': -1})), sat(vivid));self.assertGreater(sat(pa.adjust(vivid, {'vibrance': -1})), 0)
    def test_temperature_and_tint(self):
        g = flat((120, 120, 120));warm = pa.adjust(g, {'temperature': 1}).getpixel((0, 0));cool = pa.adjust(g, {'temperature': -1}).getpixel((0, 0))
        self.assertTrue(warm[0] > 120 > warm[2] and cool[2] > 120 > cool[0]);magenta = pa.adjust(g, {'tint': 1}).getpixel((0, 0));green = pa.adjust(g, {'tint': -1}).getpixel((0, 0))
        self.assertTrue(magenta[1] < 120 < green[1])
    def test_sepia_and_monochrome(self):
        c = flat((60, 160, 220));r, g, b = pa.adjust(c, {'sepia': 1}).getpixel((0, 0));self.assertTrue(r > g > b, (r, g, b));self.assertEqual(len(set(pa.adjust(c, {'monochrome': True}).getpixel((0, 0)))), 1)
        half = pa.adjust(c, {'sepia': .5}).getpixel((0, 0));self.assertTrue(half != pa.adjust(c, {'sepia': 1}).getpixel((0, 0)) and half != c)
    def test_noise_reduction_and_grain(self):
        n = noisy();self.assertLess(spread(pa.adjust(n, {'noise': 1})), spread(n) * .8);self.assertLess(spread(pa.adjust(n, {'noise': .3})), spread(n));self.assertGreater(spread(pa.adjust(n, {'noise': .3})), spread(pa.adjust(n, {'noise': 1})))
        g = flat((128, 128, 128), (96, 96));self.assertEqual(spread(g), 0);grainy = pa.adjust(g, {'grain': 1});self.assertGreater(spread(grainy), 3);self.assertAlmostEqual(mean(grainy), 128, delta=6)
        self.assertGreater(spread(pa.adjust(g, {'grain': 1})), spread(pa.adjust(g, {'grain': .2})))
    def test_vignette_darkens_corners_not_the_centre(self):
        g = flat((200, 200, 200), (100, 80));v = pa.adjust(g, {'vignette': 1});self.assertEqual(v.getpixel((50, 40)), (200, 200, 200));self.assertLess(v.getpixel((1, 1))[0], 120)
        self.assertGreater(v.getpixel((1, 1))[0], 5);self.assertLess(pa.adjust(g, {'vignette': .3}).getpixel((1, 1))[0], 200)
    def test_clarity_and_dehaze_add_local_contrast(self):
        im = scene((200, 120));self.assertGreater(spread(pa.adjust(im, {'clarity': 1})), spread(im));self.assertGreater(spread(pa.adjust(im, {'dehaze': 1})), spread(im))
    def test_clarity_radius_follows_the_picture_size(self):
        """A downscaled preview must look like the full-size render: compare a big image's result, shrunk, to the shrunk image's result."""
        big = scene((400, 240));small = big.resize((100, 60), Image.Resampling.LANCZOS)
        a = pa.adjust(big, {'clarity': 1, 'vignette': .8}).resize((100, 60), Image.Resampling.LANCZOS);b = pa.adjust(small, {'clarity': 1, 'vignette': .8})
        diff = ImageChops.difference(a, b);self.assertLess(statistics.fmean(diff.convert('L').getdata()), 6)
    def test_every_control_changes_the_picture_and_keeps_its_size(self):
        im = scene()
        for key, (lo, hi, default) in pa.LIMITS.items():
            for value in (lo, hi):
                if value == default: continue
                out = pa.adjust(im, {key: value});self.assertEqual(out.size, im.size, key);self.assertEqual(out.mode, 'RGB', key);self.assertIsNotNone(ImageChops.difference(out, im).getbbox(), (key, value))
        self.assertIsNotNone(ImageChops.difference(pa.adjust(im, {'monochrome': True}), im).getbbox())
    def test_everything_at_once_stays_valid(self):
        v = {k: hi for k, (lo, hi, d) in pa.LIMITS.items()};v['monochrome'] = True;self.assertEqual(pa.adjust(scene(), v).size, (120, 80));v = {k: lo for k, (lo, hi, d) in pa.LIMITS.items()};self.assertEqual(pa.adjust(scene(), v).size, (120, 80))

class ThroughTheTool(unittest.TestCase):
    def setUp(self): self.tmp = tempfile.TemporaryDirectory();self.root = Path(self.tmp.name).resolve()
    def tearDown(self): self.tmp.cleanup()
    def run_edit(self, src, **params): return convert({'target': 'tool:edit_image', 'paths': [str(src)], 'output': str(self.root), 'params': params})
    def test_keeps_alpha_and_format(self):
        p = self.root / 'a.png';im = Image.new('RGBA', (40, 30), (200, 100, 50, 120));im.save(p)
        out = self.run_edit(p, exposure=.5, vignette=.5, grain=.4, monochrome=True)[0]
        with Image.open(out) as r: self.assertEqual(r.mode, 'RGBA');self.assertEqual(r.getpixel((20, 15))[3], 120)
        j = self.root / 'a.jpg';scene().save(j);self.assertTrue(self.run_edit(j, clarity=.5)[0].endswith('-edited.jpg'))
    def test_opaque_photos_stay_rgb_and_translucent_ones_keep_alpha(self):
        self.assertEqual(toolops.apply_edit(scene(), {'exposure': .5}).mode, 'RGB');self.assertEqual(toolops.apply_edit(scene().convert('L'), {'exposure': .5}).mode, 'RGB');self.assertEqual(toolops.apply_edit(scene().convert('RGBA'), {'exposure': .5}).mode, 'RGBA')
    def test_validation(self):
        p = self.root / 'a.png';scene().save(p)
        for params in ({'exposure': 3}, {'highlights': -2}, {'sepia': -.1}, {'grain': 'lots'}, {'vignette': float('nan')}, {'temperature': float('inf')}):
            with self.assertRaises(ConversionError, msg=str(params)): self.run_edit(p, **params)
        self.assertEqual([x.name for x in self.root.iterdir()], ['a.png'])
    def test_heic_and_tiff_inputs_still_work(self):
        t = self.root / 'a.tif';scene().save(t);self.assertTrue(self.run_edit(t, shadows=.5)[0].endswith('.tiff'))

class Window(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
    def setUp(self):
        from PySide6.QtCore import QSettings
        self.tmp = tempfile.TemporaryDirectory();self.root = Path(self.tmp.name).resolve();self.photo = self.root / 'p.png';scene((300, 200)).save(self.photo)
        self.settings = QSettings(str(self.root / 's.ini'), QSettings.IniFormat)
    def tearDown(self): self.tmp.cleanup()
    def test_form_groups_scroll_and_reset(self):
        import toolwin
        from PySide6.QtWidgets import QScrollArea, QCheckBox
        w = toolwin.ToolWindow(toolops.TOOLS['edit_image'], [str(self.photo)], self.settings);w.show();self.app.processEvents()
        try:
            self.assertEqual(len(w.findChildren(QScrollArea)) >= 1, True)
            for key in ('exposure', 'highlights', 'clarity', 'vignette', 'sepia', 'grain'): self.assertIsInstance(w.form.rows[key][1], toolwin.SliderField, key)
            self.assertIsInstance(w.form.rows['monochrome'][1], QCheckBox)
            w.form.rows['exposure'][1].slider.setValue(150);w.form.rows['clarity'][1].slider.setValue(100);w.form.rows['monochrome'][1].setChecked(True)
            v = w.form.values();self.assertAlmostEqual(v['exposure'], 1.0, places=1);self.assertAlmostEqual(v['clarity'], .5, places=2);self.assertTrue(v['monochrome'])
            self.assertTrue(toolops.edit_values(v)['monochrome'])
            w.form.reset();v = w.form.values()
            for key, (lo, hi, default) in pa.LIMITS.items(): self.assertAlmostEqual(float(v[key]), default, places=2, msg=key)
            self.assertFalse(v['monochrome'])
        finally: w.close()
    def test_preview_follows_the_sliders_on_a_downscaled_copy(self):
        import toolwin, time
        w = toolwin.ToolWindow(toolops.TOOLS['edit_image'], [str(self.photo)], self.settings);w.show();self.app.processEvents()
        try:
            before = w.preview_label.pixmap().toImage();w.form.rows['vignette'][1].slider.setValue(200)
            end = time.monotonic() + 1.5
            while time.monotonic() < end: self.app.processEvents();time.sleep(.01)
            after = w.preview_label.pixmap().toImage();self.assertNotEqual(before.pixel(2, 2), after.pixel(2, 2))
        finally: w.close()

PEAK = r'''
import sys, ctypes, ctypes.wintypes as wt
sys.path.insert(0, sys.argv[1])
from PIL import Image
import toolops
im = Image.effect_noise((7000, 5700), 40).convert('RGB');assert im.width * im.height <= 40_000_000
out = toolops.apply_edit(im, {k: (hi if hi > 0 else lo) * .8 for k, (lo, hi, d) in __import__('photoadjust').LIMITS.items()} | {'monochrome': True})
class C(ctypes.Structure): _fields_ = [('cb', wt.DWORD), ('PageFaultCount', wt.DWORD), ('PeakWorkingSetSize', ctypes.c_size_t), ('WorkingSetSize', ctypes.c_size_t), ('a', ctypes.c_size_t), ('b', ctypes.c_size_t), ('c', ctypes.c_size_t), ('d', ctypes.c_size_t), ('PagefileUsage', ctypes.c_size_t), ('PeakPagefileUsage', ctypes.c_size_t)]
k = ctypes.windll.kernel32;k.GetCurrentProcess.restype = wt.HANDLE;k.K32GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(C), wt.DWORD];c = C();c.cb = ctypes.sizeof(c);assert k.K32GetProcessMemoryInfo(k.GetCurrentProcess(), ctypes.byref(c), c.cb)
print(c.PeakPagefileUsage // 2**20, out.size)
'''

@unittest.skipUnless(os.name == 'nt' and os.environ.get('OT_SLOW'), 'slow: set OT_SLOW=1 on Windows to measure peak memory on a 40-megapixel photo')
class Memory(unittest.TestCase):
    def test_all_adjustments_on_40_megapixels_stay_under_1_2_gb(self):
        out = subprocess.run([sys.executable, '-c', PEAK, str(Path(__file__).resolve().parents[1])], capture_output=True, text=True, timeout=900)
        self.assertEqual(out.returncode, 0, out.stderr[-500:]);peak = int(out.stdout.split()[0]);print('peak MiB', peak);self.assertLess(peak, 1200)

if __name__ == '__main__': unittest.main()
