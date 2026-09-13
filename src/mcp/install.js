import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { root } from './local.js';
const uuid=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
const digest=data=>createHash('sha256').update(data).digest('hex');
const stable=value=>Array.isArray(value)?`[${value.map(stable).join(',')}]`:value&&typeof value==='object'?`{${Object.keys(value).sort().map(k=>`${JSON.stringify(k)}:${stable(value[k])}`).join(',')}}`:JSON.stringify(value);
const expectedFiles=release=>new Set((release.packages||[]).flatMap(p=>[`${p.name}.zip`,`${p.name}_managed.zip`]));
function releasePlan(release){
  if(!release||!Array.isArray(release.packages)||!release.packages.length)throw new Error('INSTALL_RELEASE_INVALID');
  const names=release.packages.map(p=>p?.name);
  if(names.some(n=>typeof n!=='string'||!/^[A-Za-z][A-Za-z0-9]*$/.test(n))||new Set(names).size!==names.length)throw new Error('INSTALL_RELEASE_INVALID');
  const known=new Set(names), graph=new Map();
  for(const p of release.packages){
    if(p.requires !== undefined && !Array.isArray(p.requires))throw new Error('INSTALL_RELEASE_INVALID');
    const deps=p.requires===undefined?[]:p.requires;
    if(deps.some(d=>typeof d!=='string')||new Set(deps).size!==deps.length||deps.some(d=>!known.has(d)))throw new Error('INSTALL_RELEASE_INVALID');
    graph.set(p.name,[...deps].sort());
  }
  const state=new Map(), order=[];
  function visit(name){if(state.get(name)===1)throw new Error('INSTALL_RELEASE_INVALID');if(state.get(name)===2)return;state.set(name,1);for(const dep of graph.get(name))visit(dep);state.set(name,2);order.push(name);}
  for(const name of [...names].sort())visit(name);
  return {order,choices:order.map(name=>({name,unmanaged:`${name}.zip`,managed:`${name}_managed.zip`,selection:'unmanaged candidate; managed archive retained for descriptive comparison'}))};
}
function validateBinding(c){if(!c||typeof c!=='object')return'ENVIRONMENT_URL_INVALID';try{const u=new URL(c.environmentUrl);if(u.protocol!=='https:'||u.username||u.password||u.search||u.hash||!['','/'].includes(u.pathname))return'ENVIRONMENT_URL_INVALID';}catch{return'ENVIRONMENT_URL_INVALID';}if(!uuid.test(c.organizationId||'')||c.environmentClass!=='development')return'DEVELOPMENT_BINDING_REQUIRED';if(!Array.isArray(c.queueKeys)||!c.queueKeys.length||new Set(c.queueKeys).size!==c.queueKeys.length||c.queueKeys.some(k=>typeof k!=='string'||!/^[a-z][a-z0-9_-]{0,63}$/.test(k)))return'QUEUE_ALLOWLIST_REQUIRED';return'';}
// packageDir/manifest/release are internal test seams; the MCP tool never accepts them.
export async function planInstallation({bindingPath='',packageDir=path.join(root,'artifacts/packages'),manifest:givenManifest,release:givenRelease}={}){
  const release=givenRelease||JSON.parse(await readFile(path.join(root,'config/release.json'),'utf8'));const releasePlanData=releasePlan(release);let manifest=givenManifest;
  if(!manifest){try{manifest=JSON.parse(await readFile(path.join(packageDir,'manifest.json'),'utf8'));}catch{throw new Error('INSTALL_MANIFEST_INVALID');}}
  if(!manifest || typeof manifest!=='object' || Array.isArray(manifest))throw new Error('INSTALL_MANIFEST_INVALID');
  const expected=expectedFiles(release), entries=manifest.files;
  if(!Array.isArray(entries)||entries.length!==expected.size||entries.some(e=>!e)||new Set(entries.map(e=>e.file)).size!==entries.length||entries.some(e=>typeof e.file!=='string'||e.file.includes('/')||e.file.includes('\\')||!expected.has(e.file)||!/^[a-f0-9]{64}$/i.test(e.sha256)))throw new Error('INSTALL_MANIFEST_INVALID');
  const packages=[];for(const entry of entries){try{const actual=digest(await readFile(path.join(packageDir,entry.file)));packages.push({file:entry.file,expectedSha256:entry.sha256,actualSha256:actual,status:actual.toLowerCase()===entry.sha256.toLowerCase()?'verified-local':'tampered'});}catch(error){if(error.code!=='ENOENT')throw error;packages.push({file:entry.file,expectedSha256:entry.sha256,actualSha256:null,status:'missing'});}}
  let binding={provided:false,status:'missing',liveVerification:'not-run'};if(bindingPath){const c=JSON.parse(await readFile(bindingPath,'utf8')),error=validateBinding(c);binding={provided:true,status:error?'invalid':'locally-validated',error:error||null,environmentUrl:error?'':c.environmentUrl||'',organizationId:error?'':c.organizationId||'',queueKeys:error?[]:c.queueKeys||[],liveVerification:'not-run'};}
  const planHash=digest(stable({release,manifest,binding,packages,installOrder:releasePlanData.order,packageChoices:releasePlanData.choices})),complete=packages.every(p=>p.status==='verified-local');return{classification:'local-installation-plan',releaseVersion:release.version,packages,installOrder:releasePlanData.order,packageChoices:releasePlanData.choices,provenance:{source:'repository-pinned-release-candidate',signedRelease:false},localArtifacts:complete?'verified':'blocked',binding,liveVerification:'not-run',planHash,prerequisites:['Confirm package compatibility and connection references in the target tenant.','Verify solution imports, API bindings, roles, queue ownership, and flow activation in a development environment.','Run tenant smoke tests before any production promotion.']};
}
