const nativeEntities = new Set(['workqueue', 'workqueues', 'workqueueitem', 'workqueueitems']);
const recordWrites = new Set(['CreateRecord', 'UpdateRecord', 'DeleteRecord']);
const testOperations = new Set(['qmcp_WQ_StartTestRun', 'qmcp_WQ_CancelTestRun', 'qmcp_WQ_CleanupTestRun']);

export function validateFlow(flow) {
  const issues = [];
  const add = (code, path) => issues.push({ code, path });
  const visitNode = (node, path) => {
    if (!node || typeof node !== 'object') return;
    const host = node.inputs?.host;
    const parameters = node.inputs?.parameters || {};
    if (host && typeof host === 'object') {
      if (Object.prototype.hasOwnProperty.call(host, 'connectionReferenceName')) add('LEGACY_CONNECTION_HOST', path);
      if (recordWrites.has(host.operationId) && nativeEntities.has(String(parameters.entityName || '').toLowerCase())) add('RAW_NATIVE_QUEUE_WRITE', path);
      if (host.operationId === 'PerformUnboundAction') {
        const action = parameters.actionName;
        if (action === 'qmcp_WQ_Complete' && (!node.runAfter || Object.keys(node.runAfter).length === 0)) add('UNCONDITIONAL_COMPLETE', path);
        if (testOperations.has(action) && JSON.stringify(node).toLowerCase().includes('production')) add('PRODUCTION_TEST_DESTINATION', path);
      }
    }
    if (node.actions && typeof node.actions === 'object') visitCollection(node.actions, `${path}/actions`);
    if (node.else?.actions && typeof node.else.actions === 'object') visitCollection(node.else.actions, `${path}/else`);
  };
  const visitCollection = (collection, path) => {
    if (!collection || typeof collection !== 'object') return;
    for (const [name, child] of Object.entries(collection)) visitNode(child, `${path}/${name}`);
  };
  visitCollection(flow?.properties?.definition?.triggers, 'triggers');
  visitCollection(flow?.properties?.definition?.actions, 'actions');
  return {
    status: issues.length ? 'failed' : 'passed',
    issues,
    limitations: [
      'Static inspection cannot prove tenant permissions, connector behavior, or flow runtime outcomes.',
      'Authentication profile ownership and serialization must be verified by the deployment host and tenant procedure.',
      'Dynamic expressions are reported only when an unsafe value is statically visible.'
    ]
  };
}
