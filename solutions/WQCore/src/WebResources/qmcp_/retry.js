(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.QueueOperations = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
  const queueKey = /^[a-z][a-z0-9_-]{0,63}$/;
  function request(operation, queue, item, data, version, requestId) {
    if (!['GetItemStatus', 'RequestRetry'].includes(operation)) throw new Error('OPERATION_INVALID');
    if (typeof queue !== 'string' || !queueKey.test(queue) || typeof item !== 'string' || !uuid.test(item) || typeof requestId !== 'string' || !uuid.test(requestId)) throw new Error('IDENTITY_INVALID');
    if (operation === 'RequestRetry' && (!Number.isSafeInteger(version) || version < 0)) throw new Error('VERSION_INVALID');
    if (data === null || typeof data !== 'object' || Array.isArray(data)) throw new Error('INPUT_INVALID');
    if (operation === 'RequestRetry' && (typeof data.reason !== 'string' || !data.reason.trim() || data.reason.length > 500 || data.reconciliation !== 'VerifiedSafe')) throw new Error('RECONCILIATION_REQUIRED');
    const dataJson = JSON.stringify(data);
    const dataBytes = typeof TextEncoder !== 'undefined' ? new TextEncoder().encode(dataJson).length : dataJson.length;
    if (dataBytes > 8192) throw new Error('INPUT_TOO_LARGE');
    return {
      QueueKey: queue, RequestId: requestId, ItemId: item, DataJson: dataJson, ExpectedVersion: operation === 'RequestRetry' ? String(version) : '',
      getMetadata: function () {
        return { boundParameter: null, operationType: 0, operationName: 'qmcp_WQ_' + operation, parameterTypes: Object.fromEntries(['QueueKey','RequestId','ItemId','DataJson','ExpectedVersion'].map(name => [name, { typeName: 'Edm.String', structuralProperty: 1 }])) };
      }
    };
  }
  async function invoke(xrm, operation, queue, item, data, version, requestId) {
    const response = await xrm.WebApi.online.execute(request(operation, queue, item, data, version, requestId));
    if (!response.ok) throw new Error('REQUEST_FAILED');
    const result = await response.json();
    if (typeof result.ResultJson !== 'string') throw new Error('API_BINDING_INVALID');
    return JSON.parse(result.ResultJson);
  }
  return { request, invoke };
});
