import json,os,subprocess,tempfile
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
 from pypdf import PdfReader
 # AVIF encoder, A4 documents, pdfium page rendering, DOCX writer, text layout.
 with Image.open(run_worker({'paths':[str(p)],'target':'AVIF','output':folder})[0]) as im:assert im.size==(20,20)
 txt=Path(folder)/'note.txt';txt.write_text('hello world')
 page=PdfReader(run_worker({'paths':[str(txt)],'target':'Text → PDF','output':folder})[0]).pages[0];assert round(float(page.mediabox.width))==595 and round(float(page.mediabox.height))==842
 with Image.open(run_worker({'paths':[str(pdf)],'target':'PDF → PNG','output':folder})[0]) as im:assert im.size[0]>0
 import zipfile
 with zipfile.ZipFile(run_worker({'paths':[str(p)],'target':'Image → DOCX','output':folder})[0]) as z:assert b'w:w="11906"' in z.read('word/document.xml')
print('PASS: packaged GUI launch plus PNG, SVG, HEIC, AVIF, PDF-render and document worker jobs')

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
