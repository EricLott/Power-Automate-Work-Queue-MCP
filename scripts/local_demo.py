"""Run a synthetic end-to-end example without network or credentials."""
import argparse,json,os,subprocess,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--state',default=str(ROOT/'artifacts/demo/state.json'));args=parser.parse_args()
state=Path(args.state).resolve();state.parent.mkdir(parents=True,exist_ok=True)
env={**os.environ,'QMCP_SIM_STATE':str(state)}
dll=ROOT/'src/simulator/bin/Release/net8.0/QueueFramework.Simulator.dll'
def command(operation,data=None,item=''):
    request={'Operation':operation,'QueueKey':'mail','RequestId':str(uuid.uuid4()),'ItemId':item,'DataJson':json.dumps(data or {})}
    process=subprocess.run(['dotnet',str(dll)],input=json.dumps(request)+'\n',text=True,capture_output=True,env=env,check=True)
    result=json.loads(process.stdout)
    if 'Error' in result:raise RuntimeError(result['Error'])
    return result
config=json.loads((ROOT/'config/reference.json').read_text())
if not state.exists():command('RegisterQueue',config['policy'])
command('RegisterContract',config['contract'])
input={'envelopeVersion':'1.0','contract':'mail.v1','correlationId':'demo','deduplicationKey':'demo','source':{'type':'synthetic'},'payload':{'subject':'Service request','senderAddress':'alex@example.com','bodyText':'Please provide service information.'}}
run=command('StartTestRun',{'cases':[{'Id':'valid-message','Input':input,'Expected':{'contact':'alex@example.com','category':'service'},'ExpectedAttemptCount':1,'Repetitions':3}]})
worker=subprocess.Popen(['dotnet',str(dll),'--worker','mail'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        evidence=command('GetTestRun',item=run['RunId'])
        if evidence['State']!='Running':break
        time.sleep(.2)
    else:raise RuntimeError('DEMO_TIMEOUT')
    output={'classification':'local-simulation-fixture','tenantConnected':False,'run':evidence}
    (state.parent/'evidence.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps({'state':evidence['State'],'runId':run['RunId'],'cases':len(evidence['Results']),'evidence':str(state.parent/'evidence.json'),'classification':output['classification']},indent=2))
    if evidence['State']!='Passed':raise SystemExit(1)
finally:
    worker.terminate();worker.wait(timeout=10)
