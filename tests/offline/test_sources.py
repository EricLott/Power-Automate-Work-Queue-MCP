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
