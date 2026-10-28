"""Build a folder-based portable package with licenses, exact source and hashes."""
import hashlib, importlib.metadata, json, os, shutil, subprocess, sys
from pathlib import Path
from engine import VERSION
r=Path(__file__).resolve().parent;os.chdir(r)
# The executable icon is generated from icon.png, so no binary .ico is kept in the repository.
from PIL import Image
build=r/'build';build.mkdir(exist_ok=True);ico=build/'icon.ico'
with Image.open(r/'icon.png') as im:im.save(ico,sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--windowed','--name','OpenTangerine','--icon',str(ico),'--add-data','icon.png:.','--collect-all','pypdf','--collect-all','pillow_heif','--collect-all','pypdfium2','--hidden-import','PySide6.QtSvg','--hidden-import','docops','app.py'],check=True)
dest=r/'dist/OpenTangerine';lic=dest/'licenses';lic.mkdir(exist_ok=True)
shutil.copyfile(r.parent/'LICENSE',lic/'Open-Tangerine-GPL-3.0.txt')
shutil.copyfile(r/'README.md',dest/'START-HERE.md')
shutil.copyfile(r.parent/'THIRD_PARTY_NOTICES.md',dest/'THIRD_PARTY_NOTICES.md')
shutil.copytree(r/'licenses',lic/'explicit',dirs_exist_ok=True)
# Ship the corresponding application source next to the portable executable.
src=dest/'source/Desktop';src.mkdir(parents=True,exist_ok=True)
shutil.copyfile(r.parent/'LICENSE',src.parent/'LICENSE')
shutil.copyfile(r.parent/'THIRD_PARTY_NOTICES.md',src.parent/'THIRD_PARTY_NOTICES.md')
shutil.copyfile(r/'README.md',src/'README.md')
shutil.copyfile(r/'RELEASE.md',src/'RELEASE.md')
shutil.copytree(r/'licenses',src/'licenses',dirs_exist_ok=True)
shutil.copytree(r/'tests',src/'tests',ignore=shutil.ignore_patterns('__pycache__'))
for p in r.glob('*.py'):shutil.copyfile(p,src/p.name)
shutil.copyfile(r/'requirements.txt',src/'requirements.txt');shutil.copyfile(r/'icon.png',src/'icon.png')
versions={}
for name in ['Pillow','pillow-heif','pypdf','pypdfium2','PySide6-Essentials','shiboken6','pyinstaller']:
 d=importlib.metadata.distribution(name);versions[name]=d.version
 for p in d.files or []:
  if 'license' in str(p).lower() or 'copying' in str(p).lower():
   file=Path(d.locate_file(p))
   if file.is_file():
    target=lic/name/str(p).replace('..','_');target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(file,target)
(dest/'dependencies.json').write_text(json.dumps(versions,indent=2))
platform='Windows-x64' if os.name=='nt' else 'Linux-x64'
base=r/'dist'/f'Open-Tangerine-{VERSION}-{platform}'
archive=shutil.make_archive(str(base),'zip' if os.name=='nt' else 'gztar',root_dir=r/'dist',base_dir='OpenTangerine')
p=Path(archive);p.with_name(p.name+'.sha256').write_text(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n')
print(archive)
