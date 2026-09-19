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
  assert.deepEqual(result.installOrder, ['WQCore','WQNotificationsEmail','WQReferenceSharedMailbox','WQTesting']);
  assert.equal(result.provenance.signedRelease, false);
});

test('release candidate publishes a versioned compatibility matrix and provenance boundary', async () => {
  const release = JSON.parse(await readFile(path.join(path.resolve(import.meta.dirname, '../../..'), 'config/release.json'), 'utf8'));
  assert.deepEqual(release.compatibility.runtime.targetFrameworks, ['net462', 'net8.0']);
  assert.equal(release.compatibility.apiCatalog.prefix, 'qmcp_WQ_');
  assert.equal(release.compatibility.mcp.sdk, '1.30.0');
  assert.equal(release.compatibility.templates.version, '0.1.0.0');
  assert.equal(release.compatibility.envelope.version, '1.0');
  assert.equal(release.compatibility.referenceContract.id, 'mail.v1');
  assert.equal(release.compatibility.upgradePolicy.path, 'config/upgrade-policy.json');
  assert.equal(release.compatibility.upgradePolicy.version, '1');
  assert.equal(release.provenance.tenantImport, 'not-run');
  assert.equal(release.productionReady, false);
});

test('installation plan validates dependency graph and binds order to hash', async () => {
  const manifest={version:'test',files:[{file:'A.zip',sha256:'0'.repeat(64)},{file:'A_managed.zip',sha256:'0'.repeat(64)},{file:'B.zip',sha256:'0'.repeat(64)},{file:'B_managed.zip',sha256:'0'.repeat(64)}]};
  const release={version:'test',packages:[{name:'A',requires:[]},{name:'B',requires:['A']}]};
  const first=await planInstallation({packageDir:path.join(os.tmpdir(),'qmcp-no-packages'),release,manifest});
  assert.deepEqual(first.installOrder,['A','B']);
  const badManifest={version:'test',files:manifest.files};
  const oneManifest={version:'test',files:manifest.files.slice(0,2)};
  await assert.rejects(planInstallation({release:{version:'test',packages:[{name:'A',requires:['Missing']}]},manifest:oneManifest}),/INSTALL_RELEASE_INVALID/);
  await assert.rejects(planInstallation({release:{version:'test',packages:[{name:'A',requires:'B'}]},manifest:oneManifest}),/INSTALL_RELEASE_INVALID/);
  await assert.rejects(planInstallation({release:{version:'test',packages:[{name:'A',requires:['A','A']}]},manifest:oneManifest}),/INSTALL_RELEASE_INVALID/);
  await assert.rejects(planInstallation({release:{version:'test',packages:[{name:'A',requires:['B']},{name:'B',requires:['A']}]},manifest:badManifest}),/INSTALL_RELEASE_INVALID/);
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
  await assert.rejects(planInstallation({manifest:{files:null},release:{version:'test',packages:[]}}),/INSTALL_RELEASE_INVALID/);
  await assert.rejects(planInstallation({manifest:{files:[null,{file:'WQCore_managed.zip',sha256:'0'.repeat(64)}]},release:{version:'test',packages:[{name:'WQCore'}]}}),/INSTALL_MANIFEST_INVALID/);
  await assert.rejects(planInstallation({manifest:{files:[{file:'WQCore.zip',sha256:'0'.repeat(64)},{file:'WQCore.zip',sha256:'0'.repeat(64)}]},release:{version:'test',packages:[{name:'WQCore'}]}}),/INSTALL_MANIFEST_INVALID/);
  const dir=await mkdtemp(path.join(os.tmpdir(),'qmcp-packages-')); await assert.rejects(planInstallation({packageDir:dir,manifest:{},release:{version:'test',packages:[]}}),/INSTALL_RELEASE_INVALID/);
  await assert.rejects(planInstallation({packageDir:dir,release:{version:'test',packages:[]}}),/INSTALL_RELEASE_INVALID/);
  await writeFile(path.join(dir,'manifest.json'),'null'); await assert.rejects(planInstallation({packageDir:dir}),/INSTALL_MANIFEST_INVALID/);
  const binding=path.join(dir,'binding.json'); await writeFile(binding,JSON.stringify({environmentUrl:'http://unsafe.example',organizationId:'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',environmentClass:'development',queueKeys:['mail']})); const result=await planInstallation({bindingPath:binding}); assert.equal(result.binding.error,'ENVIRONMENT_URL_INVALID');
  await writeFile(binding,'null'); const nullBinding=await planInstallation({bindingPath:binding}); assert.equal(nullBinding.binding.error,'ENVIRONMENT_URL_INVALID'); assert.equal(nullBinding.binding.environmentUrl,'');
});
