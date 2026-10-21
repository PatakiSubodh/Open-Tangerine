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

class RegressionUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_merge_marks_every_input(self):
        from app import Batch
        w=Window();w.paths=['/a.pdf','/b.pdf'];w.list.addItems(['a.pdf','b.pdf']);w.batch=Batch(w.paths,'Merge PDFs',{})
        w.result(0,'Done',['/merged.pdf'])
        self.assertTrue(all('Done' in w.list.item(i).text() for i in range(2)));w.close()
    def test_drag_always_requests_copy(self):
        from unittest.mock import Mock
        from PySide6.QtCore import QUrl,Qt
        from app import DropList
        event=Mock();event.mimeData.return_value.hasUrls.return_value=True;event.mimeData.return_value.urls.return_value=[QUrl.fromLocalFile('/tmp/example.png')]
        view=DropList();view.dragEnterEvent(event);event.setDropAction.assert_called_with(Qt.CopyAction);view.dropEvent(event);event.setDropAction.assert_called_with(Qt.CopyAction)
