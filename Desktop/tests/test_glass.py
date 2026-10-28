"""In-window glass picker (community contribution, PR #2) on Windows and Linux."""
import os, sys, tempfile, unittest
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PIL import Image
from app import Window
from glass_wheel import GlassWheel

class GlassTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])
    def test_rounded_panes_match_radial_targets_for_each_file_family(self):
        from glass_design import segment, point, target_at
        for count in (1, 2, 3, 4, 6):
            formats = list(map(str, range(count)))
            for index in range(count):
                location = point(123, index * 360 / count - 90)
                self.assertTrue(segment(index, count).contains(location))
                self.assertEqual(target_at(location, formats), index)
    def test_labels_are_short(self):
        from glass_design import format_label
        self.assertEqual(format_label('Image → PDF'), 'PDF');self.assertEqual(format_label('PDF → DOCX'), 'DOCX');self.assertEqual(format_label('MP4'), 'MP4')
    def test_set_formats_rebuilds_panes(self):
        g = GlassWheel();g.resize(380, 425);self.assertEqual(len(g.buttons), 6)
        g.set_formats(['MP3', 'WAV', 'FLAC']);self.assertEqual(g.formats, ('MP3', 'WAV', 'FLAC'));self.assertEqual(len(g.buttons), 3)
        got = [];g.selected.connect(got.append);g.buttons[1].click();self.assertEqual(got, ['WAV'])
        g.set_formats(());self.assertEqual(g.formats, GlassWheel.formats);g.close()
    def test_window_wheel_follows_files_and_target(self):
        w = Window();w.show();self.app.processEvents()
        self.assertEqual(w.glass.formats, GlassWheel.formats)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'a.srt';p.write_text('1\n00:00:01,000 --> 00:00:02,000\nhi\n');w.add_paths([str(p)])
            self.assertEqual(w.glass.formats, ('SRT → VTT', 'Subtitle → Text'))
            w.glass.selected.emit('Subtitle → Text');self.assertEqual(w.target.currentText(), 'Subtitle → Text')
            w.target.setCurrentText('SRT → VTT');self.assertEqual(w.glass.current, 'SRT → VTT')
            w.clear_files()
            img = Path(d) / 'b.png';Image.new('RGB', (8, 8)).save(img);w.add_paths([str(img)])
            self.assertEqual(len(w.glass.formats), 6);self.assertNotIn('SHA-256', w.glass.formats)
        w.close()
    def test_dark_theme_renders_and_window_follows_setting(self):
        g = GlassWheel();g.resize(380, 425);light = g.grab().toImage();g.set_dark(True);self.assertTrue(g.dark);dark = g.grab().toImage()
        self.assertNotEqual(light.pixelColor(190, 190), dark.pixelColor(190, 190));g.close()        # the hub changes colour
        w = Window();prev = w.settings.value('wheel/theme')
        try:
            w.settings.setValue('wheel/theme', 'dark');self.assertTrue(Window().glass.dark)
            w.settings.setValue('wheel/theme', 'light');self.assertFalse(Window().glass.dark)
        finally:
            if prev is None: w.settings.remove('wheel/theme')
            else: w.settings.setValue('wheel/theme', prev)
            w.close()
    def test_wheel_is_disabled_while_converting(self):
        w = Window();w.set_busy(True);self.assertFalse(w.glass.isEnabled());w.set_busy(False);self.assertTrue(w.glass.isEnabled());w.close()

if __name__ == '__main__': unittest.main()
