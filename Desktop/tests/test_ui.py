import os,sys,tempfile,unittest
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from app import Window
from PIL import Image
class UITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_queue_deduplicates_and_rejects_directory(self):
        w=Window()
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'one.png';Image.new('RGB',(8,8)).save(p);w.add_paths([str(p),str(p),d]);self.assertEqual(len(w.paths),1);w.clear_files();self.assertEqual(w.list.count(),0)
        w.close()
    def test_window_and_options(self):
        w=Window();w.show();self.app.processEvents();w.target.setCurrentText('Merge PDFs');self.assertFalse(w.width.isEnabled());w.target.setCurrentText('JPEG');self.assertTrue(w.width.isEnabled());w.close()
if __name__=='__main__':unittest.main()
