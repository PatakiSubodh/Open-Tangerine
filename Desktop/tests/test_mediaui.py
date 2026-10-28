"""Windows for Bleep audio and Redact video (offscreen Qt)."""
import os, subprocess, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_toolwin import WindowBase, pump
import toolops

FFMPEG = os.environ.get('OT_FFMPEG')

class WithoutFfmpeg(WindowBase):
    def test_windows_build_without_ffmpeg_and_validate_input(self):
        wav = self.dir / 'a.wav';wav.write_bytes(b'RIFF');mp4 = self.dir / 'v.mp4';mp4.write_bytes(b'x')
        self.assertEqual(self.window('bleep_audio', [wav]).media_panel.collect(), {'ranges': [[0.0, 1.0]]})
        with self.assertRaisesRegex(ValueError, 'at least one area'): self.window('redact_video', [mp4]).media_panel.collect()

@unittest.skipUnless(FFMPEG, 'FFmpeg not installed (set OT_FFMPEG)')
class Windows(WindowBase):
    def setUp(self):
        super().setUp();self.settings.setValue('ffmpeg', FFMPEG)
        self.wav = self.dir / 'tone.wav';self.mp4 = self.dir / 'clip.mp4'
        subprocess.run([FFMPEG, '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=24000', '-t', '3', '-ac', '2', str(self.wav)], check=True)
        subprocess.run([FFMPEG, '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=red:s=320x240:r=15', '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=24000', '-t', '3', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(self.mp4)], check=True)

    def test_bleep_window_collects_ranges_and_runs(self):
        w = self.window('bleep_audio', [self.wav]);panel = w.media_panel;self.assertEqual(len(panel.ranges.rows), 1)
        self.assertEqual(panel.collect(), {'ranges': [[0.0, 1.0]]})
        panel.ranges.add(1.5, 2.0);panel.ranges.rows[0].start.setValue(.25);self.assertEqual(panel.collect()['ranges'], [[.25, 1.0], [1.5, 2.0]])
        self.assertIn('Length', w.info.text())
        self.run_and_wait(w);self.assertTrue(any(p.name == 'tone-bleeped.wav' for p in self.dir.iterdir()), [p.name for p in self.dir.iterdir()])
        self.assertIn('Done', w.status.text())
    def test_bleep_window_rejects_backwards_ranges_and_can_remove_rows(self):
        w = self.window('bleep_audio', [self.wav]);panel = w.media_panel;panel.ranges.rows[0].end.setValue(0)
        with self.assertRaisesRegex(ValueError, 'Part 1 must end'): panel.collect()
        panel.ranges.add(1, 2);panel.ranges.remove(panel.ranges.rows[0]);self.assertEqual([r.title.text() for r in panel.ranges.rows], ['Part 1']);panel.ranges.remove(panel.ranges.rows[0])
        with self.assertRaisesRegex(ValueError, 'at least one'): panel.collect()
        w.run();self.assertFalse(w.batch is not None and w.batch.isRunning())
    def test_redact_window_shows_a_frame_and_collects_boxes_with_times(self):
        w = self.window('redact_video', [self.mp4]);panel = w.media_panel;pump(self.app, .2)
        self.assertEqual((panel.canvas.pixmap.width(), panel.canvas.pixmap.height()), (320, 240));self.assertGreater(panel.duration, 2.5)
        with self.assertRaisesRegex(ValueError, 'at least one area'): panel.collect()
        panel.canvas.rects.extend([(0, 0, .5, .5), (.5, .5, .5, .5)]);panel.canvas.changed.emit();self.assertEqual(len(panel.areas.rows), 2)
        panel.areas.rows[0].start.setValue(1);panel.areas.rows[0].end.setValue(2)
        self.assertEqual(panel.collect()['boxes'], [[0, 0, .5, .5, 1.0, 2.0], [.5, .5, .5, .5, 0.0, 0.0]])
        panel.canvas.undo();self.assertEqual(len(panel.areas.rows), 1);panel.areas.rows[0].start.setValue(2);panel.areas.rows[0].end.setValue(1)
        with self.assertRaisesRegex(ValueError, 'Area 1 must end'): panel.collect()
        panel.canvas.clear();self.assertEqual(len(panel.areas.rows), 0)
    def test_redact_window_runs_end_to_end(self):
        w = self.window('redact_video', [self.mp4]);panel = w.media_panel;panel.canvas.rects.append((0, 0, .5, .5));panel.canvas.changed.emit()
        w.form.rows['style'][1].setCurrentIndex(0);self.run_and_wait(w);self.assertTrue((self.dir / 'clip-redacted.mp4').is_file());self.assertIn('Done', w.status.text())
    def test_moving_the_frame_slider_loads_another_frame(self):
        w = self.window('redact_video', [self.mp4]);panel = w.media_panel;pump(self.app, .2);panel.slider.setValue(900);pump(self.app, .6)
        self.assertIn(':', panel.when.text());self.assertNotEqual(panel.when.text(), '0:00.0');self.assertEqual(panel.canvas.pixmap.width(), 320)

if __name__ == '__main__': unittest.main()
