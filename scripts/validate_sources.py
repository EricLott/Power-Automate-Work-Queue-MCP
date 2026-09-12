"""Offline structural and framework-invariant checks. Not a Dataverse import emulator."""
import json
import re
import zipfile
import hashlib
from pathlib import Path
from xml.etree import ElementTree as ET
from generate_sources import ROOT, TABLES, OPS, PARAMS, uid

FLOW_PACKAGES = {
    'ProcessOne': 'WQReferenceSharedMailbox',
    'OnQueueChanged': 'WQReferenceSharedMailbox',
    'SweepQueue': 'WQReferenceSharedMailbox',
    'Intake': 'WQReferenceSharedMailbox',
    'Watchdog': 'WQCore',
    'TestCoordinator': 'WQTesting',
    'EmailSender': 'WQNotificationsEmail',
}

def canonical_xml(data):
    """Canonicalize XML while accounting for PAC's known set ordering.

    PAC rewrites solution root components and app module components into a
    stable alphabetical order during unpack/repack.  These containers are
    sets in the solution schema; all other XML sibling order remains strict.
    """
    root = ET.fromstring(data.decode('utf-8-sig'))
    def normalize(node):
        for child in list(node):
            normalize(child)
        if node.tag in {'RootComponents', 'AppModuleComponents'}:
            children = list(node)
            children.sort(key=lambda c: (c.tag, tuple(sorted(c.attrib.items())),
                                         ''.join(c.itertext())))
            node[:] = children
    normalize(root)
    return ET.canonicalize(ET.tostring(root, encoding='unicode'), strip_text=True)

def package_connection_logicals(package):
    custom = ET.parse(ROOT/'solutions'/package/'src/Other/Customizations.xml').getroot()
    refs = custom.find('connectionreferences')
    return set() if refs is None else {
        node.get('connectionreferencelogicalname') for node in refs
    }

def walk_actions(actions):
    for name, action in actions.items():
        yield name,action
        yield from walk_actions(action.get('actions',{}))
        yield from walk_actions(action.get('else',{}).get('actions',{}))

def validate_flow(flow,name):
    assert isinstance(flow['properties'].get('templateName'),str), (name,'templateName must be a string')
    d=flow['properties']['definition'];actions=d['actions'];flat=list(walk_actions(actions))
    assert d['contentVersion']=='0.1.0.0'
    refs=flow['properties']['connectionReferences']
    package = FLOW_PACKAGES[name]
    package_refs = package_connection_logicals(package)
    for ref_name, ref in refs.items():
        logical = ref.get('connection', {}).get('connectionReferenceLogicalName')
        assert logical in package_refs, (name, ref_name, 'missing package connection reference', logical)
    def scope(items):
        for key,a in items.items():
            assert set(a.get('runAfter',{}))<=set(items), (name,key,'missing runAfter sibling')
            scope(a.get('actions',{}));scope(a.get('else',{}).get('actions',{}))
    scope(actions)
    for key,a in flat:
        if a['type']=='OpenApiConnection':
            host=a['inputs']['host'];params=a['inputs']['parameters']
            assert host['connectionReferenceName'] in refs,(name,key,'unbound connection')
            if host['operationId']=='PerformUnboundAction':
                operation=params['actionName'].removeprefix('qmcp_WQ_');assert operation in OPS
                assert params.get('item/RequestId','').startswith("@outputs('RequestIds')"),(name,key,'unstable request identity')
                assert 'item/QueueKey' in params
                if operation in ['Complete','Fail','Checkpoint']:
                    for field in ['ItemId','AttemptId','Generation']:assert "outputs('Acquired')" in params['item/'+field]
            if host['operationId'] in ['CreateRecord','UpdateRecord','DeleteRecord']:
                assert params.get('entityName')!='workqueueitems','Native lifecycle bypass'
        if a['type']=='Workflow':assert a['inputs']['host']['workflowReferenceName']==uid('flow:ProcessOne')
        if a['type']=='Until':assert a['limit']['count']<=20 and a['limit']['timeout']=='PT5M'
        if a['type']=='Foreach':assert a['runtimeConfiguration']['concurrency']['repetitions']==1
    if name=='ProcessOne':
        assert actions['AcquireNext']['runAfter']=={'RequestIds':['Succeeded']}
        assert actions['HasWork']['expression']=={'equals':["@outputs('Acquired')?['Outcome']",'Acquired']}
        assert actions['HasWork']['actions']['ReportFailure']['runAfter']=={'Business':['Failed','TimedOut']}
    if name=='OnQueueChanged':assert list(actions)==['ProcessOne'],'Event must be a wake-up only'
    return len(flat)

def validate():
    report={'classification':'offline-structure','tenantImport':'not-run','checks':[],'bindingGates':['plug-in API/guard registration','AI Builder prompt action','connection references','queue owner-team configuration']}
    for package,tables in TABLES.items():
        base=ROOT/'solutions'/package/'src'
        for xml in base.rglob('*.xml'):ET.parse(xml)
        for sitemap in (base/'AppModuleSiteMaps').glob('*/AppModuleSiteMap.xml'):
            assert ET.parse(sitemap).findtext('SiteMapName'), (str(sitemap),'missing SiteMapName')
        manifest=ET.parse(base/'Other/Solution.xml')
        assert manifest.findtext('./SolutionManifest/Publisher/CustomizationPrefix')=='qmcp'
        assert manifest.findtext('./SolutionManifest/Version')=='0.1.0.0'
        for logical in tables:
            entity=ET.parse(base/'Entities'/('qmcp_'+logical)/'Entity.xml')
            attrs=entity.findall('./EntityInfo/entity/attributes/attribute')
            names={a.findtext('LogicalName') for a in attrs}
            assert {'qmcp_key','qmcp_queuekey','qmcp_document'}<=names
            assert entity.findtext('./EntityInfo/entity/EntityKeys/EntityKey/EntityKeyAttributes/AttributeName')=='qmcp_key'
            for view in (base/'Entities'/('qmcp_'+logical)/'SavedQueries').glob('*.xml'):
                query=ET.parse(view).find('savedquery')
                for field in ('IsCustomizable','CanBeDeleted','isquickfindquery','isprivate'):
                    assert query.findtext(field) in ('0','1'), (str(view),field,'missing import metadata')
        for api in (base/'customapis').glob('*/customapi.xml') if (base/'customapis').exists() else []:
            doc=ET.parse(api);assert doc.findtext('isfunction')=='0'
            actual={p.parent.name for p in api.parent.glob('customapirequestparameters/*/*.xml')};assert actual==set(PARAMS)
            for prop in api.parent.glob('customapiresponseproperties/*/*.xml'):assert ET.parse(prop).find('isoptional') is None
        for metadata in (base/'Workflows').glob('*.data.xml'):
            workflow=ET.parse(metadata)
            assert workflow.findtext('StateCode')=='0','Unvalidated flow must stay draft'
            assert workflow.findtext('PrimaryEntity')=='none', (str(metadata),'missing PrimaryEntity')
            assert workflow.findtext('AsyncAutodelete')=='0', (str(metadata),'invalid AsyncAutodelete')
            assert workflow.find('./LocalizedNames/LocalizedName') is not None
        report['checks'].append({'package':package,'tables':len(tables),'xml':'parsed','publisher':'qmcp'})
    for file in (ROOT/'templates/flows').glob('*.json'):
        count=validate_flow(json.loads(file.read_text()),file.stem);report['checks'].append({'flow':file.stem,'actions':count,'invariants':'passed'})
    catalog=json.loads((ROOT/'config/api-catalog.json').read_text());assert set(catalog['operations'])==set(OPS)
    plugin=ROOT/'solutions/WQCore/src/pluginpackages/qmcp_QueueFramework/package/qmcp_QueueFramework.nupkg'
    for file in (ROOT/'artifacts/packages').glob('WQ*.zip'):
        with zipfile.ZipFile(file) as z:
            assert {'customizations.xml','solution.xml','[Content_Types].xml'}<=set(z.namelist())
            assert len(z.namelist())==len(set(z.namelist()))
            for entry in z.namelist():
                assert not entry.startswith('/') and '..' not in Path(entry).parts
                if entry.endswith('.xml'):ET.fromstring(z.read(entry))
            doc=ET.fromstring(z.read('customizations.xml'))
            assert len(doc.find('Entities'))==len(TABLES[file.stem.removesuffix('_managed')])
            if file.stem.startswith('WQCore'):
                assert 'pluginpackages/qmcp_QueueFramework/package/qmcp_QueueFramework.nupkg' in z.namelist()
                assert z.read('pluginpackages/qmcp_QueueFramework/package/qmcp_QueueFramework.nupkg') == plugin.read_bytes(), (file.name, 'embedded plugin package changed')
            roundtrip=json.loads((ROOT/'artifacts/validation/roundtrip.json').read_text(encoding='utf-8-sig'))['runId']
            assert re.fullmatch(r'[a-f0-9-]{36}',roundtrip), 'invalid roundtrip run ID'
            repacked=ROOT/'artifacts/repacked'/roundtrip/file.name
            assert repacked.exists(), (file.name,'repack missing for current build')
            if repacked.exists():
                with zipfile.ZipFile(repacked) as other:
                    assert set(z.namelist())==set(other.namelist()),(file.name,'roundtrip lost entries')
                    for entry in z.namelist():
                        before,after=z.read(entry),other.read(entry)
                        if entry.endswith('.json'):assert json.loads(before)==json.loads(after),(file.name,entry,'JSON changed')
                        elif entry.endswith('.xml'):
                            assert canonical_xml(before)==canonical_xml(after),(file.name,entry,'XML changed')
                        else:assert before==after,(file.name,entry,'binary changed')
            report['checks'].append({'archive':file.name,'entries':len(z.namelist()),'structure':'passed'})
    pack_output=ROOT/'artifacts/plugin-package/QueueFramework.Plugins.0.1.0.nupkg'
    if pack_output.exists():
        # The build copies this exact dotnet-pack output into the solution
        # source.  Preserve a byte-level check at that boundary.
        assert plugin.read_bytes()==pack_output.read_bytes(), 'plugin package differs from dotnet pack output'
    with zipfile.ZipFile(plugin) as archive:
        for assembly in ['QueueFramework.Plugins.dll','QueueFramework.Runtime.dll','Newtonsoft.Json.dll','System.ValueTuple.dll']:
            payload = archive.read('lib/net462/'+assembly)
            assert payload[:2] == b'MZ' and len(payload) > 1024, ('invalid packaged assembly', assembly)
            published=ROOT/'src/plugins/bin/Release/net462/publish'/assembly
            assert published.exists() and payload==published.read_bytes(), ('stale packaged assembly', assembly)
    output=ROOT/'artifacts/validation/structure.json';output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n')
    return report
if __name__=='__main__':print(json.dumps(validate(),indent=2))
