const assert=require('node:assert/strict');const {assetFor}=require('../docs/assets/desktop.js');
for(const platform of ['Windows','Linux']){
 const name='Open-Tangerine-0.2.0-'+platform+'-x64.'+(platform==='Windows'?'zip':'tar.gz');
 const asset={name,state:'uploaded',browser_download_url:'https://github.com/sintaxerrorpvtltd/Open-Tangerine/releases/download/desktop-v0.2.0/'+name};
 const release={tag_name:'desktop-v0.2.0',draft:false,prerelease:true,assets:[asset]};
 assert.equal(assetFor(release,platform),asset);assert.equal(assetFor({...release,draft:true},platform),null);assert.equal(assetFor({...release,tag_name:'v0.1.9'},platform),null);assert.equal(assetFor({...release,assets:[{...asset,browser_download_url:'https://evil.example/a'}]},platform),null);
}
assert.equal(assetFor(null,'Windows'),null);assert.equal(assetFor({},'ARM'),null);
console.log('PASS desktop release and exact download URL validation');
