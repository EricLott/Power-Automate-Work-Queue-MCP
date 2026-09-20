import copy
import json
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from validate_sources import validate_flow, canonical_xml

class FlowInvariantTests(unittest.TestCase):
    def flow(self,name):return json.loads((ROOT/'templates/flows'/(name+'.json')).read_text())
    def test_all_generated_flows(self):
        for file in (ROOT/'templates/flows').glob('*.json'):validate_flow(json.loads(file.read_text()),file.stem)

    def test_optional_sender_connector_is_not_required_by_core(self):
        core = (ROOT/'solutions'/'WQCore'/'src'/'Other'/'Customizations.xml').read_text()
        sender = (ROOT/'solutions'/'WQNotificationsEmail'/'src'/'Other'/'Customizations.xml').read_text()
        self.assertIn('shared_commondataserviceforapps', core)
        self.assertNotIn('shared_office365', core)
        self.assertNotIn('qmcp_notifications_outlook', core)
        self.assertIn('shared_office365', sender)
        self.assertIn('qmcp_notifications_outlook', sender)
    def test_wrong_child_binding_rejected(self):
        flow=self.flow('OnQueueChanged');flow['properties']['definition']['actions']['ProcessOne']['inputs']['host']['workflowReferenceName']='wrong'
        with self.assertRaises(AssertionError):validate_flow(flow,'OnQueueChanged')
    def test_ownership_bypass_rejected(self):
        flow=self.flow('ProcessOne');a=flow['properties']['definition']['actions']['HasWork']['actions']['ReportFailure'];a['inputs']['parameters']['item/Generation']='@triggerBody()'
        with self.assertRaises(AssertionError):validate_flow(flow,'ProcessOne')
    def test_native_raw_write_rejected(self):
        flow=self.flow('ProcessOne');flow['properties']['definition']['actions']['Bad']={'type':'OpenApiConnection','inputs':{'host':{'connectionName':'qmcp_Dataverse','operationId':'UpdateRecord'},'parameters':{'entityName':'workqueueitems'}}}
        with self.assertRaises(AssertionError):validate_flow(flow,'ProcessOne')
    def test_legacy_connection_host_key_rejected(self):
        flow=self.flow('ProcessOne')
        host=flow['properties']['definition']['actions']['RequestIds']
        host['type']='OpenApiConnection'
        host['inputs']={'host':{'connectionReferenceName':'qmcp_Dataverse','operationId':'ListRecords'},'parameters':{}}
        with self.assertRaises(AssertionError):validate_flow(flow,'ProcessOne')
    def test_legacy_trigger_connection_host_key_rejected(self):
        flow=self.flow('OnQueueChanged')
        host=flow['properties']['definition']['triggers']['trigger']['inputs']['host']
        host['connectionReferenceName']=host.pop('connectionName')
        with self.assertRaises(AssertionError):validate_flow(flow,'OnQueueChanged')
    def test_webhook_trigger_requires_webhook_type(self):
        flow=self.flow('OnQueueChanged')
        flow['properties']['definition']['triggers']['trigger']['type']='OpenApiConnection'
        with self.assertRaises(AssertionError):validate_flow(flow,'OnQueueChanged')
    def test_unbounded_loop_rejected(self):
        flow=self.flow('Watchdog');flow['properties']['definition']['actions']['Sweep']['limit']['count']=100000
        with self.assertRaises(AssertionError):validate_flow(flow,'Watchdog')
    def test_unstable_request_id_rejected(self):
        flow=self.flow('ProcessOne');flow['properties']['definition']['actions']['PrepareAcquire']['inputs']['parameters']['item/RequestId']='@guid()'
        with self.assertRaises(AssertionError):validate_flow(flow,'ProcessOne')
    def test_missing_dependency_rejected(self):
        flow=self.flow('ProcessOne');flow['properties']['definition']['actions']['PrepareAcquire']['runAfter']={'missing':['Succeeded']}
        with self.assertRaises(AssertionError):validate_flow(flow,'ProcessOne')
    def test_completion_retry_reuses_request_and_output_id(self):
        flow=self.flow('ProcessOne');branch=flow['properties']['definition']['actions']['HasWork']['actions']
        self.assertEqual(branch['Complete']['runAfter'],{'OutputRecordId':['Succeeded']})
        self.assertEqual(branch['CompleteRetry']['runAfter'],{'Complete':['Failed','TimedOut']})
        self.assertEqual(branch['Complete']['inputs']['parameters']['item/RequestId'],branch['CompleteRetry']['inputs']['parameters']['item/RequestId'])
        self.assertIn("outputs('OutputRecordId')",branch['Complete']['inputs']['parameters']['item/DataJson'])

    def test_completion_failure_does_not_route_to_fail(self):
        flow=self.flow('ProcessOne');branch=flow['properties']['definition']['actions']['HasWork']['actions']
        self.assertEqual(branch['ReportFailure']['runAfter'],{'Business':['Failed','TimedOut']})
        self.assertEqual(branch['CompletionUnknown']['runAfter'],{'CompleteRetry':['Failed','TimedOut']})
        self.assertEqual(branch['CompletionUnknown']['type'],'Compose')
        self.assertNotIn('Complete',branch['ReportFailure']['runAfter'])

    def test_response_returns_on_handled_failure_and_is_truthful(self):
        flow=self.flow('ProcessOne');actions=flow['properties']['definition']['actions'];response=actions['Respond']
        self.assertEqual(response['runAfter'],{'HasWork':['Succeeded','Failed','TimedOut','Skipped']})
        outcome=response['inputs']['body']['outcome']
        for action in ('Complete','CompleteRetry','ReportFailure'):
            self.assertIn("actions('%s')?['status']"%action,outcome)
            self.assertIn("json(coalesce(body('%s')?['ResultJson'],'{}'))?['Outcome']"%action,outcome)
        self.assertIn("coalesce(outputs('Acquired')?['Outcome'],'Unknown')",outcome)
        self.assertIn("'Unknown'",outcome)

    def test_failure_diagnostics_use_bounded_stage_codes(self):
        flow=self.flow('ProcessOne');data=flow['properties']['definition']['actions']['HasWork']['actions']['ReportFailure']['inputs']['parameters']['item/DataJson']
        for stage in ('Prompt','NormalizeExtraction','ValidateExtraction','ValidateSender','ValidateIntent','CreateRecord','FindExisting','FindResult','Reconciled'):
            self.assertIn("actions('%s')?['status']"%stage,data)
            self.assertIn('%s_FAILED'%stage.upper(),data)
            self.assertIn('%s_TIMED_OUT'%stage.upper(),data)
        self.assertIn("'WORKER_SCOPE_FAILED'",data)
        self.assertNotIn("['body']",data)
        self.assertNotIn('message',data.lower())
        self.assertIn("'category','Unknown'",data)
        self.assertIn("'effect','Unknown'",data)

    def test_extraction_accepts_only_one_json_markdown_fence(self):
        flow=self.flow('ProcessOne');make=flow['properties']['definition']['actions']['HasWork']['actions']['Business']['actions']['CreateIfAbsent']['actions']
        normalized=make['NormalizeExtraction']['inputs']
        self.assertIn("startsWith(trim(string(body('Prompt')?['responsev2']?['predictionOutput']?['text'])),concat('```json',decodeUriComponent('%0A')))",normalized)
        self.assertIn("endsWith(trim(string(body('Prompt')?['responsev2']?['predictionOutput']?['text'])),'```')",normalized)
        self.assertIn("equals(length(split(",normalized)
        self.assertIn(",'```')),3)",normalized)
        self.assertIn("substring(",normalized)
        self.assertNotIn("startsWith(@",normalized)
        self.assertNotIn("'```json'),",normalized)
        self.assertEqual(make['ValidateExtraction']['inputs']['content'],"@outputs('NormalizeExtraction')")

    def test_prepare_captures_flow_provenance(self):
        flow=self.flow('ProcessOne');data=flow['properties']['definition']['actions']['PrepareAcquire']['inputs']['parameters']['item/DataJson']
        self.assertIn("'flowId', workflow()?['name']",data)

    def test_intent_evidence_is_source_bound_and_narrow(self):
        flow=self.flow('ProcessOne');make=flow['properties']['definition']['actions']['HasWork']['actions']['Business']['actions']['CreateIfAbsent']['actions'];schema=make['ValidateExtraction']['inputs']['schema'];intent=make['ValidateIntent']['expression']
        self.assertIn('intentEvidence',schema['required']);self.assertIn('intentSignal',schema['required']);self.assertEqual(schema['properties']['intentSignal']['enum'],['explicit-request','explicit-question']);self.assertEqual(schema['properties']['intentEvidence']['maxLength'],500)
        self.assertIn("contains(string(outputs('Acquired')?['Envelope']?['payload']?['bodyText'])",intent);self.assertIn("'please '",intent);self.assertIn("'what '",intent);self.assertIn("'explicit-request'",intent);self.assertIn("'explicit-question'",intent)
        self.assertEqual(make['ValidateIntent']['else']['actions']['RejectIntent']['metadata']['qmcpErrorCode'],'EXTRACTION_INTENT_UNSUPPORTED')

    def test_intent_rejection_cannot_reach_business_output_or_complete(self):
        flow=self.flow('ProcessOne')
        actions=flow['properties']['definition']['actions']['HasWork']['actions']
        business=actions['Business']
        make=business['actions']['CreateIfAbsent']['actions']
        rejection=make['ValidateIntent']['else']['actions']['RejectIntent']

        # The injected validator failure must fail the business scope. The
        # success-only dependencies below keep output lookup and Complete out
        # of the rejection path even if the provider returns schema-valid JSON.
        self.assertEqual(rejection['type'],'ParseJson')
        self.assertEqual(rejection['metadata']['qmcpErrorCode'],'EXTRACTION_INTENT_UNSUPPORTED')
        self.assertEqual(make['BusinessDocument']['runAfter'],{'ValidateIntent':['Succeeded']})
        self.assertEqual(actions['OutputRecordId']['runAfter'],{'Business':['Succeeded']})
        self.assertEqual(actions['Complete']['runAfter'],{'OutputRecordId':['Succeeded']})
        self.assertEqual(actions['ReportFailure']['runAfter'],{'Business':['Failed','TimedOut']})

    def test_completion_retry_changed_output_is_rejected(self):
        flow=self.flow('ProcessOne');branch=flow['properties']['definition']['actions']['HasWork']['actions']
        branch['CompleteRetry']['inputs']['parameters']['item/DataJson']='{}'
        with self.assertRaises(AssertionError):validate_flow(flow,'ProcessOne')

    def test_prompt_output_and_sender_validation_cannot_be_bypassed(self):
        flow=self.flow('ProcessOne');make=flow['properties']['definition']['actions']['HasWork']['actions']['Business']['actions']['CreateIfAbsent']['actions']
        make['BusinessDocument']['runAfter']={'Prompt':['Succeeded']}
        with self.assertRaises(AssertionError):validate_flow(flow,'ProcessOne')

    def test_expando_key_is_escaped_for_workflow_expression_parser(self):
        flow=self.flow('ProcessOne');make=flow['properties']['definition']['actions']['HasWork']['actions']['Business']['actions']['CreateIfAbsent']['actions']
        request=make['Prompt']['inputs']['parameters']['item/requestv2']
        self.assertIn('@@odata.type',request)
        self.assertNotIn('@odata.type',request)

    def test_business_rejection_does_not_terminate_failure_handler(self):
        flow=self.flow('ProcessOne');branch=flow['properties']['definition']['actions']['HasWork']['actions']
        branch['Business']['actions']['Reconciled']['else']['actions']['Conflict']['type']='Terminate'
        with self.assertRaises(AssertionError):validate_flow(flow,'ProcessOne')

class XmlRoundTripTests(unittest.TestCase):
    def test_sharded_records_start_with_element_not_declaration(self):
        # Dataverse SourceControlHandler appends these records to an aggregate
        # document. An XML declaration cannot be appended as an element child.
        files=list((ROOT/'solutions').glob('*/src/customapis/**/*.xml'))
        files+=list((ROOT/'solutions').glob('*/src/pluginpackages/**/*.xml'))
        self.assertTrue(files)
        for file in files:
            self.assertFalse(file.read_bytes().lstrip().startswith(b'<?xml'),str(file))

    def test_pac_set_order_is_accepted(self):
        before=b'<ImportExportXml><SolutionManifest><RootComponents><RootComponent schemaName="b"/><RootComponent schemaName="a"/></RootComponents></SolutionManifest></ImportExportXml>'
        after=b'<ImportExportXml><SolutionManifest><RootComponents><RootComponent schemaName="a"/><RootComponent schemaName="b"/></RootComponents></SolutionManifest></ImportExportXml>'
        self.assertEqual(canonical_xml(before), canonical_xml(after))

    def test_real_component_change_is_rejected(self):
        before=b'<ImportExportXml><SolutionManifest><RootComponents><RootComponent schemaName="a"/></RootComponents></SolutionManifest></ImportExportXml>'
        after=b'<ImportExportXml><SolutionManifest><RootComponents><RootComponent schemaName="changed"/></RootComponents></SolutionManifest></ImportExportXml>'
        self.assertNotEqual(canonical_xml(before), canonical_xml(after))

    def test_unlisted_sibling_order_remains_strict(self):
        before=b'<ImportExportXml><Entities><Entity><Name>a</Name><EntityInfo/></Entity><Entity><Name>b</Name><EntityInfo/></Entity></Entities></ImportExportXml>'
        after=b'<ImportExportXml><Entities><Entity><Name>b</Name><EntityInfo/></Entity><Entity><Name>a</Name><EntityInfo/></Entity></Entities></ImportExportXml>'
        self.assertNotEqual(canonical_xml(before), canonical_xml(after))

if __name__=='__main__':unittest.main()
