import os, sys, unittest
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication, QScrollArea, QWidget
import screenfit


class FakeScreen:
    def __init__(self, rect): self.rect = rect
    def availableGeometry(self): return self.rect


class ScreenFitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def make_window(self):
        from app import Window
        import inspect
        params = inspect.signature(Window.__init__).parameters
        # Whichever switch this version of the window has for the Windows drag wheel; off in tests.
        flag = next((name for name in ('enable_wheel', 'global_wheel') if name in params), None)
        return Window(**({flag: False} if flag else {}))

    def test_keeps_preferred_size_on_a_large_screen(self):
        self.assertEqual(screenfit.fitted_size(960, 700, QRect(0, 0, 2560, 1400)), (960, 700))

    def test_shrinks_to_small_or_scaled_screens(self):
        # 1366x768 at 150% leaves about 910x480 usable.
        w, h = screenfit.fitted_size(960, 700, QRect(0, 0, 910, 480))
        self.assertLessEqual(w, 910); self.assertLessEqual(h, 480)

    def test_never_below_the_window_minimum(self):
        self.assertEqual(screenfit.fitted_size(960, 700, QRect(0, 0, 200, 150)), screenfit.MINIMUM)

    def test_window_opens_inside_the_screen(self):
        window = self.make_window()
        area = QRect(100, 50, 1000, 520)
        screenfit.fit(window, 960, 700, FakeScreen(area))
        self.assertTrue(area.contains(QRect(window.pos(), window.size())))
        window.close()

    def test_short_window_scrolls_instead_of_overlapping(self):
        window = self.make_window()
        self.assertIsInstance(window.centralWidget(), QScrollArea)
        window.resize(*screenfit.MINIMUM); window.show(); self.app.processEvents()
        content = window.centralWidget().widget()
        # The content keeps the height its layout needs; the scroll area absorbs the difference.
        self.assertGreaterEqual(content.height(), content.layout().minimumSize().height())
        self.assertGreater(content.height(), window.centralWidget().viewport().height())
        window.close()

    def test_moving_to_a_smaller_screen_shrinks_the_window(self):
        window = self.make_window()
        window.resize(1200, 900)
        screenfit.shrink_to(window, FakeScreen(QRect(0, 0, 800, 450)))
        size = QWidget.size(window)
        self.assertLessEqual(size.width(), 800); self.assertLessEqual(size.height(), 450)
        window.close()

    def test_secondary_windows_can_shrink_to_small_screens(self):
        import settings_dialog, dialogs
        window = self.make_window()
        for dialog in (settings_dialog.SettingsDialog(window.settings, window),
                       dialogs.InfoDialog('Supported formats', 'intro', [('Images', 'text ' * 80)] * 8, window)):
            dialog.show(); self.app.processEvents()
            hint = dialog.minimumSizeHint().expandedTo(dialog.minimumSize())
            self.assertLessEqual(hint.width(), 640, type(dialog).__name__)
            self.assertLessEqual(hint.height(), 360, type(dialog).__name__)
            dialog.close()
        window.close()

    def test_window_is_moved_fully_onto_its_screen(self):
        window = self.make_window(); window.show(); self.app.processEvents()
        area = window.screen().availableGeometry()
        window.move(area.right() - 50, area.bottom() - 50)
        screenfit.keep_on_screen(window)
        self.assertTrue(area.contains(window.frameGeometry()))
        window.close()


if __name__ == '__main__':
    unittest.main()
