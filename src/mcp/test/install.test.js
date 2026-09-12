import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile, unlink } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import os from 'node:os';
import path from 'node:path';
import { planInstallation } from '../install.js';

test('installation plan reports local package state and missing binding', async () => {
  const result = await planInstallation();
  assert.equal(result.classification, 'local-installation-plan');
  assert.ok(result.packages.length > 0);
  assert.equal(result.binding.status, 'missing');
  assert.equal(result.liveVerification, 'not-run');
});

test('installation plan validates explicit development binding without contacting it', async () => {
  const dir = await mkdtemp(path.join(os.tmpdir(), 'qmcp-install-'));
  const binding = path.join(dir, 'binding.json');
  await writeFile(binding, JSON.stringify({ environmentUrl: 'https://synthetic.crm.dynamics.com', organizationId: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', environmentClass: 'development', queueKeys: ['mail'] }));
  const result = await planInstallation({ bindingPath: binding });
  assert.equal(result.binding.status, 'locally-validated');
  assert.equal(result.liveVerification, 'not-run');
});

test('installation plan reports tampered and missing pinned packages and binds hash to artifacts', async () => {
  const dir = await mkdtemp(path.join(os.tmpdir(), 'qmcp-packages-')); const names=['WQCore.zip','WQCore_managed.zip']; const files=[];
  for(const name of names){const data=Buffer.from(name+'-fixture');await writeFile(path.join(dir,name),data);files.push({file:name,sha256:createHash('sha256').update(data).digest('hex')});}
  const release={version:'test',packages:[{name:'WQCore'}]}; const manifest={version:'test',files};
  const before=await planInstallation({packageDir:dir,release,manifest});
  await writeFile(path.join(dir,names[0]),Buffer.from('changed-fixture')); await unlink(path.join(dir,names[1]));
  const result=await planInstallation({packageDir:dir,release,manifest});
  assert.equal(result.packages.find(p=>p.file===names[0]).status,'tampered'); assert.equal(result.packages.find(p=>p.file===names[1]).status,'missing');
  assert.notEqual(result.planHash,before.planHash);
});

test('installation plan rejects unsafe binding and malformed manifests', async () => {
  await assert.rejects(planInstallation({manifest:{files:[{file:'../escape.zip',sha256:'0'.repeat(64)}]},release:{version:'test',packages:[{name:'WQCore'}]}}),/INSTALL_MANIFEST_INVALID/);
  await assert.rejects(planInstallation({manifest:{files:null},release:{version:'test',packages:[]}}),/INSTALL_MANIFEST_INVALID/);
  await assert.rejects(planInstallation({manifest:{files:[null,{file:'WQCore_managed.zip',sha256:'0'.repeat(64)}]},release:{version:'test',packages:[{name:'WQCore'}]}}),/INSTALL_MANIFEST_INVALID/);
  await assert.rejects(planInstallation({manifest:{files:[{file:'WQCore.zip',sha256:'0'.repeat(64)},{file:'WQCore.zip',sha256:'0'.repeat(64)}]},release:{version:'test',packages:[{name:'WQCore'}]}}),/INSTALL_MANIFEST_INVALID/);
  const dir=await mkdtemp(path.join(os.tmpdir(),'qmcp-packages-')); await assert.rejects(planInstallation({packageDir:dir,manifest:{},release:{version:'test',packages:[]}}),/INSTALL_MANIFEST_INVALID/);
  await assert.rejects(planInstallation({packageDir:dir,release:{version:'test',packages:[]}}),/INSTALL_MANIFEST_INVALID/);
  await writeFile(path.join(dir,'manifest.json'),'null'); await assert.rejects(planInstallation({packageDir:dir}),/INSTALL_MANIFEST_INVALID/);
  const binding=path.join(dir,'binding.json'); await writeFile(binding,JSON.stringify({environmentUrl:'http://unsafe.example',organizationId:'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',environmentClass:'development',queueKeys:['mail']})); const result=await planInstallation({bindingPath:binding}); assert.equal(result.binding.error,'ENVIRONMENT_URL_INVALID');
  await writeFile(binding,'null'); const nullBinding=await planInstallation({bindingPath:binding}); assert.equal(nullBinding.binding.error,'ENVIRONMENT_URL_INVALID'); assert.equal(nullBinding.binding.environmentUrl,'');
});
