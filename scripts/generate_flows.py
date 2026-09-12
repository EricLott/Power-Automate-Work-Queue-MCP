"""Power Automate workflow sources with bounded loops and explicit lifecycle ownership.

The prompt action is a binding seam: the first tenant export supplies its environment-
specific AI Builder action metadata. The default action fails closed. Local simulation
uses a labeled fixture provider, never a pretend live prompt.
"""
from generate_sources import ROOT, VERSION, uid, write_json, write_xml, element, ET

API='/providers/Microsoft.PowerApps/apis/shared_commondataserviceforapps'
def connector(operation,parameters,after=None,connection='qmcp_Dataverse',api=API):
    return {'type':'OpenApiConnection','inputs':{'host':{'apiId':api,'connectionReferenceName':connection,'operationId':operation},'parameters':parameters,'retryPolicy':{'type':'none'}},'runAfter':{} if after is None else {after:['Succeeded']}}
def action(op,data='{}',after=None,owned=False):
    p={'actionName':'qmcp_WQ_'+op,'item/QueueKey':"@parameters('qmcp_QueueKey')",'item/RequestId':"@outputs('RequestIds')?['"+op+"']",'item/DataJson':data}
    if owned:
        for name in ['ItemId','AttemptId','Generation']:p['item/'+name]="@outputs('Acquired')?['"+name+"']"
    return connector('PerformUnboundAction',p,after)
def compose(value,after=None):return {'type':'Compose','inputs':value,'runAfter':{} if after is None else {after:['Succeeded']}}
def request_ids(ops):return compose({op:'@guid()' for op in ops})
def workflow(name,trigger,actions,connections=('qmcp_Dataverse',)):
    refs={}
    scope='core' if name=='Watchdog' else 'testing' if name=='TestCoordinator' else 'notifications' if name=='EmailSender' else 'reference'
    for ref in connections:
        apiname='shared_office365' if ref=='qmcp_Outlook' else 'shared_conversionservice' if ref=='qmcp_ContentConversion' else 'shared_commondataserviceforapps'
        logical='qmcp_'+scope+'_'+ref.removeprefix('qmcp_').lower()
        if scope=='reference' and ref=='qmcp_Dataverse':logical='qmcp_reference_'+('intake' if name=='Intake' else 'worker')+'_dataverse'
        refs[ref]={'runtimeSource':'embedded','connection':{'connectionReferenceLogicalName':logical},'api':{'name':apiname}}
    return {'properties':{'connectionReferences':refs,'definition':{'$schema':'https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#','contentVersion':VERSION,'parameters':{'$connections':{'defaultValue':{},'type':'Object'},'$authentication':{'defaultValue':{},'type':'SecureObject'},'qmcp_QueueKey':{'defaultValue':'mail','type':'String'},'qmcp_NativeQueueId':{'defaultValue':'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa','type':'String'},'qmcp_Mailbox':{'defaultValue':'synthetic@example.invalid','type':'String'},'qmcp_NotificationAddress':{'defaultValue':'operations@example.invalid','type':'String'}},'triggers':{'manual' if trigger['type']=='Request' else 'trigger':trigger},'actions':actions,'outputs':{}},'templateName':None},'schemaVersion':'1.0.0.0'}
def recurrence():return {'type':'Recurrence','recurrence':{'frequency':'Minute','interval':1},'runtimeConfiguration':{'concurrency':{'runs':1}}}
def child():return {'type':'Request','kind':'Button','inputs':{'schema':{'type':'object','properties':{}}}}
def call_child(after=None):return {'type':'Workflow','inputs':{'host':{'workflowReferenceName':uid('flow:ProcessOne')},'body':{}},'runAfter':{} if after is None else {after:['Succeeded']}}
def save(name,package,data):
    write_json(ROOT/'templates/flows'/(name+'.json'),data)
    folder=ROOT/'solutions'/package/'src/Workflows';file=name+'-'+uid('flow:'+name)
    write_json(folder/(file+'.json'),data)
    root=ET.Element('Workflow',WorkflowId='{'+uid('flow:'+name)+'}',Name=name)
    element(root,'JsonFileName','/Workflows/'+file+'.json')
    for tag,value in {'Type':1,'Subprocess':0,'Category':5,'Mode':0,'Scope':4,'OnDemand':0,'TriggerOnCreate':0,'TriggerOnDelete':0,'AsyncAutoDelete':0,'StateCode':0,'StatusCode':1,'RunAs':1,'IsTransacted':1,'IntroducedVersion':VERSION,'IsCustomizable':1,'BusinessProcessType':0,'IsCustomProcessingStepAllowedForOtherPublishers':1,'ModernFlowType':0}.items():element(root,tag,value)
    write_xml(folder/(file+'.json.data.xml'),root)
    # Root workflow components are referenced by deterministic IDs.
    solpath=ROOT/'solutions'/package/'src/Other/Solution.xml';sol=ET.parse(solpath);roots=sol.find('./SolutionManifest/RootComponents')
    if not any(r.get('id')=='{'+uid('flow:'+name)+'}' for r in roots):element(roots,'RootComponent',type='29',id='{'+uid('flow:'+name)+'}',behavior='0')
    write_xml(solpath,sol.getroot())

def generate():
    acquired="@json(body('AcquireNext')?['ResultJson'])"
    record_doc={'sourceKey':"@outputs('Acquired')?['SourceKey']",'contentHash':"@outputs('Acquired')?['ContentHash']",'testRun':"@outputs('Acquired')?['TestRun']",'fields':"@body('ValidateExtraction')",'promptVersion':'mail-extraction-v1'}
    prompt={'type':'Terminate','inputs':{'runStatus':'Failed','runError':{'code':'PROMPT_BINDING_REQUIRED','message':'Bind the approved AI Builder prompt action before activation.'}},'runAfter':{},'metadata':{'qmcpBinding':'approved-prompt-action'}}
    output_schema={'type':'object','additionalProperties':False,'required':['contact','category','summary'],'properties':{'contact':{'type':'string','minLength':1,'maxLength':320},'category':{'type':'string','enum':['service','question']},'summary':{'type':'string','maxLength':4000}}}
    make={'Prompt':prompt,'ValidateExtraction':{'type':'ParseJson','inputs':{'content':"@outputs('Prompt')?['body']",'schema':output_schema},'runAfter':{'Prompt':['Succeeded']}},'BusinessDocument':compose(record_doc,'ValidateExtraction'),
          'CreateRecord':connector('CreateRecord',{'entityName':'qmcp_emailrequests','item/qmcp_name':"@outputs('Acquired')?['BusinessKey']",'item/qmcp_key':"@outputs('Acquired')?['BusinessKey']",'item/qmcp_queuekey':"@parameters('qmcp_QueueKey')",'item/qmcp_document':"@string(outputs('BusinessDocument'))"},'BusinessDocument')}
    # Reconciliation reads by the protected source identity before any prompt or write.
    business={'FindExisting':connector('ListRecords',{'entityName':'qmcp_emailrequests','$filter':"@concat('qmcp_key eq ''', outputs('Acquired')?['BusinessKey'], '''')",'$top':2}),
      'CreateIfAbsent':{'type':'If','expression':{'equals':["@length(body('FindExisting')?['value'])",0]},'actions':make,'else':{'actions':{}},'runAfter':{'FindExisting':['Succeeded']}},
      'FindResult':connector('ListRecords',{'entityName':'qmcp_emailrequests','$filter':"@concat('qmcp_key eq ''', outputs('Acquired')?['BusinessKey'], '''')",'$top':2},'CreateIfAbsent'),
      'Reconciled':{'type':'If','expression':{'and':[{'equals':["@length(body('FindResult')?['value'])",1]},{'equals':["@json(first(body('FindResult')?['value'])?['qmcp_document'])?['contentHash']","@outputs('Acquired')?['ContentHash']"]}]},'actions':{'Complete':action('Complete',"@string(setProperty(setProperty(json('{}'), 'table', 'qmcp_emailrequest'), 'recordId', first(body('FindResult')?['value'])?['qmcp_emailrequestid']))",owned=True)},'else':{'actions':{'Conflict':{'type':'Terminate','inputs':{'runStatus':'Failed','runError':{'code':'BUSINESS_CONTENT_CONFLICT','message':'Existing source identity failed reconciliation.'}},'runAfter':{}}}},'runAfter':{'FindResult':['Succeeded']}}}
    a={'RequestIds':request_ids(['AcquireNext','Complete','Fail']),'AcquireNext':action('AcquireNext',"@string(setProperty(setProperty(json('{}'), 'runId', workflow()?['run']?['name']), 'templateVersion', '0.1.0.0'))",'RequestIds'),'Acquired':compose(acquired,'AcquireNext'),
       'HasWork':{'type':'If','expression':{'equals':["@outputs('Acquired')?['Outcome']",'Acquired']},'actions':{'Business':{'type':'Scope','actions':business,'runAfter':{}},'ReportFailure':action('Fail','{"category":"Unknown","code":"WORKER_SCOPE_FAILED","effect":"Unknown"}',owned=True)},'else':{'actions':{}},'runAfter':{'Acquired':['Succeeded']}}}
    a['HasWork']['actions']['ReportFailure']['runAfter']={'Business':['Failed','TimedOut']}
    a['Respond']={'type':'Response','kind':'PowerApp','inputs':{'statusCode':200,'body':{'outcome':"@outputs('Acquired')?['Outcome']"}},'runAfter':{'HasWork':['Succeeded']}}
    save('ProcessOne','WQReferenceSharedMailbox',workflow('ProcessOne',child(),a))
    trigger={'type':'OpenApiConnectionNotification','inputs':{'host':{'apiId':API,'connectionReferenceName':'qmcp_Dataverse','operationId':'SubscribeWebhookTrigger'},'parameters':{'subscriptionRequest/message':4,'subscriptionRequest/entityname':'workqueueitem','subscriptionRequest/scope':4,'subscriptionRequest/filterexpression':"@concat('_workqueueid_value eq ', parameters('qmcp_NativeQueueId'), ' and statecode eq 0')"}},'runtimeConfiguration':{'concurrency':{'runs':1}}}
    save('OnQueueChanged','WQReferenceSharedMailbox',workflow('OnQueueChanged',trigger,{'ProcessOne':call_child()}))
    sweep={'BoundedSweep':{'type':'Foreach','foreach':'@range(0,10)','runtimeConfiguration':{'concurrency':{'repetitions':1}},'actions':{'ProcessOne':call_child()},'runAfter':{}}}
    save('SweepQueue','WQReferenceSharedMailbox',workflow('SweepQueue',recurrence(),sweep))
    outlook='/providers/Microsoft.PowerApps/apis/shared_office365'
    trigger={'type':'OpenApiConnection','inputs':{'host':{'apiId':outlook,'connectionReferenceName':'qmcp_Outlook','operationId':'SharedMailboxOnNewEmailV2'},'parameters':{'mailboxAddress':"@parameters('qmcp_Mailbox')",'folderId':'Inbox','includeAttachments':False,'importance':'Any','hasAttachments':False}},'recurrence':{'frequency':'Minute','interval':1},'splitOn':"@triggerOutputs()?['body/value']"}
    envelope={'envelopeVersion':'1.0','contract':'mail.v1','correlationId':"@workflow()?['run']?['name']",'deduplicationKey':"@triggerOutputs()?['body/id']",'source':{'type':'shared-mailbox','mailbox':"@parameters('qmcp_Mailbox')"},'payload':{'subject':"@coalesce(triggerOutputs()?['body/subject'],'')",'senderAddress':"@triggerOutputs()?['body/from']",'bodyText':"@body('HtmlToText')"}}
    normalize=connector('HtmlToText',{'Content':"@triggerOutputs()?['body/body']"},connection='qmcp_ContentConversion',api='/providers/Microsoft.PowerApps/apis/shared_conversionservice')
    a={'RequestIds':request_ids(['Enqueue','ReportIntakeFailure']),'Intake':{'type':'Scope','actions':{'HtmlToText':normalize,'Envelope':compose(envelope,'HtmlToText'),'Enqueue':action('Enqueue',"@string(outputs('Envelope'))",'Envelope')},'runAfter':{'RequestIds':['Succeeded']}},'ReportIntakeFailure':action('ReportIntakeFailure',"@string(setProperty(setProperty(setProperty(json('{}'),'source',coalesce(triggerOutputs()?['body/id'],'unknown')),'correlationId',workflow()?['run']?['name']),'code','INTAKE_FAILED'))")}
    a['ReportIntakeFailure']['runAfter']={'Intake':['Failed','TimedOut']}
    a['Intake']['actions']['ValidateEnqueueResult']={'type':'ParseJson','inputs':{'content':"@json(body('Enqueue')?['ResultJson'])",'schema':{'type':'object','required':['Outcome','ItemId'],'properties':{'Outcome':{'type':'string','enum':['Enqueued','Existing']},'ItemId':{'type':'string'}}}},'runAfter':{'Enqueue':['Succeeded']}}
    save('Intake','WQReferenceSharedMailbox',workflow('Intake',trigger,a,('qmcp_Dataverse','qmcp_Outlook','qmcp_ContentConversion')))
    # Maintenance advances its cursor through bounded pages; one scheduling run cannot monopolize capacity.
    a={'Cursor':{'type':'InitializeVariable','inputs':{'variables':[{'name':'cursor','type':'string','value':''}]},'runAfter':{}},'Sweep':{'type':'Until','expression':"@empty(variables('cursor'))",'limit':{'count':20,'timeout':'PT5M'},'actions':{'RequestIds':request_ids(['RunMaintenance']),'RunMaintenance':action('RunMaintenance',"@string(setProperty(json('{}'),'cursor',variables('cursor')))",'RequestIds'),'NextCursor':{'type':'SetVariable','inputs':{'name':'cursor','value':"@coalesce(json(body('RunMaintenance')?['ResultJson'])?['NextCursor'],'')"},'runAfter':{'RunMaintenance':['Succeeded']}}},'runAfter':{'Cursor':['Succeeded']}}}
    a['Sweep']['actions']['RequestIds']=request_ids(['RunMaintenance','ApplyRetention'])
    a['Sweep']['actions']['ApplyRetention']=action('ApplyRetention',after='NextCursor')
    save('Watchdog','WQCore',workflow('Watchdog',recurrence(),a))
    a={'ListRuns':connector('ListRecords',{'entityName':'qmcp_wqtestruns','$filter':"qmcp_outcome eq 'Running'",'$top':50}),
       'Advance':{'type':'Foreach','foreach':"@body('ListRuns')?['value']",'runtimeConfiguration':{'concurrency':{'repetitions':1}},'actions':{'RequestIds':request_ids(['AdvanceTestRun']),'AdvanceTestRun':action('AdvanceTestRun',after='RequestIds')},'runAfter':{'ListRuns':['Succeeded']}}}
    a['Advance']['actions']['AdvanceTestRun']['inputs']['parameters'].update({'item/ItemId':"@items('Advance')?['qmcp_key']",'item/QueueKey':"@items('Advance')?['qmcp_queuekey']"})
    save('TestCoordinator','WQTesting',workflow('TestCoordinator',recurrence(),a))
    claim=action('ClaimEvent',after='RequestIds')
    event="json(body('ClaimEvent')?['ResultJson'])?['Event']"
    send=connector('SendEmailV2',{'emailMessage/To':"@parameters('qmcp_NotificationAddress')",'emailMessage/Subject':"@concat('Queue event ', "+event+"?['Id'])",'emailMessage/Body':"@concat('Queue: ',parameters('qmcp_QueueKey'),'<br>Event: ',"+event+"?['Id'],'<br>Item: ',"+event+"?['ItemId'],'<br>Disposition: ',"+event+"?['Kind'])"},connection='qmcp_Outlook',api=outlook)
    finish=lambda ok:action('FinishEvent',"@string(setProperty(setProperty(setProperty(setProperty(json('{}'),'eventId',"+event+"?['Id']),'leaseToken',"+event+"?['LeaseToken']),'accepted',"+str(ok).lower()+"),'code','SENDER_FAILED'))")
    a={'RequestIds':request_ids(['ClaimEvent','FinishEvent']),'ClaimEvent':claim,'HasEvent':{'type':'If','expression':{'equals':["@json(body('ClaimEvent')?['ResultJson'])?['Outcome']",'Claimed']},'actions':{'Send':send,'Accepted':finish(True),'Rejected':finish(False)},'else':{'actions':{}},'runAfter':{'ClaimEvent':['Succeeded']}}}
    a['HasEvent']['actions']['Accepted']['runAfter']={'Send':['Succeeded']};a['HasEvent']['actions']['Rejected']['runAfter']={'Send':['Failed','TimedOut']}
    save('EmailSender','WQNotificationsEmail',workflow('EmailSender',recurrence(),a,('qmcp_Dataverse','qmcp_Outlook')))
    write_json(ROOT/'templates/catalog.json',{'version':VERSION,'customerFlows':['Intake.json','ProcessOne.json','OnQueueChanged.json','SweepQueue.json'],'frameworkFlows':['Watchdog.json','TestCoordinator.json','EmailSender.json'],'owner':'customer','activation':'disabled until tenant binding and validation','promptBinding':'ProcessOne/HasWork/Business/CreateIfAbsent/Prompt'})
    write_json(ROOT/'templates/extraction-output.schema.json',output_schema)

if __name__=='__main__': generate();print('Generated seven disabled flow candidates with explicit prompt binding gate.')
