"""Verify release bytes and required notices/source inside the actual archive."""
import hashlib, json, os, tarfile, zipfile
from pathlib import Path
from engine import VERSION
root=Path(__file__).resolve().parent
platform='Windows-x64.zip' if os.name=='nt' else 'Linux-x64.tar.gz'
p=root/'dist'/f'Open-Tangerine-{VERSION}-{platform}'
assert p.with_name(p.name+'.sha256').read_text().split()[0]==hashlib.sha256(p.read_bytes()).hexdigest()
if os.name=='nt':
    with zipfile.ZipFile(p) as archive:names=archive.namelist()
else:
    with tarfile.open(p) as archive:names=archive.getnames()
for name in ['licenses/explicit/LGPL-3.0-only.txt','licenses/explicit/Python-3.12-LICENSE.txt','licenses/Open-Tangerine-GPL-3.0.txt','THIRD_PARTY_NOTICES.md','source/THIRD_PARTY_NOTICES.md','source/Desktop/engine.py','source/Desktop/licenses/LGPL-3.0-only.txt']:
    assert 'OpenTangerine/'+name in names,name
print('PASS: archive checksum, explicit notices and rebuildable source')
