"""Open Tangerine desktop trial for Windows and Linux."""
import sys
# Worker never creates the app window or recursively starts the app (SVG rendering uses headless Qt).
if '--worker' in sys.argv:
    from engine import worker_main
    raise SystemExit(worker_main())
import os, signal
from pathlib import Path
from PySide6.QtCore import Qt, Signal, QTimer, QUrl, QSettings
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPainter
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QFileDialog,QComboBox,QListWidget,QProgressBar,QSpinBox,QAbstractItemView,QLineEdit,QMenu)
import engine, prefs, settings_dialog, theme, dialogs
from engine import VERSION, OPERATIONS, IMAGE_OUTPUTS, MEDIA_OUTPUTS, source_file
from batch import Batch
from glass_wheel import GlassWheel, WHEEL_STYLE
WEBSITE='https://sintaxerrorpvtltd.github.io/Open-Tangerine/'

class DropList(QListWidget):
    files=Signal(list);remove=Signal()
    def __init__(self):
        super().__init__();self.setObjectName('drop');self.setAcceptDrops(True);self.setSelectionMode(QAbstractItemView.ExtendedSelection);self.setMinimumHeight(170)
    def paintEvent(self,event):
        super().paintEvent(event)
        if self.count():return
        p=QPainter(self.viewport());p.setPen(QColor('#9a9a9a'));font=p.font();font.setPixelSize(17);p.setFont(font)
        p.drawText(self.viewport().rect(),Qt.AlignCenter,'Drop files here\n\nor click “Add files…”');p.end()
    def keyPressEvent(self,event):
        if event.key() in (Qt.Key_Delete,Qt.Key_Backspace):self.remove.emit()
        else:super().keyPressEvent(event)
    def _drag_style(self,on):self.setProperty('dragging',on);self.style().unpolish(self);self.style().polish(self)
    @staticmethod
    def _copyable(event):
        # Always answer Copy: accepting Explorer's proposed Move would let it delete the original after the drop.
        return bool(event.possibleActions() & Qt.CopyAction) and event.mimeData().hasUrls() and all(u.isLocalFile() for u in event.mimeData().urls())
    def dragEnterEvent(self,event):
        if self._copyable(event):self._drag_style(True);event.setDropAction(Qt.CopyAction);event.accept()
        else:event.ignore()
    def dragMoveEvent(self,event): self.dragEnterEvent(event)
    def dragLeaveEvent(self,event): self._drag_style(False);event.accept()
    def dropEvent(self,event):
        self._drag_style(False)
        if self._copyable(event):
            self.files.emit([u.toLocalFile() for u in event.mimeData().urls()]);event.setDropAction(Qt.CopyAction);event.accept()
        else:event.ignore()

def helper_for(op):
    """Settings key of the optional helper program an operation needs, or ''."""
    return 'tesseract' if op in OCR_OPS else 'soffice' if op=='Office → PDF' else 'ffmpeg' if op in MEDIA_OUTPUTS else ''
OCR_OPS=('OCR → Text','OCR → Searchable PDF')
HINTS={'OCR → Text':'Reads the text in images and scanned PDFs into a .txt file (PDFs up to 50 pages).','OCR → Searchable PDF':'Keeps the page look but makes the text selectable and searchable.','PDF → Text':'Copies the text a PDF already contains. For scans, use OCR instead.','Merge PDFs':'Combines all listed PDFs, in list order, into one file.','Office → PDF':'Word, Excel, PowerPoint and OpenDocument files to PDF.','SHA-256':'Writes a checksum file you can use to verify a download.'}
STYLE=theme.STYLE

class Window(QMainWindow):
    def __init__(self):
        super().__init__();self.paths=[];self.outputs=[];self.batch=None;self.tool_windows=[];self.counts=[0,0]
        self.settings=QSettings('Sintax Error Private Limited','Open Tangerine Desktop')
        self.setWindowTitle('Open Tangerine');self.resize(960,700);self.setMinimumSize(860,600)
        icon=Path(__file__).with_name('icon.png')
        if icon.exists():self.setWindowIcon(QIcon(str(icon)))
        box=QWidget();self.setCentralWidget(box);layout=QVBoxLayout(box);layout.setContentsMargins(28,22,28,16);layout.setSpacing(10)
        head=QHBoxLayout();layout.addLayout(head)
        title=QLabel('Open Tangerine');title.setStyleSheet('font-size:28px;font-weight:bold;color:#ff762b;background:transparent');head.addWidget(title);head.addStretch(1)
        sub=QLabel('Converts files on your computer.\nNothing is uploaded; originals are never changed.');sub.setObjectName('muted');sub.setAlignment(Qt.AlignRight|Qt.AlignVCenter);head.addWidget(sub)
        step=QLabel('1   Add your files');step.setObjectName('step');layout.addWidget(step)
        # Community glass picker (PR #2) beside the list on Windows and Linux; its panes follow the listed files.
        workspace=QHBoxLayout();layout.addLayout(workspace,1)
        self.glass=GlassWheel();self.glass.setStyleSheet(WHEEL_STYLE);self.glass.setMinimumSize(260,292);self.glass.set_dark(prefs.wheel_theme(self.settings)=='dark');workspace.addWidget(self.glass)
        self.list=DropList();self.list.files.connect(self.add_paths);self.list.remove.connect(self.remove_selected);self.list.itemSelectionChanged.connect(self.update_buttons);workspace.addWidget(self.list,1)
        row=QHBoxLayout();layout.addLayout(row)
        self.add=QPushButton('Add files…');self.add.clicked.connect(self.pick);row.addWidget(self.add)
        self.remove=QPushButton('Remove selected');self.remove.setToolTip('Or press Delete');self.remove.clicked.connect(self.remove_selected);row.addWidget(self.remove)
        self.clear=QPushButton('Clear all');self.clear.clicked.connect(self.clear_files);row.addWidget(self.clear);row.addStretch(1)
        self.tools=QPushButton('Edit tools…');self.tools.setToolTip('Crop, trim, compress, merge, redact and more for the files in the list');self.tools.clicked.connect(self.show_tools);row.addWidget(self.tools)
        step=QLabel('2   Choose what to make');step.setObjectName('step');layout.addWidget(step)
        row=QHBoxLayout();layout.addLayout(row);row.addWidget(QLabel('Convert to'))
        self.target=QComboBox();self.target.setMinimumContentsLength(16);self.target.setMaxVisibleItems(20);row.addWidget(self.target,1)
        self.width_label=QLabel('Max size');row.addWidget(self.width_label)
        self.width=QSpinBox();self.width.setRange(0,10000);self.width.setSpecialValueText('Original');self.width.setSuffix(' px');self.width.setAccessibleName('Maximum image side in pixels');self.width.setToolTip('Shrink so the longest side is at most this many pixels');row.addWidget(self.width)
        self.rotate=QComboBox();self.rotate.addItems(['No rotation','Rotate 90° right','Rotate 180°','Rotate 90° left']);row.addWidget(self.rotate)
        self.lang_label=QLabel('OCR language');row.addWidget(self.lang_label)
        self.lang=QLineEdit(self.settings.value('ocr_lang','eng'));self.lang.setMaximumWidth(90);self.lang.setToolTip('Tesseract language code, for example eng or eng+deu. Installed languages are listed in Settings.');self.lang.editingFinished.connect(lambda:self.settings.setValue('ocr_lang',self.lang.text().strip() or 'eng'));row.addWidget(self.lang)
        self.hint=QLabel();self.hint.setObjectName('muted');self.hint.setWordWrap(True);layout.addWidget(self.hint)
        self.banner=QWidget();bl=QHBoxLayout(self.banner);bl.setContentsMargins(0,0,0,0)
        self.banner_text=QLabel();self.banner_text.setObjectName('banner');self.banner_text.setWordWrap(True);self.banner_text.setTextInteractionFlags(Qt.TextSelectableByMouse);bl.addWidget(self.banner_text,1)
        self.banner_btn=QPushButton('Open Settings…');self.banner_btn.clicked.connect(lambda:self.show_settings('formats'));bl.addWidget(self.banner_btn);layout.addWidget(self.banner)
        step=QLabel('3   Convert');step.setObjectName('step');layout.addWidget(step)
        row=QHBoxLayout();layout.addLayout(row)
        self.output='';self.where=QLabel();self.where.setObjectName('muted');self.where.setWordWrap(True);row.addWidget(self.where,1)
        self.folder=QPushButton('Change folder…');self.folder.clicked.connect(self.choose_folder);row.addWidget(self.folder)
        self.folder_reset=QPushButton('Use default');self.folder_reset.setToolTip('Go back to the output folder chosen in Settings');self.folder_reset.clicked.connect(self.reset_folder);row.addWidget(self.folder_reset)
        row=QHBoxLayout();layout.addLayout(row)
        self.convert=QPushButton('Convert');self.convert.setProperty('primary',True);self.convert.clicked.connect(self.start);row.addWidget(self.convert,1)
        self.cancel=QPushButton('Cancel');self.cancel.setVisible(False);self.cancel.clicked.connect(self.cancel_batch);row.addWidget(self.cancel)
        self.open=QPushButton('Show results');self.open.setVisible(False);self.open.setToolTip('Open the folder with the converted files');self.open.clicked.connect(self.open_output);row.addWidget(self.open)
        self.progress=QProgressBar();self.progress.setValue(0);self.progress.setTextVisible(False);self.progress.setVisible(False);layout.addWidget(self.progress)
        self.status=QLabel('');self.status.setWordWrap(True);self.status.setTextFormat(Qt.PlainText);layout.addWidget(self.status)
        foot=QHBoxLayout();layout.addLayout(foot)
        for label,slot,tip in (('Settings','show_settings','Output folder, theme and helper programs'),('Supported formats','show_limits',''),('Downloads / updates','open_site','')):
            b=QPushButton(label);b.setProperty('link',True);b.setToolTip(tip);b.setCursor(Qt.PointingHandCursor);b.clicked.connect(getattr(self,slot));foot.addWidget(b)
        foot.addStretch(1);version=QLabel('Sintax Error Private Limited · GPL-3.0-only · v'+VERSION);version.setObjectName('muted');foot.addWidget(version)
        self.glass.selected.connect(self.target.setCurrentText);self.target.currentTextChanged.connect(self.glass.set_current)
        self.target.currentTextChanged.connect(self.update_options);self.refresh_targets();self.update_folder_label()
    def refresh_targets(self):
        """Offer only what works for every listed file (all operations while the list is empty)."""
        import wheelmodel
        keep=self.target.currentText();options=[o for o in wheelmodel.targets_for(self.paths,limit=None) if o in OPERATIONS] if self.paths else list(OPERATIONS)
        self.target.blockSignals(True);self.target.clear();self.target.addItems(options)
        if keep in options:self.target.setCurrentText(keep)
        self.target.blockSignals(False)
        # The six most common targets as glass panes; the rest stay in the list. An empty queue shows the classic image ring.
        self.glass.set_formats(([t for t in options if t!='SHA-256'][:6] or options) if self.paths else ());self.glass.set_current(self.target.currentText())
        self.update_options()
    def helper_missing(self,op):
        key=helper_for(op)
        return key,bool(key) and not settings_dialog.helper_state(self.settings,key)[0]
    def update_options(self):
        op=self.target.currentText();img=op in [*IMAGE_OUTPUTS,'Image → PDF'];ocr=op in OCR_OPS
        for w in (self.width,self.rotate):w.setEnabled(img);w.setVisible(img)
        self.width_label.setVisible(img);self.lang.setVisible(ocr);self.lang_label.setVisible(ocr)
        hint=HINTS.get(op,'');self.hint.setText(hint);self.hint.setVisible(bool(hint))
        key,missing=self.helper_missing(op);self.banner.setVisible(missing)
        if missing:
            name,_,install=engine.TOOLS[key];self.banner_text.setText(f'{name} is needed for this and was not found on this computer. '+(f'Install it with:  {install}' if os.name=='nt' else 'Install it with your package manager')+'  — then it is picked up automatically, or choose it yourself in Settings.')
        self.update_buttons()
    def update_buttons(self):
        busy=bool(self.batch and self.batch.isRunning());op=self.target.currentText();key,missing=self.helper_missing(op);n=len(self.paths)
        self.convert.setText(f'Convert {n} file{"s" if n!=1 else ""} to {op}' if n and op else 'Convert')
        self.convert.setEnabled(bool(n) and not busy and not missing)
        self.convert.setToolTip('Add at least one file first.' if not n else f'Install {engine.TOOLS[key][0]} first.' if missing else '')
        self.remove.setEnabled(bool(self.list.selectedItems()) and not busy);self.clear.setEnabled(bool(n) and not busy);self.tools.setEnabled(not busy)
    def set_busy(self,busy):
        for w in (self.add,self.folder,self.folder_reset,self.target,self.glass,self.width,self.rotate,self.lang):w.setEnabled(not busy)
        self.cancel.setVisible(busy)
        if busy:self.update_buttons()
        else:self.update_options()
    def update_folder_label(self):
        self.where.setText('Saving to: '+(self.output or prefs.output_folder(self.settings) or 'the same folder as each original file'));self.folder_reset.setVisible(bool(self.output))
    def add_paths(self,paths):
        if self.batch and self.batch.isRunning():return
        errors=[];added=0
        for raw in paths:
            try:
                p=str(source_file(raw))
                if p in self.paths:continue
                if len(self.paths)>=100:raise ValueError('Batch limit: 100 files.')
                self.paths.append(p);self.list.addItem(Path(p).name);added+=1
            except Exception as e:errors.append(f'{Path(raw).name or raw}: {e}')
        if added:self.open.setVisible(False);self.progress.setVisible(False)
        if errors:theme.set_status(self.status,'Skipped '+'; '.join(errors[:3])+(f' (+{len(errors)-3} more)' if len(errors)>3 else ''),'warn')
        else:theme.set_status(self.status,f'{len(self.paths)} file{"s" if len(self.paths)!=1 else ""} ready. Choose what to convert them to.')
        self.refresh_targets()
    def pick(self): self.add_paths(QFileDialog.getOpenFileNames(self,'Select files')[0])
    def remove_selected(self):
        if self.batch and self.batch.isRunning():return
        for r in sorted({self.list.row(i) for i in self.list.selectedItems()},reverse=True):self.list.takeItem(r);del self.paths[r]
        theme.set_status(self.status,f'{len(self.paths)} file(s) left.' if self.paths else '');self.refresh_targets()
    def clear_files(self):
        self.paths=[];self.list.clear();self.outputs=[];self.open.setVisible(False);self.progress.setVisible(False);theme.set_status(self.status,'');self.refresh_targets()
    def choose_folder(self):
        folder=QFileDialog.getExistingDirectory(self,'Choose output folder')
        if folder:self.output=folder;self.update_folder_label()
    def reset_folder(self):self.output='';self.update_folder_label()
    def open_site(self):QDesktopServices.openUrl(QUrl(WEBSITE+'?platform=desktop&version='+VERSION+'#desktop'))
    def show_settings(self,tab='general'):
        settings_dialog.SettingsDialog(self.settings,self,tab=tab if isinstance(tab,str) else 'general').exec();self.update_folder_label();self.update_options();self.glass.set_dark(prefs.wheel_theme(self.settings)=='dark')
    def show_limits(self):
        dialogs.InfoDialog('Supported formats','Everything runs on this computer. Failed files never stop the rest of a batch.',[
            ('Images','Output: PNG, JPEG, WebP, AVIF, TIFF, BMP, HEIC. Input also includes SVG. Resize and rotate. Single-frame only (HEIC: primary image), up to 40 megapixels. SVG is drawn at its own size, or scaled to the maximum side you set. RAW is not supported.'),
            ('Documents','Image to PDF or DOCX (A4 pages), merge PDFs (up to 200 pages), split, extract text, pages to PNG/JPEG, PDF to DOCX. Text files to PDF, PNG, JPEG, SRT or VTT. Password-protected PDFs are not supported.'),
            ('OCR (needs Tesseract)','Images and PDFs up to 50 pages, to a text file or a searchable PDF. Tesseract is found automatically when installed, or choose it in Settings.'),
            ('Office (needs LibreOffice)','Word, Excel, PowerPoint and OpenDocument files to PDF. LibreOffice is found automatically when installed, or choose it in Settings.'),
            ('Audio and video (needs FFmpeg)','MP4, WebM, MOV, MKV, AVI, WMV, GIF, MP3, M4A, WAV, FLAC, Ogg, Opus, AIFF and WMA. Codecs depend on your FFmpeg. FFmpeg is found automatically when installed, or choose it in Settings.'),
            ('Subtitles and checksums','SRT and VTT conversion (also to plain text), and SHA-256 checksums.'),
            ('Good to know','Workers have time and output limits but are not an operating-system sandbox, so process trusted files. Archives and the Mac notch are not included.')],self).exec()
    def start(self):
        if not self.paths:return
        self.outputs=[];self.counts=[0,0];self.open.setVisible(False);self.progress.setValue(0);self.progress.setVisible(True)
        for i,p in enumerate(self.paths):self.list.item(i).setText(Path(p).name);self.list.item(i).setForeground(QColor('#f5f3ed'))
        theme.set_status(self.status,'Converting…')
        self.batch=Batch(list(self.paths),self.target.currentText(),{'output':self.output or prefs.output_folder(self.settings),'width':self.width.value(),'rotation':self.rotate.currentIndex()*90,'ffmpeg':self.settings.value('ffmpeg',''),'tesseract':self.settings.value('tesseract',''),'soffice':self.settings.value('soffice',''),'ocr_lang':self.lang.text().strip() or 'eng'})
        self.batch.result.connect(self.result);self.batch.progress.connect(lambda n,total:self.progress.setValue(round(n/total*100)));self.batch.finished.connect(self.finished);self.set_busy(True);self.batch.start()
    def result(self,index,status,outputs):
        self.outputs.extend(outputs);ok=status=='Done';self.counts[0 if ok else 1]+=1
        rows=range(len(self.paths)) if self.batch and self.batch.combined() else [index]
        for r in rows:
            item=self.list.item(r)
            if not item:continue
            name=Path(self.paths[r]).name
            item.setText(f'✓  {name}  →  {Path(outputs[0]).name}' if ok and outputs else f'✓  {name}' if ok else f'✕  {name} — {status}')
            item.setForeground(QColor('#7bd88f' if ok else '#ff7b7b'));item.setToolTip(chr(10).join(outputs) or status)
        self.open.setVisible(bool(self.outputs))
    def finished(self):
        done,failed=self.counts;self.set_busy(False)
        if self.outputs and prefs.reveal_results(self.settings):self.open_output()
        if failed:theme.set_status(self.status,f'{done} succeeded, {failed} had a problem. Hover a ✕ row for details; the other files are not affected.','warn')
        else:theme.set_status(self.status,f'All done: {len(self.outputs)} file{"s" if len(self.outputs)!=1 else ""} created.' if self.outputs else 'Stopped before anything was created.','ok' if self.outputs else '')
    def cancel_batch(self):
        if self.batch:self.batch.cancel.set();theme.set_status(self.status,'Cancelling… files already converted are kept.')
    def open_output(self):
        if self.outputs:QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.outputs[-1]).parent)))
    def show_tools(self):
        import toolops
        available=toolops.tools_for(self.paths);menu=QMenu(self)
        if not self.paths:menu.addAction('Add files first').setEnabled(False)
        elif not available:menu.addAction('No tools for this mix of files').setEnabled(False)
        for tool in available:menu.addAction(f'{tool.title}  —  {tool.caption}').triggered.connect(lambda _=False,t=tool:self.open_tool(t))
        menu.exec(self.tools.mapToGlobal(self.tools.rect().bottomLeft()))
    def open_tool(self,tool):
        import toolwin
        window=toolwin.ToolWindow(tool,list(self.paths),self.settings);self.tool_windows.append(window)
        window.finished.connect(lambda _=0,w=window:self.tool_windows.remove(w) if w in self.tool_windows else None);window.show()
    def bring_forward(self):self.showNormal();self.raise_();self.activateWindow()
    def quit_app(self):
        for w in list(self.tool_windows):w.close()
        self.close()
    def closeEvent(self,event):
        if self.batch and self.batch.isRunning():
            self.batch.cancel.set();event.ignore();theme.set_status(self.status,'Stopping conversion before closing…');QTimer.singleShot(200,self.close)
        else:event.accept()

INSTANCE='SintaxError.OpenTangerine.Desktop.instance'
def main():
    if os.name=='nt' and getattr(sys,'frozen',False):
        import ctypes
        handle=ctypes.windll.kernel32.GetConsoleWindow()
        if handle: ctypes.windll.user32.ShowWindow(handle,0)
    if os.name=='nt':
        # Own taskbar identity, otherwise Windows groups the window under python(w).exe and shows its icon.
        import ctypes
        try:ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('SintaxError.OpenTangerine.Desktop')
        except Exception:pass
    app=QApplication(sys.argv);app.setStyle('Fusion');app.setWindowIcon(QIcon(str(Path(__file__).with_name('icon.png'))));theme.apply(app)
    # Single instance: a second launch asks the running one to show itself and exits.
    guard=QLocalSocket();guard.connectToServer(INSTANCE)
    if '--smoke-test' not in sys.argv and guard.waitForConnected(300):
        guard.write(b'show');guard.waitForBytesWritten(300)
        return 0
    QLocalServer.removeServer(INSTANCE);server=QLocalServer();server.listen(INSTANCE)
    window=Window()
    server.newConnection.connect(lambda:(server.nextPendingConnection(),window.bring_forward()))
    window.show()
    if '--smoke-test' in sys.argv:
        # Exercise the lazily imported tool window (Pillow preview, canvas, form) from the packaged build.
        import toolops, toolwin
        tool_window=toolwin.ToolWindow(toolops.TOOLS['crop_image'],[str(Path(__file__).with_name('icon.png'))],window.settings);tool_window.show()
        QTimer.singleShot(500,tool_window.close);QTimer.singleShot(700,app.quit)
    # Ctrl+C in the terminal: Python only sees the signal when it gets control back from Qt, so tick a timer and quit cleanly.
    signal.signal(signal.SIGINT,lambda *_:QTimer.singleShot(0,window.quit_app));tick=QTimer();tick.start(250);tick.timeout.connect(lambda:None)
    return app.exec()
if __name__=='__main__':raise SystemExit(main())
