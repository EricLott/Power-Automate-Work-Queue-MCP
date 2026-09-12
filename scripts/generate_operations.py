"""Operations app, role, connection reference and package metadata sources."""
from generate_sources import ROOT, VERSION, TABLES, uid, write_xml, element, labels, ET

def generate():
    for package,tables in TABLES.items():
        base=ROOT/'solutions'/package/'src'
        custompath=base/'Other/Customizations.xml';custom=ET.parse(custompath);references=custom.find('connectionreferences')
        if references is None:references=element(custom.getroot(),'connectionreferences')
        references.clear()
        scope={'WQCore':'core','WQTesting':'testing','WQNotificationsEmail':'notifications','WQReferenceSharedMailbox':'reference'}[package]
        refs=['qmcp_'+scope+'_dataverse'] if scope!='reference' else ['qmcp_reference_intake_dataverse','qmcp_reference_worker_dataverse']
        if package in ['WQNotificationsEmail','WQReferenceSharedMailbox']:refs+=['qmcp_'+scope+'_outlook']
        if package=='WQReferenceSharedMailbox':refs+=['qmcp_reference_contentconversion']
        old_directory=base/'connectionreferences'
        if old_directory.exists():
            for old_file in old_directory.glob('*/connectionreference.xml'):old_file.unlink()
        for ref in refs:
            connector='shared_office365' if ref.endswith('outlook') else 'shared_conversionservice' if ref.endswith('contentconversion') else 'shared_commondataserviceforapps'
            node=ET.Element('connectionreference',connectionreferencelogicalname=ref)
            element(node,'connectionreferencedisplayname',ref);element(node,'connectorid','/providers/Microsoft.PowerApps/apis/'+connector);element(node,'iscustomizable',1)
            references.append(node)
        write_xml(custompath,custom.getroot())
        # An actor receives Dataverse privileges AND a trusted API profile; neither replaces queue-team ownership.
        for role in ['Worker','Reader']:
            name=package+' '+role;node=ET.Element('Role',id='{'+uid('role:'+name)+'}',name=name)
            element(node,'IsCustomizable',1)
            privileges=element(node,'RolePrivileges')
            for table in tables:
                actions=['Read'] if role=='Reader' or table=='wqprincipal' else ['Read','Create','Write','Append','AppendTo','Assign']
                for action in actions:element(privileges,'RolePrivilege',name='prv'+action+'qmcp_'+table,level='Global' if table=='wqprincipal' else 'Basic')
            if package=='WQCore':
                for table in ['workqueue','workqueueitem']:
                    for action in ['Read'] if role=='Reader' else ['Read','Create','Write','Append','AppendTo']:element(privileges,'RolePrivilege',name='prv'+action+table,level='Basic')
            old=base/'Roles'/('{'+uid('role:'+name)+'}.xml')
            if old.exists():old.unlink()
            write_xml(base/'Roles'/(name+'.xml'),node)
            solpath=base/'Other/Solution.xml';sol=ET.parse(solpath);roots=sol.find('./SolutionManifest/RootComponents')
            if not any(r.get('id')=='{'+uid('role:'+name)+'}' for r in roots):element(roots,'RootComponent',type='20',id='{'+uid('role:'+name)+'}',behavior='0')
            write_xml(solpath,sol.getroot())
        for key,value in {'qmcp_InstallValidated':'false','qmcp_EnvironmentClass':'production','qmcp_ReplayRetentionDays':'30'}.items():
            if package!='WQCore':continue
            env=ET.Element('environmentvariabledefinition',schemaname=key)
            for tag,val in {'defaultvalue':value,'type':100000000,'iscustomizable':1,'isrequired':1}.items():element(env,tag,val)
            for tag in ['displayname','description']:
                d=element(env,tag,default=key);element(d,'label',description=key,languagecode='1033')
            write_xml(base/'environmentvariabledefinitions'/key/'environmentvariabledefinition.xml',env)
    core=ROOT/'solutions/WQCore/src'
    solpath=core/'Other/Solution.xml';sol=ET.parse(solpath);roots=sol.find('./SolutionManifest/RootComponents')
    for kind in ['80','62']:
        if not any(r.get('type')==kind and r.get('schemaName')=='qmcp_Operations' for r in roots):element(roots,'RootComponent',type=kind,schemaName='qmcp_Operations',behavior='0')
    if not any(r.get('schemaName')=='qmcp_/icons/queue.svg' for r in roots):element(roots,'RootComponent',type='61',schemaName='qmcp_/icons/queue.svg',behavior='0')
    write_xml(solpath,sol.getroot())
    icon=core/'WebResources/qmcp_/icons/queue.svg';icon.parent.mkdir(parents=True,exist_ok=True);icon.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="6" fill="#145a7a"/><path d="M8 9h16M8 16h16M8 23h10" stroke="white" stroke-width="3"/></svg>')
    wr=ET.Element('WebResource')
    for tag,val in {'WebResourceId':'{'+uid('icon:queue')+'}','Name':'qmcp_/icons/queue.svg','DisplayName':'Queue framework','WebResourceType':11,'IntroducedVersion':VERSION,'IsCustomizable':1,'CanBeDeleted':1,'FileName':'/WebResources/qmcp_/icons/queue.svg'}.items():element(wr,tag,val)
    write_xml(icon.with_suffix('.svg.data.xml'),wr)
    for filename,kind in [('retry.html',1),('retry.js',3)]:
        file=core/'WebResources/qmcp_'/filename;file.write_bytes((ROOT/'src/operations'/filename).read_bytes())
        resource=ET.Element('WebResource')
        for tag,val in {'WebResourceId':'{'+uid('operations:'+filename)+'}','Name':'qmcp_/'+filename,'DisplayName':'Queue retry '+filename,'WebResourceType':kind,'IntroducedVersion':VERSION,'IsCustomizable':1,'CanBeDeleted':1,'FileName':'/WebResources/qmcp_/'+filename}.items():element(resource,tag,val)
        write_xml(file.with_suffix(file.suffix+'.data.xml'),resource)
        if not any(r.get('schemaName')=='qmcp_/'+filename for r in roots):element(roots,'RootComponent',type='61',schemaName='qmcp_/'+filename,behavior='0')
    write_xml(solpath,sol.getroot())
    app=ET.Element('AppModule')
    for tag,value in {'UniqueName':'qmcp_Operations','IntroducedVersion':VERSION,'WebResourceId':uid('icon:queue'),'FormFactor':1,'ClientType':4}.items():element(app,tag,value)
    components=element(app,'AppModuleComponents')
    for table in ['workqueue','workqueueitem']+['qmcp_'+t for t in TABLES['WQCore'] if t!='wqprincipal']:element(components,'AppModuleComponent',type='1',schemaName=table)
    element(components,'AppModuleComponent',type='62',schemaName='qmcp_Operations')
    roles=element(app,'AppModuleRoleMaps')
    for role in ['Worker','Reader']:element(roles,'Role',id='{'+uid('role:WQCore '+role)+'}')
    labels(app,'LocalizedNames','Queue Operations')
    write_xml(core/'AppModules/qmcp_Operations/AppModule.xml',app)
    sitemap=ET.Element('AppModuleSiteMap');element(sitemap,'SiteMapUniqueName','qmcp_Operations');element(sitemap,'SiteMapName','Queue Operations');sm=element(sitemap,'SiteMap');area=element(sm,'Area',Id='qmcp_work',ShowGroups='true');titles=element(area,'Titles');element(titles,'Title',LCID='1033',Title='Queue Operations')
    group=element(area,'Group',Id='qmcp_operations');titles=element(group,'Titles');element(titles,'Title',LCID='1033',Title='Runtime')
    for table in ['workqueueitem','qmcp_wqitemcontext','qmcp_wqattempt','qmcp_wqevent','qmcp_wqintakefailure','qmcp_wqdefinition']:
        element(group,'SubArea',Id=table,Entity=table)
    retry=element(group,'SubArea',Id='qmcp_retry',Url='$webresource:qmcp_/retry.html');titles=element(retry,'Titles');element(titles,'Title',LCID='1033',Title='Request retry')
    write_xml(core/'AppModuleSiteMaps/qmcp_Operations/AppModuleSiteMap.xml',sitemap)
    # NuGet dependency package is copied here by build.ps1 after compilation.
    package=ET.Element('pluginpackage',uniquename='qmcp_QueueFramework')
    for tag,val in {'exportkeyversion':1,'iscustomizable':1,'name':'qmcp_QueueFramework','statecode':0,'statuscode':1,'version':'0.1.0'}.items():element(package,tag,val)
    element(package,'package','qmcp_QueueFramework.nupkg',mimetype='application/octet-stream')
    write_xml(core/'pluginpackages/qmcp_QueueFramework/pluginpackage.xml',package)

if __name__=='__main__':generate();print('Generated role, app, connection and installation metadata.')
