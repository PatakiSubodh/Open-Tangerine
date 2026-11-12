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
        return Window(**({'enable_wheel': False} if 'enable_wheel' in params else {'global_wheel': False}))

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


if __name__ == '__main__':
    unittest.main()
