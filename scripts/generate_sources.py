"""Generate deterministic Dataverse solution and Power Automate source candidates.

These files are locally packable sources, not evidence of successful tenant import.
Stable component IDs must remain stable across upgrades. Customer scaffolds are copied
out of templates; this generator never visits those customer-owned directories.
"""
import json
import re
import uuid
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
VERSION = '0.1.0.0'
NS = uuid.UUID('46dd7edc-6813-42ae-884e-009b1b700db9')
def uid(name): return str(uuid.uuid5(NS, name))
def write_json(file, data):
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(data, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
def element(parent, tag, text=None, **attrs):
    node=ET.SubElement(parent,tag,attrs)
    if text is not None: node.text=str(text)
    return node
def write_xml(file, root):
    file.parent.mkdir(parents=True,exist_ok=True)
    ET.indent(root,space='  ')
    # Dataverse merges sharded source files as element nodes; an XML declaration
    # is not a valid child of the aggregate import document.
    ET.ElementTree(root).write(file,encoding='utf-8',xml_declaration=False)
def labels(parent, name, label):
    container=element(parent,name)
    element(container, {'LocalizedNames':'LocalizedName','LocalizedCollectionNames':'LocalizedCollectionName','Descriptions':'Description','displaynames':'displayname'}[name],description=label,languagecode='1033')

TABLES = {
 'WQCore': ['wqdefinition','wqqueuebinding','wqcontract','wqitemcontext','wqattempt','wqcommand','wqevent','wqcursor','wqintakefailure','wqprincipal'],
 'WQTesting':['wqtestcase','wqtestrun','wqtestresult'],
 'WQNotificationsEmail':[],
 'WQReferenceSharedMailbox':['emailrequest']
}
OPS = re.findall(r'\["([A-Za-z]+)"\]\s*=\s*"[a-z]+"', (ROOT/'src/runtime/Engine.cs').read_text())
# Acquisition handoff is intentionally generated ahead of the tenant bootstrap
# registration; the legacy AcquireNext surface remains for compatibility but
# production use is rejected until this handoff is bound and validated.
for _operation in ['PrepareAcquire', 'AcceptAcquire', 'ResolveAcquire']:
    if _operation not in OPS: OPS.append(_operation)
TEST_OPS={'StartTestRun','SeedRetentionFixture','CancelTestRun','GetTestRun','AdvanceTestRun','CleanupTestRun'}
PARAMS={'QueueKey':(10,False),'RequestId':(10,False),'ItemId':(10,True),'AttemptId':(10,True),'Generation':(7,True),'ExpectedVersion':(10,True),'DataJson':(10,True)}

def attribute(parent,name,kind='nvarchar',length=100,primary=False):
    a=element(parent,'attribute',PhysicalName=name)
    for key,val in {'Type':kind,'Name':name,'LogicalName':name,'RequiredLevel':'systemrequired' if kind=='primarykey' else 'required' if primary else 'none',
        'DisplayMask':('PrimaryName|' if primary else '')+'ValidForAdvancedFind|ValidForForm|ValidForGrid','ImeMode':'auto','ValidForUpdateApi':0 if kind=='primarykey' else 1,
        'ValidForReadApi':1,'ValidForCreateApi':1,'IsCustomField':0 if kind=='primarykey' else 1,'IsAuditEnabled':0,'IsSecured':0,
        'IntroducedVersion':VERSION,'IsCustomizable':1,'IsRenameable':1,'CanModifySearchSettings':1,'CanModifyRequirementLevelSettings':1,'CanModifyAdditionalSettings':1}.items(): element(a,key,val)
    if kind in ('nvarchar','ntext'): element(a,'Format','text' if kind=='nvarchar' else ''); element(a,'MaxLength',length)
    labels(a,'displaynames',name.removeprefix('qmcp_')); labels(a,'Descriptions','Framework '+name.removeprefix('qmcp_'))

def table_source(base, logical):
    name='qmcp_'+logical
    root=ET.Element('Entity'); element(root,'Name',name,LocalizedName=logical,OriginalName=logical)
    info=element(root,'EntityInfo'); entity=element(info,'entity',Name=name)
    labels(entity,'LocalizedNames',logical);labels(entity,'LocalizedCollectionNames',logical+' records');labels(entity,'Descriptions','Queue framework '+logical)
    attrs=element(entity,'attributes')
    attribute(attrs,name+'id','primarykey'); attribute(attrs,'qmcp_name',length=100,primary=True)
    attribute(attrs,'qmcp_key',length=100);attribute(attrs,'qmcp_queuekey',length=100);attribute(attrs,'qmcp_document','ntext',1048576)
    for column in ['qmcp_outcome','qmcp_itemid','qmcp_attemptid','qmcp_sourcekey','qmcp_testrun','qmcp_reviewrequired']:
        attribute(attrs,column,length=100)
    for key,val in {'EntitySetName':name+'s','OwnershipTypeMask':'OrgOwned' if logical=='wqprincipal' else 'UserOwned','IsActivity':0,'IsAuditEnabled':0,
        'IsCustomizable':1,'IsRenameable':1,'CanCreateAttributes':1,'CanCreateForms':1,'CanCreateViews':1,'CanCreateCharts':1,'IntroducedVersion':VERSION,
        'IsQuickCreateEnabled':0,'IsOfflineInMobileClient':0,'IsVisibleInMobileClient':0}.items():element(entity,key,val)
    keys=element(entity,'EntityKeys');key=element(keys,'EntityKey');element(key,'Name',name+'_identity');element(key,'LogicalName',name+'_identity')
    labels(key,'displaynames','Stable framework identity');element(key,'IsCustomizable',1);ka=element(key,'EntityKeyAttributes');element(ka,'AttributeName','qmcp_key')
    element(root,'RibbonDiffXml'); element(root,'FormXml');element(root,'SavedQueries')
    write_xml(base/'Entities'/name/'Entity.xml',root)
    # Views use scalar projections; the authoritative document remains versioned for engine serialization.
    view=ET.Element('savedqueries');sq=element(view,'savedquery')
    for field,value in {'IsCustomizable':1,'CanBeDeleted':1,'isquickfindquery':0,'isprivate':0,'IntroducedVersion':VERSION}.items():element(sq,field,value)
    element(sq,'savedqueryid','{'+uid(name+':view')+'}');element(sq,'querytype',0);element(sq,'isdefault',1)
    fx=element(sq,'fetchxml');fetch=element(fx,'fetch',version='1.0',mapping='logical');en=element(fetch,'entity',name=name)
    for field in [name+'id','qmcp_name','qmcp_queuekey','qmcp_outcome','qmcp_reviewrequired']:element(en,'attribute',name=field)
    element(en,'order',attribute='qmcp_name',descending='false')
    lx=element(sq,'layoutxml');grid=element(lx,'grid',name='resultset',jump='qmcp_name',select='1',icon='1',preview='1');row=element(grid,'row',name='result',id=name+'id')
    for field in ['qmcp_name','qmcp_queuekey','qmcp_outcome','qmcp_reviewrequired']:element(row,'cell',name=field,width='150')
    labels(sq,'LocalizedNames',logical+' overview')
    write_xml(base/'Entities'/name/'SavedQueries'/(uid(name+':view')+'.xml'),view)
    return name

def api_source(base,op):
    name='qmcp_WQ_'+op;root=ET.Element('customapi',uniquename=name)
    for key,val in {'allowedcustomprocessingsteptype':0,'bindingtype':0,'boundentitylogicalname':'','iscustomizable':0,'executeprivilegename':'prvReadqmcp_wqprincipal','isfunction':0,'isprivate':0,'name':name,'workflowsdkstepenabled':0}.items():element(root,key,val)
    for key in ['description','displayname']:
        node=element(root,key,default=op);element(node,'label',description=op,languagecode='1033')
    # First-build bootstrap resolves the actual registered package type. Never activate before binding.
    element(root,'plugintypeid')
    folder=base/'customapis'/name;write_xml(folder/'customapi.xml',root)
    for param,(kind,optional) in PARAMS.items():
        r=ET.Element('customapirequestparameter',uniquename=param)
        for key,val in {'iscustomizable':0,'isoptional':int(optional),'logicalentityname':'','name':name+'.'+param,'type':kind}.items():element(r,key,val)
        for key in ['description','displayname']:
            node=element(r,key,default=param);element(node,'label',description=param,languagecode='1033')
        write_xml(folder/'customapirequestparameters'/param/'customapirequestparameter.xml',r)
    r=ET.Element('customapiresponseproperty',uniquename='ResultJson')
    for key,val in {'iscustomizable':0,'logicalentityname':'','name':name+'.ResultJson','type':10}.items():element(r,key,val)
    for key in ['description','displayname']:
        node=element(r,key,default='ResultJson');element(node,'label',description='ResultJson',languagecode='1033')
    write_xml(folder/'customapiresponseproperties'/'ResultJson'/'customapiresponseproperty.xml',r)

def solutions():
    for package,tables in TABLES.items():
        base=ROOT/'solutions'/package/'src';other=base/'Other'
        sol=ET.Element('ImportExportXml',version='9.1.0.643',SolutionPackageVersion='9.1',languagecode='1033',generatedBy='CrmLive')
        m=element(sol,'SolutionManifest');element(m,'UniqueName',package);labels(m,'LocalizedNames',package);labels(m,'Descriptions','Local development candidate; tenant validation pending')
        element(m,'Version',VERSION);element(m,'Managed',2)
        pub=element(m,'Publisher');element(pub,'UniqueName','QueueFramework');labels(pub,'LocalizedNames','Queue Framework');labels(pub,'Descriptions','Independent queue framework')
        element(pub,'CustomizationPrefix','qmcp');element(pub,'CustomizationOptionValuePrefix',40147)
        roots=element(m,'RootComponents');element(m,'MissingDependencies')
        for table in tables:element(roots,'RootComponent',type='1',schemaName=table_source(base,table),behavior='0')
        operations=[op for op in OPS if (op in TEST_OPS)==(package=='WQTesting')] if package in ('WQCore','WQTesting') else []
        for op in operations:api_source(base,op)
        write_xml(other/'Solution.xml',sol)
        custom=ET.Element('ImportExportXml');
        sections=['Entities','Roles','Workflows','FieldSecurityProfiles','Templates','EntityMaps','EntityRelationships','OrganizationSettings','optionsets']
        if package=='WQCore':sections+=['WebResources']
        sections+=['CustomControls']
        if package=='WQCore':sections+=['AppModuleSiteMaps','AppModules']
        sections+=['connectionreferences']
        for section in sections:element(custom,section)
        write_xml(other/'Customizations.xml',custom);write_xml(other/'Relationships.xml',ET.Element('EntityRelationships'))
        project=ET.Element('Project',ToolsVersion='15.0',DefaultTargets='Build',xmlns='http://schemas.microsoft.com/developer/msbuild/2003')
        element(project,'Import',Project='$(MSBuildExtensionsPath)/$(MSBuildToolsVersion)/Microsoft.Common.props')
        pg=element(project,'PropertyGroup')
        for key,val in {'ProjectGuid':uid(package),'TargetFramework':'net462','TargetFrameworkVersion':'v4.6.2','RestoreProjectStyle':'PackageReference','SolutionRootPath':'src','SolutionPackageType':'Both'}.items():element(pg,key,val)
        ig=element(project,'ItemGroup');element(ig,'PackageReference',Include='Microsoft.PowerApps.MSBuild.Solution',Version='2.12.2');element(ig,'PackageReference',Include='Microsoft.NETFramework.ReferenceAssemblies',Version='1.0.3',PrivateAssets='All')
        element(project,'Import',Project='$(MSBuildToolsPath)/Microsoft.Common.targets')
        write_xml(base.parent/(package+'.cdsproj'),project)
    write_json(ROOT/'config/api-catalog.json',{'version':VERSION,'prefix':'qmcp_WQ_','parameters':{k:{'type':v[0],'optional':v[1]} for k,v in PARAMS.items()},'operations':OPS,'response':'ResultJson'})
    write_json(ROOT/'config/registration.json',{'version':VERSION,'pluginPackage':'QueueFramework.Plugins','runtimeType':'QueueFramework.Plugins.LifecyclePlugin',
        'guardType':'QueueFramework.Plugins.LifecycleGuard','isolation':'Sandbox','transactionRequired':True,
        'acquisitionHandoff':{'prepareApi':'qmcp_WQ_PrepareAcquire','acceptApi':'qmcp_WQ_AcceptAcquire','resolveApi':'qmcp_WQ_ResolveAcquire',
            'legacyApi':'qmcp_WQ_AcquireNext','legacyDisposition':'rejected: ACQUISITION_HANDOFF_REQUIRED',
            'flowSequence':['PrepareAcquire','native Dequeue(workqueue)','ResolveAcquire'],'sameRequestId':True,
            'nativeQueueId':'PrepareAcquire.ResultJson.NativeQueueId','businessGate':'ResolveAcquire.ResultJson.Outcome == Acquired'},
        'guardSteps':[{'table':'qmcp_'+table,'messages':['Create','Update','Delete'],'stage':20,'mode':0} for tables in TABLES.values() for table in tables if table not in ('wqprincipal','emailrequest')]+[{'table':'workqueueitem','messages':['Create','Update','Delete'],'stage':20,'mode':0}],
        'bootstrap':'Resolve actual plug-in type IDs from the imported dependent assembly package, then bind APIs and register guard steps before activating flows. Export the validated registration metadata after the first development import.'})

if __name__=='__main__':
    solutions()
    print('Generated four solution source trees and API/registration catalogs; live import unvalidated.')
