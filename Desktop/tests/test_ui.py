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
    def test_new_operations_are_listed_and_options_follow_image_targets(self):
        w=Window()
        for name in ('HEIC','OCR → Text','Office → PDF'):self.assertGreaterEqual(w.target.findText(name),0,name)
        w.target.setCurrentText('HEIC');self.assertTrue(w.width.isEnabled());w.target.setCurrentText('OCR → Text');self.assertFalse(w.width.isEnabled());w.close()
    def test_tools_and_language_are_passed_to_batch(self):
        w=Window();w.settings.setValue('tesseract','C:/t/tesseract.exe');w.lang.setText('eng+deu')
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a.png';Image.new('RGB',(8,8)).save(p);w.add_paths([str(p)]);w.start();opts=w.batch.options;w.batch.cancel.set();w.batch.wait(20000)
        self.assertEqual(opts['tesseract'],'C:/t/tesseract.exe');self.assertEqual(opts['ocr_lang'],'eng+deu');self.assertIn('soffice',opts);w.settings.remove('tesseract');w.close()
    def test_targets_follow_the_listed_files_and_convert_button_explains_itself(self):
        w=Window();w.show();self.app.processEvents();self.assertFalse(w.convert.isEnabled())
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a.srt';p.write_text('1\n00:00:01,000 --> 00:00:02,000\nhi\n');w.add_paths([str(p)])
            items=[w.target.itemText(i) for i in range(w.target.count())];self.assertIn('SRT → VTT',items);self.assertNotIn('PNG',items)
            self.assertTrue(w.convert.isEnabled());self.assertIn('1 file to',w.convert.text());w.list.setCurrentRow(0);w.remove_selected();self.assertEqual(w.paths,[])
        self.assertGreater(w.target.count(),20);w.close()
    def test_missing_helper_shows_banner_and_blocks_convert(self):
        from unittest import mock
        import settings_dialog
        w=Window();w.show()
        with tempfile.TemporaryDirectory() as d,mock.patch('engine.find_tool',return_value=None):
            p=Path(d)/'a.png';Image.new('RGB',(8,8)).save(p);w.add_paths([str(p)]);w.target.setCurrentText('OCR → Text')
            self.assertTrue(w.banner.isVisible());self.assertFalse(w.convert.isEnabled());self.assertTrue(w.lang.isVisible())
            w.target.setCurrentText('PNG');self.assertFalse(w.banner.isVisible());self.assertTrue(w.convert.isEnabled());self.assertFalse(w.lang.isVisible())
        w.close()

class RegressionUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_merge_marks_every_input(self):
        from batch import Batch
        w=Window();w.paths=['/a.pdf','/b.pdf'];w.list.addItems(['a.pdf','b.pdf']);w.batch=Batch(w.paths,'Merge PDFs',{})
        w.result(0,'Done',['/merged.pdf'])
        self.assertTrue(all('✓' in w.list.item(i).text() for i in range(2)));w.batch=None;w.close()
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


class DialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_colour_dialog_presets_set_the_colour(self):
        from PySide6.QtGui import QColor
        import dialogs
        d=dialogs.ColorDialog(QColor('#ff610a'));self.assertEqual(d.colour().name(),'#ff610a')
        d.picker.setCurrentColor(QColor(dialogs.SWATCHES[7]));self.assertEqual(d.colour().name(),dialogs.SWATCHES[7]);d.close()
    def test_info_dialog_and_settings_dialog_build(self):
        import dialogs,settings_dialog
        from PySide6.QtCore import QSettings
        dialogs.InfoDialog('T','intro',[('A','text')]).close();settings_dialog.SettingsDialog(QSettings('Sintax Error Private Limited','Open Tangerine Test')).close()

if __name__=='__main__':unittest.main()
