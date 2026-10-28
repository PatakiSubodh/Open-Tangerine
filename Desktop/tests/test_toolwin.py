import os, sys, tempfile, time, unittest
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import QApplication
from PIL import Image
from pypdf import PdfReader, PdfWriter
import toolops, toolwin
from toolwin import ToolWindow, OptionsForm

FFMPEG = os.environ.get('OT_FFMPEG')

def pump(app, seconds=.05):
    end = time.monotonic() + seconds
    while time.monotonic() < end: app.processEvents();time.sleep(.005)

class WindowBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.dir = Path(self.tmp.name).resolve();self.settings = QSettings(str(self.dir / 's.ini'), QSettings.IniFormat);self.windows = []
        self.photo = self.dir / 'photo.png';Image.new('RGB', (120, 80), (200, 100, 50)).save(self.photo)
    def tearDown(self):
        for w in self.windows: w.close()
        self.tmp.cleanup()
    def window(self, tool, paths=None):
        w = ToolWindow(toolops.TOOLS[tool], [str(p) for p in (paths or [self.photo])], self.settings);self.windows.append(w);return w
    def pdf(self, name='doc.pdf', pages=3):
        p = self.dir / name;w = PdfWriter()
        for i in range(pages): w.add_blank_page(100 + i * 10, 100)
        with p.open('wb') as f: w.write(f)
        return p
    def run_and_wait(self, w, timeout=60):
        w.run();end = time.monotonic() + timeout
        while w.batch.isRunning(): self.assertLess(time.monotonic(), end);pump(self.app, .02)
        pump(self.app, .1)

class FormTests(WindowBase):
    def test_every_tool_builds_a_form_with_declared_defaults(self):
        for tool in toolops.TOOLS.values():
            values = OptionsForm(tool.fields).values();self.assertEqual(set(values), {f.key for f in tool.fields}, tool.id)
            for f in tool.fields: self.assertAlmostEqual(float(values[f.key]), float(f.default), places=1, msg=(tool.id, f.key)) if f.kind in ('int', 'float') else self.assertEqual(values[f.key], f.default, (tool.id, f.key))
    def test_conditional_rows_follow_the_choice(self):
        form = OptionsForm(toolops.TOOLS['resize_image'].fields);form.show();self.app.processEvents()
        self.assertTrue(form.rows['percent'][1].isVisible());self.assertFalse(form.rows['width'][1].isVisible())
        form.rows['mode'][1].setCurrentIndex(form.rows['mode'][1].findData('fit'));self.assertFalse(form.rows['percent'][1].isVisible());self.assertTrue(form.rows['width'][1].isVisible() and form.rows['height'][1].isVisible())
        form.close()
    def test_slider_range_and_values(self):
        form = OptionsForm(toolops.TOOLS['edit_image'].fields);slider = form.rows['brightness'][1];slider.slider.setValue(200);self.assertAlmostEqual(form.values()['brightness'], 1.0);slider.slider.setValue(0);self.assertAlmostEqual(form.values()['brightness'], -1.0)

class WindowTests(WindowBase):
    def test_crop_needs_a_selection_then_runs(self):
        w = self.window('crop_image');self.assertIsNotNone(w.canvas)
        with self.assertRaises(ValueError): w.collect()
        w.run();self.assertIn('select', w.status.text().lower())
        w.canvas.rects = [(.25, .25, .5, .5)];params, paths = w.collect();self.assertEqual(params['rect'], [[.25, .25, .5, .5]])
        self.run_and_wait(w);self.assertTrue('Done' in w.status.text(), w.status.text());self.assertFalse(w.open_btn.isHidden())
        with Image.open(w.outputs[0]) as im: self.assertEqual(im.size, (60, 40))
    def test_canvas_drag_and_ratio(self):
        w = self.window('crop_image');c = w.canvas;c.resize(500, 400);f = c.frame()
        from PySide6.QtTest import QTest
        from PySide6.QtCore import QPoint
        QTest.mousePress(c, Qt.LeftButton, Qt.NoModifier, QPoint(int(f.left() + 10), int(f.top() + 10)));QTest.mouseMove(c, QPoint(int(f.left() + 110), int(f.top() + 60)));QTest.mouseRelease(c, Qt.LeftButton, Qt.NoModifier, QPoint(int(f.left() + 110), int(f.top() + 60)))
        self.assertEqual(len(c.rects), 1);x, y, rw, rh = c.rects[0];self.assertAlmostEqual(rw * f.width(), 100, delta=2);self.assertAlmostEqual(rh * f.height(), 50, delta=2)
        c.ratio = 1.0;QTest.mousePress(c, Qt.LeftButton, Qt.NoModifier, QPoint(int(f.left() + 10), int(f.top() + 10)));QTest.mouseRelease(c, Qt.LeftButton, Qt.NoModifier, QPoint(int(f.left() + 90), int(f.top() + 30)))
        self.assertEqual(len(c.rects), 1, 'crop keeps one rectangle');x, y, rw, rh = c.rects[0];self.assertAlmostEqual(rw * f.width(), rh * f.height(), delta=2)
        c.clear();self.assertEqual(c.rects, []);self.assertFalse(c.grab().isNull())
    def test_redact_collects_many_areas_and_applies(self):
        w = self.window('redact_image');w.canvas.rects = [(0, 0, .5, .5), (.5, .5, .5, .5)];w.canvas.undo();self.assertEqual(len(w.canvas.rects), 1);w.canvas.rects.append((.5, .5, .4, .4));params, _ = w.collect();self.assertEqual(len(params['rects']), 2)
        self.run_and_wait(w)
        with Image.open(w.outputs[0]) as im: self.assertLess(sum(im.convert('RGB').getpixel((5, 5))), 30)
    def test_live_preview_changes_with_options(self):
        w = self.window('edit_image');w.show();self.app.processEvents();before = w.preview_label.pixmap().toImage().pixel(10, 10) if w.preview_label.pixmap() else None
        w.form.rows['brightness'][1].slider.setValue(200);w.update_preview();after = w.preview_label.pixmap().toImage();self.assertIsNotNone(after);self.assertFalse(after.isNull())
        center = w.preview_label.pixmap().toImage().pixelColor(w.preview_label.pixmap().width() // 2, w.preview_label.pixmap().height() // 2);self.assertGreater(center.red() + center.green() + center.blue(), 200 + 100 + 50)
    def test_resize_reports_the_result_size(self):
        w = self.window('resize_image');w.update_preview();self.assertIn('60×40', w.info.text())
        w.form.rows['mode'][1].setCurrentIndex(w.form.rows['mode'][1].findData('width'));w.form.rows['width'][1].setValue(240);w.update_preview();self.assertIn('240×160', w.info.text())
    def test_order_list_controls_the_order_of_the_inputs(self):
        a, b, c = (self.dir / n for n in ('a.png', 'b.png', 'c.png'))
        for p, colour in ((a, 'red'), (b, 'green'), (c, 'blue')): Image.new('RGB', (40, 30), colour).save(p)
        w = self.window('collage', [a, b, c]);lst = w.order_list;lst.setCurrentRow(2);w.move_row(-1);w.move_row(-1)
        _, paths = w.collect();self.assertEqual([Path(p).name for p in paths], ['c.png', 'a.png', 'b.png'])
        w.form.rows['color'][1].colour = '#000000';w.form.rows['cell'][1].setValue(100);w.form.rows['spacing'][1].setValue(10);w.form.rows['columns'][1].setValue(3);self.run_and_wait(w)
        with Image.open(w.outputs[0]) as im: self.assertEqual(im.convert('RGB').getpixel((60, 60)), (0, 0, 255))
    def test_organize_pages_reorder_rotate_remove(self):
        w = self.window('organize_pdf', [self.pdf(pages=4)]);lst = w.page_list;self.assertEqual(lst.count(), 4)
        lst.item(1).setSelected(True);w.rotate_pages()
        lst.item(3).setSelected(True);lst.item(1).setSelected(False);w.remove_pages();params, _ = w.collect();self.assertEqual([p['page'] for p in params['pages']], [0, 1, 2]);self.assertEqual(params['pages'][1]['rotate'], 90)
        self.run_and_wait(w);out = PdfReader(w.outputs[0]);self.assertEqual(len(out.pages), 3);self.assertEqual(out.pages[1].get('/Rotate'), 90)
        pump(self.app, .3)
    def test_organize_move_buttons_reorder_the_plan(self):
        w = self.window('organize_pdf', [self.pdf(pages=4)]);lst = w.page_list
        lst.item(0).setSelected(True);w.move_pages(1);self.assertEqual([lst.item(i).data(Qt.UserRole)['page'] for i in range(4)], [1, 0, 2, 3])
        lst.clearSelection();lst.item(2).setSelected(True);lst.item(3).setSelected(True);w.move_pages(-1);self.assertEqual([lst.item(i).data(Qt.UserRole)['page'] for i in range(4)], [1, 2, 3, 0])
        lst.clearSelection();lst.item(0).setSelected(True);w.move_pages(-1);self.assertEqual([lst.item(i).data(Qt.UserRole)['page'] for i in range(4)], [1, 2, 3, 0], 'cannot move past the start')
        params, _ = w.collect();self.assertEqual([p['page'] for p in params['pages']], [1, 2, 3, 0]);self.run_and_wait(w)
        self.assertEqual([float(pg.mediabox.width) for pg in PdfReader(w.outputs[0]).pages], [110, 120, 130, 100])
    def test_organize_thumbnails_render_with_page_numbers(self):
        w = self.window('organize_pdf', [self.pdf(pages=3)]);pump(self.app, .6);self.assertEqual(len(w.thumb_base), 3);self.assertFalse(w.page_list.item(0).icon().isNull())
        lst = w.page_list;lst.item(1).setSelected(True);w.rotate_pages();self.assertIn('90', lst.item(1).toolTip())
    def test_organize_refuses_an_empty_plan(self):
        w = self.window('organize_pdf', [self.pdf(pages=2)]);w.page_list.selectAll();w.remove_pages()
        with self.assertRaises(ValueError): w.collect()
    def test_generic_tool_runs_and_never_touches_the_original(self):
        before = self.photo.read_bytes();w = self.window('rotate_image');w.form.rows['rotation'][1].setCurrentIndex(w.form.rows['rotation'][1].findData(90));self.run_and_wait(w)
        with Image.open(w.outputs[0]) as im: self.assertEqual(im.size, (80, 120))
        self.assertEqual(before, self.photo.read_bytes())
    def test_failure_is_shown_not_raised(self):
        import random;random.seed(2);small = self.dir / 's.jpg';noisy = Image.new('RGB', (160, 160));noisy.putdata([(random.randrange(256),) * 3 for _ in range(160 * 160)]);noisy.save(small, quality=12);w = self.window('compress', [small]);self.run_and_wait(w);self.assertEqual(w.outputs, []);self.assertTrue(w.status.text())
        self.assertTrue(w.run_btn.isEnabled())

class FfmpegGateTests(WindowBase):
    def setUp(self):
        super().setUp();from unittest import mock;patcher = mock.patch('engine.find_tool', return_value=None);patcher.start();self.addCleanup(patcher.stop)
    def test_media_tools_ask_for_ffmpeg_and_block_apply(self):
        clip = self.dir / 'a.mp4';clip.write_bytes(b'x');w = self.window('trim', [clip]);w.show();self.app.processEvents()
        self.assertFalse(w.run_btn.isEnabled());self.assertTrue(w.banner.isVisible());self.assertIn('FFmpeg', w.banner_text.text())
        self.settings.setValue('ffmpeg', sys.executable);w.refresh_requirements();self.assertTrue(w.run_btn.isEnabled());self.assertFalse(w.banner.isVisible())
    def test_image_tools_never_ask_for_ffmpeg(self):
        w = self.window('compress');w.show();self.app.processEvents();self.assertTrue(w.run_btn.isEnabled());self.assertFalse(w.banner.isVisible())
        clip = self.dir / 'a.wav';clip.write_bytes(b'x');v = self.window('compress', [clip]);self.assertFalse(v.run_btn.isEnabled())
    @unittest.skipUnless(FFMPEG, 'FFmpeg not available (set OT_FFMPEG)')
    def test_trim_window_probes_and_runs(self):
        import subprocess
        clip = self.dir / 'clip.mp4';subprocess.run([FFMPEG, '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=orange:s=64x64:r=10', '-t', '3', '-pix_fmt', 'yuv420p', str(clip)], check=True)
        self.settings.setValue('ffmpeg', FFMPEG);w = self.window('trim', [clip]);self.assertIn('Length: 0:03', w.info.text())
        w.form.rows['start'][1].setValue(1);w.form.rows['end'][1].setValue(2);self.run_and_wait(w);self.assertTrue('Done' in w.status.text(), w.status.text())

class MainWindowToolsTests(WindowBase):
    def test_tools_button_lists_applicable_tools_and_opens_a_window(self):
        from app import Window
        w = Window();w.add_paths([str(self.photo)]);w.settings = self.settings
        names = [t.id for t in toolops.tools_for(w.paths)];self.assertIn('crop_image', names)
        w.open_tool(toolops.TOOLS['rotate_image']);self.assertEqual(len(w.tool_windows), 1);w.tool_windows[0].close();self.assertEqual(len(w.tool_windows), 0);w.close()

if __name__ == '__main__': unittest.main()
