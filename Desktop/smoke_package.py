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
print('PASS: packaged GUI launch and actual PNG to JPEG worker conversion')
