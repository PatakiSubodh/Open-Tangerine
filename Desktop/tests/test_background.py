import os
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication, QSystemTrayIcon
from app import Window, background_startup
from background import BackgroundController


class BackgroundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_background_is_explicit_and_window_override(self):
        self.assertFalse(background_startup([], windows=True))
        self.assertFalse(background_startup(['--window'], windows=True))
        self.assertTrue(background_startup(['--background'], windows=True))
        self.assertTrue(background_startup(['--headless'], windows=True))
        self.assertFalse(background_startup(['--smoke-test'], windows=True))
        self.assertFalse(background_startup([], windows=False))

    def test_close_hides_and_preserves_running_conversion(self):
        w = Window(global_wheel=False)
        w.background = Mock(); w.shift_wheel = Mock()
        w.batch = Mock(); w.batch.isRunning.return_value = True
        w.show(); w.close()
        self.assertFalse(w.isVisible())
        w.batch.cancel.set.assert_not_called()
        w.shift_wheel.stop.assert_not_called()
        w.background.stop.assert_not_called()
        w.batch = None; w.background = None; w.close()

    def test_tray_status_failures_restore_and_explicit_quit(self):
        w = Window(global_wheel=False)
        previous = self.app.quitOnLastWindowClosed()
        with patch.object(QSystemTrayIcon, 'isSystemTrayAvailable', return_value=True), \
             patch.object(QSystemTrayIcon, 'show'), \
             patch.object(QSystemTrayIcon, 'showMessage') as notify, \
             patch.object(QApplication, 'quit') as quit_app:
            w.background = BackgroundController(w)
            w.background.started()
            self.assertTrue(w.background.cancel.isEnabled())
            w.batch_errors = ['Unsupported file contents.']
            w.background.finished()
            notify.assert_called_once()
            self.assertIn('Unsupported file contents.', notify.call_args.args)
            self.assertFalse(w.background.cancel.isEnabled())
            w.background.activated(QSystemTrayIcon.DoubleClick)
            self.assertTrue(w.isVisible())
            w.close(); self.assertFalse(w.isVisible())
            quit_app.assert_not_called()
            w.request_quit(); quit_app.assert_called_once()
        self.app.setQuitOnLastWindowClosed(previous)

    def test_quit_waits_for_busy_worker_before_stopping_tray(self):
        w = Window(global_wheel=False)
        w.background = Mock(); w.shift_wheel = Mock()
        w.batch = Mock(); w.batch.isRunning.return_value = True
        with patch('app.QTimer.singleShot') as schedule, patch.object(QApplication, 'quit') as quit_app:
            w.request_quit()
            w.batch.cancel.set.assert_called_once()
            w.background.stop.assert_not_called()
            quit_app.assert_not_called()
            schedule.assert_called_once()
            w.batch.isRunning.return_value = False
            w.close()
            w.background.stop.assert_called_once()
            quit_app.assert_called_once()
        w.background = None; w.batch = None

    def test_background_requires_reachable_tray(self):
        w = Window(global_wheel=False)
        with patch.object(QSystemTrayIcon, 'isSystemTrayAvailable', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'system tray'):
                BackgroundController(w)
        w.close()


if __name__ == '__main__':
    unittest.main()
