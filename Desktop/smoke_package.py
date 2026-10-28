import json,os,subprocess,tempfile
from pathlib import Path
from PIL import Image
root=Path(__file__).resolve().parent
exe=root/'dist/OpenTangerine'/('OpenTangerine.exe' if os.name=='nt' else 'OpenTangerine')
subprocess.run([str(exe),'--smoke-test'],check=True,timeout=30)
with tempfile.TemporaryDirectory() as folder:
 p=Path(folder)/'input.png';Image.new('RGB',(20,20),'orange').save(p)
 r=subprocess.run([str(exe),'--worker'],input=json.dumps({'paths':[str(p)],'target':'JPEG','output':folder}),text=True,capture_output=True,timeout=30)
 # A Windows --windowed executable has no standard streams. Build uses console
 # mode so the conversion worker protocol remains available on both platforms.
 if r.returncode!=0:raise RuntimeError(r.stderr or r.stdout)
 data=json.loads(r.stdout);assert data['ok'];out=Path(data['outputs'][0])
 with Image.open(out) as im:assert im.size==(20,20)

 # Native pieces that PyInstaller can silently drop: Qt SVG, libheif and pdfium.
 def worker(job):
  r=subprocess.run([str(exe),'--worker'],input=json.dumps(job),text=True,capture_output=True,timeout=60)
  data=json.loads(r.stdout)
  if not data['ok']:raise RuntimeError(data['error'])
  return data['outputs']
 svg=Path(folder)/'logo.svg';svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="30" height="10"><rect width="30" height="10" fill="red"/></svg>')
 with Image.open(worker({'paths':[str(svg)],'target':'PNG','output':folder})[0]) as im:assert im.size==(30,10)
 heic=worker({'paths':[str(p)],'target':'HEIC','output':folder})[0]
 with Image.open(worker({'paths':[heic],'target':'PNG','output':folder})[0]) as im:assert im.size==(20,20)
 from pypdf import PdfWriter
 pdf=Path(folder)/'blank.pdf';w=PdfWriter();w.add_blank_page(100,100);w.write(pdf)
 from pypdf import PdfReader
 # AVIF encoder, A4 documents, pdfium page rendering, DOCX writer, text layout.
 with Image.open(worker({'paths':[str(p)],'target':'AVIF','output':folder})[0]) as im:assert im.size==(20,20)
 txt=Path(folder)/'note.txt';txt.write_text('hello world')
 page=PdfReader(worker({'paths':[str(txt)],'target':'Text → PDF','output':folder})[0]).pages[0];assert round(float(page.mediabox.width))==595 and round(float(page.mediabox.height))==842
 with Image.open(worker({'paths':[str(pdf)],'target':'PDF → PNG','output':folder})[0]) as im:assert im.size[0]>0
 import zipfile
 with zipfile.ZipFile(worker({'paths':[str(p)],'target':'Image → DOCX','output':folder})[0]) as z:assert b'w:w="11906"' in z.read('word/document.xml')
print('PASS: packaged GUI launch plus PNG, SVG, HEIC, AVIF, PDF-render and document worker jobs')

# Exercise the FFmpeg subprocess under the packaged worker's Linux resource limits.
import shutil
ff=shutil.which('ffmpeg')
if ff:
 with tempfile.TemporaryDirectory() as folder:
  clip=Path(folder)/'clip.mp4'
  subprocess.run([ff,'-nostdin','-v','error','-f','lavfi','-i','testsrc2=s=640x480:r=25','-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','3','-threads','1','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(clip)],check=True,timeout=30)
  result=subprocess.run([str(exe),'--worker'],input=json.dumps({'paths':[str(clip)],'target':'MP4','output':folder,'ffmpeg':str(Path(ff).resolve())}),text=True,capture_output=True,timeout=60)
  assert result.returncode==0,result.stdout+result.stderr
  data=json.loads(result.stdout);assert data['ok']
  subprocess.run([ff,'-nostdin','-v','error','-xerror','-threads','1','-i',data['outputs'][0],'-f','null','-'],check=True,timeout=30)
 print('PASS: packaged video conversion and full output decode')
