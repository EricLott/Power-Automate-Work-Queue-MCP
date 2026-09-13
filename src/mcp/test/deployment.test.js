import test from 'node:test';import assert from 'node:assert/strict';import {mkdtemp,writeFile,rm,mkdir} from 'node:fs/promises';import os from 'node:os';import path from 'node:path';import {applyDeployment,deploymentStatus} from '../deployment.js';
const b={environmentUrl:'https://synthetic.crm.dynamics.com',organizationId:'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',environmentClass:'development',queueKeys:['mail']};
const roots=[];test.afterEach(async()=>{for(const root of roots.splice(0))await rm(root,{recursive:true,force:true});});
test('approval mismatch fails before launch',async()=>{const root=await mkdtemp(path.join(os.tmpdir(),'dep-'));roots.push(root);const bp=path.join(root,'b.json'),sp=path.join(root,'s.json');await writeFile(bp,JSON.stringify(b));await writeFile(sp,'{}');await assert.rejects(applyDeployment({planHash:'0'.repeat(64),requestId:'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'},{root,env:{QMCP_ENVIRONMENT_BINDING:bp,QMCP_DEPLOYMENT_SETTINGS:sp,QMCP_APPROVED_DEPLOYMENT_PLAN:'1'.repeat(64)},launch:()=>{throw Error('spawn')}}),/PLAN_APPROVAL_MISMATCH/);});
test('launch is journaled and replay does not respawn',async()=>{const root=await mkdtemp(path.join(os.tmpdir(),'dep-'));roots.push(root);const bp=path.join(root,'b.json'),sp=path.join(root,'s.json');await writeFile(bp,JSON.stringify(b));await writeFile(sp,'{}');const env={QMCP_ENVIRONMENT_BINDING:bp,QMCP_DEPLOYMENT_SETTINGS:sp,QMCP_APPROVED_DEPLOYMENT_PLAN:'1'.repeat(64)},calls=[];const args={planHash:env.QMCP_APPROVED_DEPLOYMENT_PLAN,requestId:'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'};const first=await applyDeployment(args,{root,env,launch:a=>calls.push(a)});const second=await applyDeployment(args,{root,env,launch:()=>{throw Error('respawn')}});assert.equal(calls.length,1);assert.deepEqual(first,second);const status=await deploymentStatus(args,{root,env});assert.equal(status.liveState,'unknown');});
test('invalid UUID and unsafe binding fail closed',async()=>{const root=await mkdtemp(path.join(os.tmpdir(),'dep-'));roots.push(root);const bp=path.join(root,'b.json'),sp=path.join(root,'s.json');await writeFile(bp,JSON.stringify({...b,environmentUrl:'http://user:pass@unsafe'}));await writeFile(sp,'{}');const env={QMCP_ENVIRONMENT_BINDING:bp,QMCP_DEPLOYMENT_SETTINGS:sp,QMCP_APPROVED_DEPLOYMENT_PLAN:'1'.repeat(64)};await assert.rejects(applyDeployment({planHash:env.QMCP_APPROVED_DEPLOYMENT_PLAN,requestId:'bad'},{root,env,launch:()=>{throw Error('spawn')}}),/REQUEST_ID_INVALID/);await assert.rejects(applyDeployment({planHash:env.QMCP_APPROVED_DEPLOYMENT_PLAN,requestId:'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'},{root,env,launch:()=>{throw Error('spawn')}}),/ENVIRONMENT_URL_INVALID/);});
test('same request rejects changed binding or settings',async()=>{const root=await mkdtemp(path.join(os.tmpdir(),'dep-'));roots.push(root);const bp=path.join(root,'b.json'),bp2=path.join(root,'b2.json'),sp=path.join(root,'s.json'),sp2=path.join(root,'s2.json');await writeFile(bp,JSON.stringify(b));await writeFile(bp2,JSON.stringify({...b,organizationId:'cccccccc-cccc-cccc-cccc-cccccccccccc'}));await writeFile(sp,'{}');await writeFile(sp2,'{"changed":true}');const env={QMCP_ENVIRONMENT_BINDING:bp,QMCP_DEPLOYMENT_SETTINGS:sp,QMCP_APPROVED_DEPLOYMENT_PLAN:'1'.repeat(64)},args={planHash:env.QMCP_APPROVED_DEPLOYMENT_PLAN,requestId:'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'};await applyDeployment(args,{root,env,launch:()=>{}});await assert.rejects(applyDeployment(args,{root,env:{...env,QMCP_ENVIRONMENT_BINDING:bp2},launch:()=>{}}),/REQUEST_CONFLICT/);await assert.rejects(applyDeployment(args,{root,env:{...env,QMCP_DEPLOYMENT_SETTINGS:sp2},launch:()=>{}}),/REQUEST_CONFLICT/);});
test('launch failure is returned safely',async()=>{const root=await mkdtemp(path.join(os.tmpdir(),'dep-'));roots.push(root);const bp=path.join(root,'b.json'),sp=path.join(root,'s.json');await writeFile(bp,JSON.stringify(b));await writeFile(sp,'{}');const env={QMCP_ENVIRONMENT_BINDING:bp,QMCP_DEPLOYMENT_SETTINGS:sp,QMCP_APPROVED_DEPLOYMENT_PLAN:'1'.repeat(64)};const result=await applyDeployment({planHash:env.QMCP_APPROVED_DEPLOYMENT_PLAN,requestId:'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'},{root,env,launch:()=>{throw Error('raw secret')}});assert.equal(result.status,'LaunchFailed');assert.notEqual(result.error,'raw secret');});

test('CLI journal is readable without launch record and rejects a different organization', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'dep-')); roots.push(root);
  const bp = path.join(root, 'binding.json'); await writeFile(bp, JSON.stringify(b));
  const env = { QMCP_ENVIRONMENT_BINDING: bp };
  const requestId = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
  const dir = path.join(root, 'artifacts/deployments'); await mkdir(dir, { recursive: true });
  const file = path.join(dir, requestId + '.json');
  const journal = { requestId, organizationId: b.organizationId, environmentUrl: b.environmentUrl, planHash: '1'.repeat(64), status: 'Running' };
  await writeFile(file, JSON.stringify(journal));
  const status = await deploymentStatus({ requestId }, { root, env });
  assert.equal(status.status, 'Running'); assert.equal(status.liveState, 'unknown');
  await writeFile(file, JSON.stringify({ ...journal, organizationId: 'cccccccc-cccc-cccc-cccc-cccccccccccc' }));
  await assert.rejects(deploymentStatus({ requestId }, { root, env }), /DEPLOYMENT_RECORD_MISMATCH/);
});

test('apply rejects a CLI journal whose request ID differs from its filename', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'dep-')); roots.push(root);
  const bp = path.join(root, 'binding.json'), sp = path.join(root, 'settings.json');
  await writeFile(bp, JSON.stringify(b)); await writeFile(sp, '{}');
  const requestId = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
  const env = { QMCP_ENVIRONMENT_BINDING: bp, QMCP_DEPLOYMENT_SETTINGS: sp, QMCP_APPROVED_DEPLOYMENT_PLAN: '1'.repeat(64) };
  const dir = path.join(root, 'artifacts/deployments'); await mkdir(dir, { recursive: true });
  await writeFile(path.join(dir, requestId + '.json'), JSON.stringify({
    requestId: 'cccccccc-cccc-cccc-cccc-cccccccccccc', organizationId: b.organizationId,
    environmentUrl: b.environmentUrl, planHash: env.QMCP_APPROVED_DEPLOYMENT_PLAN, status: 'Running'
  }));
  await assert.rejects(applyDeployment({ planHash: env.QMCP_APPROVED_DEPLOYMENT_PLAN, requestId }, { root, env, launch: () => { throw Error('respawn'); } }), /REQUEST_CONFLICT/);
});

test('apply rejects a launch journal whose request ID differs from its filename', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'dep-')); roots.push(root);
  const bp = path.join(root, 'binding.json'), sp = path.join(root, 'settings.json');
  await writeFile(bp, JSON.stringify(b)); await writeFile(sp, '{}');
  const requestId = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
  const env = { QMCP_ENVIRONMENT_BINDING: bp, QMCP_DEPLOYMENT_SETTINGS: sp, QMCP_APPROVED_DEPLOYMENT_PLAN: '1'.repeat(64) };
  const dir = path.join(root, 'artifacts/deployments'); await mkdir(dir, { recursive: true });
  await writeFile(path.join(dir, requestId + '.launch.json'), JSON.stringify({
    requestId: 'cccccccc-cccc-cccc-cccc-cccccccccccc', organizationId: b.organizationId,
    environmentUrl: b.environmentUrl, planHash: env.QMCP_APPROVED_DEPLOYMENT_PLAN,
    settingsPath: path.resolve(sp), bindingPath: path.resolve(bp), status: 'AwaitingJournal'
  }));
  await assert.rejects(applyDeployment({ planHash: env.QMCP_APPROVED_DEPLOYMENT_PLAN, requestId }, { root, env, launch: () => { throw Error('respawn'); } }), /REQUEST_CONFLICT/);
});

test('status rejects launch and CLI journals whose request ID differs from filename', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'dep-')); roots.push(root);
  const bp = path.join(root, 'binding.json'); await writeFile(bp, JSON.stringify(b));
  const env = { QMCP_ENVIRONMENT_BINDING: bp };
  const requestId = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
  const dir = path.join(root, 'artifacts/deployments'); await mkdir(dir, { recursive: true });
  await writeFile(path.join(dir, requestId + '.launch.json'), JSON.stringify({
    requestId: 'cccccccc-cccc-cccc-cccc-cccccccccccc', organizationId: b.organizationId,
    environmentUrl: b.environmentUrl, planHash: '1'.repeat(64), status: 'AwaitingJournal'
  }));
  await assert.rejects(deploymentStatus({ requestId }, { root, env }), /DEPLOYMENT_RECORD_MISMATCH/);
  await rm(path.join(dir, requestId + '.launch.json'));
  await writeFile(path.join(dir, requestId + '.json'), JSON.stringify({
    requestId: 'cccccccc-cccc-cccc-cccc-cccccccccccc', organizationId: b.organizationId,
    environmentUrl: b.environmentUrl, planHash: '1'.repeat(64), status: 'Running'
  }));
  await assert.rejects(deploymentStatus({ requestId }, { root, env }), /DEPLOYMENT_RECORD_MISMATCH/);
});
