import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch, Mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QObject, QMimeData, QPointF, QUrl, Qt, QEventLoop, QTimer, Signal
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication, QSystemTrayIcon
from island import ConversionIsland, RETRACT_MS, MARGIN, WIDTH, HEIGHT
from app import Window


class FakeBatch(QObject):
    progress = Signal(int, int)
    finished = Signal()

    def __init__(self):
        super().__init__(); self.cancel = threading.Event()


class IslandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.still = patch('island.animations_enabled', return_value=False); self.still.start()
        self.addCleanup(self.still.stop)

    def test_single_output_offers_open(self):
        window = Window(); island = ConversionIsland(window)
        batch = FakeBatch()
        self.assertTrue(island.track(batch, 'Image → PDF', 1))
        self.assertEqual(island.title.text(), 'Converting 1 file to PDF')
        self.assertEqual(island.bar.maximum(), 0)
        window.outputs = [str(Path(tempfile.gettempdir())/'only.pdf')]; window.batch_errors = []
        batch.finished.emit()
        self.assertEqual(island.phase, 'done')
        self.assertTrue(island.open_button.isVisibleTo(island))
        self.assertEqual(island.detail.text(), 'Ready · only.pdf')
        with patch('island.QDesktopServices.openUrl') as open_url:
            island.open_button.click()
            self.assertEqual(open_url.call_args.args[0].toLocalFile(), Path(window.outputs[0]).as_posix())
        island.stop(); window.close()

    def test_cancelled_batch_reports_kept_outputs_and_retracts(self):
        window = Window(); island = ConversionIsland(window)
        batch = FakeBatch(); island.track(batch, 'PNG', 3)
        batch.progress.emit(1, 3)
        self.assertEqual((island.bar.value(), island.bar.maximum()), (1, 3))
        self.assertEqual(island.detail.text(), '1 of 3 done')
        window.outputs = ['a.png']; window.batch_errors = ['Cancelled; completed outputs are kept.']
        batch.cancel.set(); batch.finished.emit()
        self.assertEqual(island.phase, 'cancelled')
        self.assertEqual(island.detail.text(), '1 completed output(s) kept')
        self.assertTrue(island.retract_timer.isActive())
        island.stop(); window.close()

    def test_stale_batch_signals_are_ignored(self):
        window = Window(); island = ConversionIsland(window)
        old, new = FakeBatch(), FakeBatch()
        island.track(old, 'PNG', 2); island.track(new, 'JPEG', 2)
        window.outputs = []; window.batch_errors = ['old failure']
        old.progress.emit(2, 2); old.finished.emit()
        self.assertEqual(island.phase, 'running')
        self.assertEqual(island.title.text(), 'Converting 2 files to JPEG')
        self.assertTrue(island.handles(new)); self.assertFalse(island.handles(old))
        island.stop(); window.close()

    def test_off_style_never_shows(self):
        window = Window(); island = ConversionIsland(window, 'Off')
        self.assertFalse(island.track(FakeBatch(), 'PNG', 1))
        self.assertFalse(island.isVisible())
        island.set_style('Glass'); self.assertTrue(island.track(FakeBatch(), 'PNG', 1))
        self.assertTrue(island.isVisible())
        island.set_style('Off'); self.assertFalse(island.isVisible())
        island.set_style('unknown'); self.assertEqual(island.style_name, 'Pure black')
        island.stop(); window.close()

    def test_off_during_batch_restores_tray_feedback(self):
        window = Window(); window.island = ConversionIsland(window)
        batch = FakeBatch(); window.batch = batch
        window.island.track(batch, 'PNG', 1)
        window.island.set_style('Off')
        self.assertFalse(window.island.handles(batch))
        window.outputs = []; window.batch_errors = ['failed']
        batch.finished.emit()
        self.assertEqual(window.island.phase, 'idle')
        self.assertFalse(window.island.retract_timer.isActive())
        window.batch = None; window.close()

    def test_island_never_takes_drops_or_focus(self):
        island = ConversionIsland(Mock())
        self.assertFalse(island.acceptDrops())
        self.assertTrue(island.windowFlags() & Qt.WindowDoesNotAcceptFocus)
        self.assertTrue(island.testAttribute(Qt.WA_ShowWithoutActivating))
        island.close()

    def test_top_center_of_cursor_screen_work_area(self):
        island = ConversionIsland(Mock())
        area = (QApplication.screenAt(island.cursor().pos()) or QApplication.primaryScreen()).availableGeometry()
        resting, hidden = island.placement()
        self.assertEqual(resting.x(), area.center().x() - WIDTH // 2)
        self.assertEqual(resting.y(), area.top() + MARGIN)
        self.assertLess(hidden, area.top())
        island.close()

    def test_reopening_interrupts_retraction(self):
        window = Window(); island = ConversionIsland(window)
        island.track(FakeBatch(), 'PNG', 1)
        with patch('island.animations_enabled', return_value=True):
            island.retract()
            self.assertTrue(island.retracting)
            island.track(FakeBatch(), 'JPEG', 1)
            self.assertFalse(island.retracting)
            island.motion_finished()
        self.assertTrue(island.isVisible())
        self.assertEqual(island.phase, 'running')
        island.stop(); window.close()


class WheelIslandTests(unittest.TestCase):
    """The drag wheel reports conversions in the island, or in the card when that is chosen in Settings."""
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from PySide6.QtCore import QSettings
        self.still = patch('island.animations_enabled', return_value=False); self.still.start()
        self.addCleanup(self.still.stop)
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name).resolve()
        self.settings = QSettings(str(self.dir / 's.ini'), QSettings.IniFormat)

    def controller(self):
        import wheel
        c = wheel.WheelController(self.settings); self.addCleanup(c.shutdown)
        return c

    def run_batch(self, c, paths, target):
        c.convert([str(p) for p in paths], target)
        loop = QEventLoop(); c.batch.finished.connect(loop.quit)
        timeout = QTimer(); timeout.setSingleShot(True); timeout.timeout.connect(loop.quit); timeout.start(15000)
        loop.exec(); timeout.stop(); self.app.processEvents()
        self.assertFalse(c.batch.isRunning())

    def images(self, *names):
        from PIL import Image
        paths = [self.dir / name for name in names]
        for path in paths: Image.new('RGB', (8, 8), 'orange').save(path)
        return paths

    def test_new_installs_use_the_island_and_old_settings_carry_over(self):
        import prefs, island
        self.assertEqual(prefs.wheel_progress(self.settings), 'Pure black')
        self.settings.setValue('islandStyle', 'Glass'); self.assertEqual(prefs.wheel_progress(self.settings), 'Glass')
        self.settings.setValue('islandStyle', 'Off'); self.assertEqual(prefs.wheel_progress(self.settings), 'card')
        self.settings.setValue('wheel/progress', 'Pure black'); self.assertEqual(prefs.wheel_progress(self.settings), 'Pure black')
        self.assertEqual(set(prefs.ISLAND_STYLES) | {'Off'}, set(island.STYLES))

    def test_wheel_success_shows_island_then_retracts(self):
        c = self.controller()
        self.run_batch(c, self.images('a.png', 'b.png'), 'JPEG')
        self.assertTrue(c.island.isVisible()); self.assertEqual(c.island.phase, 'done')
        self.assertEqual(c.island.title.text(), 'Converted 2 files to JPEG')
        self.assertEqual(len(c.island.outputs), 2); self.assertFalse(c.notch.isVisible())
        self.assertTrue(c.island.retract_timer.isActive())
        c.island.retract_timer.timeout.emit(); self.assertFalse(c.island.isVisible())

    def test_wheel_failure_stays_until_dismissed(self):
        c = self.controller()
        bad = self.dir / 'bad.png'; bad.write_bytes(b'broken')
        self.run_batch(c, [bad], 'JPEG')
        self.assertEqual(c.island.phase, 'failed'); self.assertTrue(c.island.isVisible())
        self.assertEqual(c.island.detail.text(), c.batch_errors[0])
        self.assertFalse(c.island.retract_timer.isActive())
        c.island.dismiss_button.click(); self.assertFalse(c.island.isVisible())

    def test_card_choice_reports_conversions_in_the_card(self):
        c = self.controller(); c.set_progress('card')
        self.run_batch(c, self.images('a.png'), 'JPEG')
        self.assertFalse(c.island.isVisible()); self.assertEqual(c.notch.kind, 'ok')
        c.set_progress('Glass'); self.assertEqual(c.island.style_name, 'Glass')
        self.assertEqual(self.settings.value('wheel/progress'), 'Glass')


if __name__ == '__main__':
    unittest.main()
