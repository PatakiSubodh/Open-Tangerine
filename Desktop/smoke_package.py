import json,os,subprocess,sys,tempfile
from pathlib import Path
from PIL import Image
root=Path(__file__).resolve().parent
exe=root/'dist/OpenTangerine'/('OpenTangerine.exe' if os.name=='nt' else 'OpenTangerine')
worker=exe.with_name('OpenTangerineWorker.exe') if os.name=='nt' else exe
worker_flags={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
subprocess.run([str(exe),'--smoke-test'],check=True,timeout=30)
with tempfile.TemporaryDirectory() as folder:
 p=Path(folder)/'input.png';Image.new('RGB',(20,20),'orange').save(p)
 r=subprocess.run([str(worker),'--worker'],input=json.dumps({'paths':[str(p)],'target':'JPEG','output':folder}),text=True,capture_output=True,timeout=30,**worker_flags)
 # The worker remains console-enabled, but its parent starts it without a console window.
 if r.returncode!=0:raise RuntimeError(r.stderr or r.stdout)
 data=json.loads(r.stdout);assert data['ok'];out=Path(data['outputs'][0])
 with Image.open(out) as im:assert im.size==(20,20)

 # Native pieces that PyInstaller can silently drop: Qt SVG, libheif and pdfium.
 def run_worker(job):
  r=subprocess.run([str(worker),'--worker'],input=json.dumps(job),text=True,capture_output=True,timeout=60,**worker_flags)
  data=json.loads(r.stdout)
  if not data['ok']:raise RuntimeError(data['error'])
  return data['outputs']
 svg=Path(folder)/'logo.svg';svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="30" height="10"><rect width="30" height="10" fill="red"/></svg>')
 with Image.open(run_worker({'paths':[str(svg)],'target':'PNG','output':folder})[0]) as im:assert im.size==(30,10)
 heic=run_worker({'paths':[str(p)],'target':'HEIC','output':folder})[0]
 with Image.open(run_worker({'paths':[heic],'target':'PNG','output':folder})[0]) as im:assert im.size==(20,20)
 from pypdf import PdfWriter
 pdf=Path(folder)/'blank.pdf';w=PdfWriter();w.add_blank_page(100,100);w.write(pdf)
 # Stand-in Tesseract (we cannot ship the real one): proves the packaged app renders PDF pages with the bundled pdfium.
 fake=Path(folder)/'fake-tesseract.py';fake.write_text("import sys\nopen(sys.argv[2]+'.txt','w').write('packaged OCR ok')\n")
 if os.name=='nt':ocr=Path(folder)/'fake-tesseract.bat';ocr.write_text(f'@"{sys.executable}" "{fake}" %*'+chr(13)+chr(10))
 else:ocr=Path(folder)/'fake-tesseract';ocr.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{fake}" "$@"'+chr(10));ocr.chmod(0o755)
 assert 'packaged OCR ok' in Path(run_worker({'paths':[str(pdf)],'target':'OCR → Text','output':folder,'tesseract':str(ocr)})[0]).read_text(encoding='utf8')
 from pypdf import PdfReader
 # Phase 1-4 pieces: AVIF encoder, A4 documents, pdfium page rendering, DOCX writer, text layout.
 with Image.open(run_worker({'paths':[str(p)],'target':'AVIF','output':folder})[0]) as im:assert im.size==(20,20)
 txt=Path(folder)/'note.txt';txt.write_text('hello world')
 page=PdfReader(run_worker({'paths':[str(txt)],'target':'Text → PDF','output':folder})[0]).pages[0];assert round(float(page.mediabox.width))==595 and round(float(page.mediabox.height))==842
 with Image.open(run_worker({'paths':[str(pdf)],'target':'PDF → PNG','output':folder})[0]) as im:assert im.size[0]>0
 import zipfile
 with zipfile.ZipFile(run_worker({'paths':[str(p)],'target':'Image → DOCX','output':folder})[0]) as z:assert b'w:w="11906"' in z.read('word/document.xml')
 with Image.open(run_worker({'paths':[str(p)],'target':'tool:edit_image','output':folder,'params':{'exposure':.4,'vignette':.3,'grain':.2}})[0]) as im:assert im.size==(20,20)
 # Editing tools run through the same packaged worker.
 crop=run_worker({'paths':[str(p)],'target':'tool:crop_image','output':folder,'params':{'rect':[[0,0,.5,.5]]}})[0]
 with Image.open(crop) as im:assert im.size==(10,10)
 merged=run_worker({'paths':[str(pdf),str(pdf)],'target':'tool:merge_pdf','output':folder})[0]
 from pypdf import PdfReader
 assert len(PdfReader(merged).pages)==2
 collage=run_worker({'paths':[str(p),str(p)],'target':'tool:collage','output':folder,'params':{'columns':2,'cell':100}})[0]
 with Image.open(collage) as im:assert im.size[0]>200
 # Separate files to one file: every page lands on A4 whatever its source size.
 combined=PdfReader(run_worker({'paths':[str(pdf),str(p),str(txt)],'target':'Combine → PDF','output':folder})[0]).pages
 assert all(round(float(x.mediabox.width))==595 and round(float(x.mediabox.height))==842 for x in combined) and len(combined)>=3
 with zipfile.ZipFile(run_worker({'paths':[str(p),str(txt)],'target':'Combine → DOCX','output':folder})[0]) as z:assert b'w:type="page"' in z.read('word/document.xml')
print('PASS: packaged GUI launch plus PNG, SVG, HEIC, PDF-render/OCR, combine-to-one-file and editing-tool worker jobs')

# Exercise the FFmpeg subprocess under the packaged worker's Linux resource limits.
import shutil
ff=shutil.which('ffmpeg')
if ff:
 with tempfile.TemporaryDirectory() as folder:
  clip=Path(folder)/'clip.mp4'
  subprocess.run([ff,'-nostdin','-v','error','-f','lavfi','-i','testsrc2=s=640x480:r=25','-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','3','-threads','1','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(clip)],check=True,timeout=30)
  result=subprocess.run([str(worker),'--worker'],input=json.dumps({'paths':[str(clip)],'target':'MP4','output':folder,'ffmpeg':str(Path(ff).resolve())}),text=True,capture_output=True,timeout=60,**worker_flags)
  assert result.returncode==0,result.stdout+result.stderr
  data=json.loads(result.stdout);assert data['ok']
  subprocess.run([ff,'-nostdin','-v','error','-xerror','-threads','1','-i',data['outputs'][0],'-f','null','-'],check=True,timeout=30)
 print('PASS: packaged video conversion and full output decode')

# DOCX parsing and the PDF writer load lazily inside the frozen worker.
import sys
sys.path.insert(0,str(root/'tests'))
from docx_fixtures import write_docx,para,run
from pypdf import PdfReader
with tempfile.TemporaryDirectory() as folder:
 p=write_docx(Path(folder)/'input.docx',para(run('Packaged DOCX check'))+para(run('Second page'),page_before=True))
 r=subprocess.run([str(worker),'--worker'],input=json.dumps({'paths':[str(p)],'target':'DOCX → PDF (text only)','output':folder}),text=True,capture_output=True,timeout=30,**worker_flags)
 if r.returncode!=0:raise RuntimeError(r.stderr or r.stdout)
 data=json.loads(r.stdout);assert data['ok'];pdf=PdfReader(data['outputs'][0])
 assert len(pdf.pages)==2 and 'Packaged DOCX check' in pdf.pages[0].extract_text(),data
print('PASS: packaged DOCX to text-only PDF worker conversion')

# Exercise the real frozen GUI's worker selection and JSON pipes together.
with tempfile.TemporaryDirectory() as folder:
 p=Path(folder)/'gui-input.png';Image.new('RGB',(16,12),'orange').save(p)
 before=p.read_bytes()
 subprocess.run([str(exe),'--smoke-test','--smoke-input',str(p)],check=True,timeout=30)
 with Image.open(Path(folder)/'gui-input-converted.jpg') as image:assert image.size==(16,12)
 assert p.read_bytes()==before
print('PASS: packaged GUI-to-worker conversion and original preservation')
