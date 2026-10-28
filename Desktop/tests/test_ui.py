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
        w=Window(global_wheel=False)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'one.png';Image.new('RGB',(8,8)).save(p);w.add_paths([str(p),str(p),d]);self.assertEqual(len(w.paths),1);w.clear_files();self.assertEqual(w.list.count(),0)
        w.close()
    def test_window_and_options(self):
        w=Window(global_wheel=False);w.show();self.app.processEvents();w.target.setCurrentText('Merge PDFs');self.assertFalse(w.width.isEnabled());w.target.setCurrentText('JPEG');self.assertTrue(w.width.isEnabled());w.close()
    def test_new_operations_are_listed_and_options_follow_image_targets(self):
        w=Window(global_wheel=False)
        for name in ('HEIC','OCR → Text','Office → PDF'):self.assertGreaterEqual(w.target.findText(name),0,name)
        w.target.setCurrentText('HEIC');self.assertTrue(w.width.isEnabled());self.assertTrue(w.lang.isHidden())
        w.target.setCurrentText('OCR → Text');self.assertFalse(w.width.isEnabled());self.assertFalse(w.lang.isHidden());w.close()
    def test_tools_and_language_are_passed_to_batch(self):
        w=Window(global_wheel=False);w.settings.setValue('tesseract','C:/t/tesseract.exe');w.lang.setText('eng+deu')
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a.png';Image.new('RGB',(8,8)).save(p);w.add_paths([str(p)]);w.start();opts=w.batch.options;w.batch.cancel.set();w.batch.wait(20000)
        self.assertEqual(opts['tesseract'],'C:/t/tesseract.exe');self.assertEqual(opts['ocr_lang'],'eng+deu');self.assertIn('soffice',opts);w.settings.remove('tesseract');w.close()

class RegressionUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_merge_marks_every_input(self):
        from app import Batch
        w=Window(global_wheel=False);w.paths=['/a.pdf','/b.pdf'];w.list.addItems(['a.pdf','b.pdf']);w.batch=Batch(w.paths,'Merge PDFs',{})
        w.result(0,'Done',['/merged.pdf'])
        self.assertTrue(all('Done' in w.list.item(i).text() for i in range(2)));w.close()
    def test_drag_always_requests_copy(self):
        from PySide6.QtCore import QMimeData,QPoint,QPointF,QUrl,Qt
        from PySide6.QtGui import QDragEnterEvent,QDropEvent
        from app import DropList
        mime=QMimeData();mime.setUrls([QUrl.fromLocalFile('/tmp/example.png')])
        view=DropList();received=[];view.files.connect(received.append)
        for event in [QDragEnterEvent(QPoint(1,1),Qt.CopyAction|Qt.MoveAction,mime,Qt.LeftButton,Qt.ShiftModifier),QDropEvent(QPointF(1,1),Qt.CopyAction|Qt.MoveAction,mime,Qt.LeftButton,Qt.ShiftModifier)]:
            if isinstance(event,QDragEnterEvent):view.dragEnterEvent(event)
            else:view.dropEvent(event)
            self.assertTrue(event.isAccepted());self.assertEqual(event.dropAction(),Qt.CopyAction)
        self.assertEqual(received,[['/tmp/example.png']]);view.close()

    def test_move_only_drag_is_rejected(self):
        from PySide6.QtCore import QMimeData,QPoint,QPointF,QUrl,Qt
        from PySide6.QtGui import QDragEnterEvent,QDropEvent
        from app import DropList
        mime=QMimeData();mime.setUrls([QUrl.fromLocalFile('/tmp/example.png')])
        view=DropList();received=[];view.files.connect(received.append)
        enter=QDragEnterEvent(QPoint(1,1),Qt.MoveAction,mime,Qt.LeftButton,Qt.ShiftModifier)
        drop=QDropEvent(QPointF(1,1),Qt.MoveAction,mime,Qt.LeftButton,Qt.ShiftModifier)
        view.dragEnterEvent(enter);view.dropEvent(drop)
        self.assertFalse(enter.isAccepted());self.assertFalse(drop.isAccepted());self.assertEqual(received,[]);view.close()

if __name__=='__main__':unittest.main()
