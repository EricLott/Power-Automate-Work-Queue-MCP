const operations = new Set(['RegisterQueue','RegisterContract','Enqueue','GetItemStatus','GetQueueHealth','StartTestRun','CancelTestRun','GetTestRun','CleanupTestRun']);
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
export class DataverseClient {
  constructor(binding, tokenProvider, fetchImpl = fetch) {
    const url = new URL(binding.environmentUrl);
    if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash || !['','/'].includes(url.pathname)) throw new Error('ENVIRONMENT_URL_INVALID');
    if (!uuid.test(binding.organizationId) || binding.environmentClass !== 'development') throw new Error('DEVELOPMENT_BINDING_REQUIRED');
    if (!Array.isArray(binding.queueKeys) || !binding.queueKeys.length || new Set(binding.queueKeys).size !== binding.queueKeys.length || binding.queueKeys.some(key => typeof key !== 'string' || !/^[a-z][a-z0-9_-]{0,63}$/.test(key))) throw new Error('QUEUE_ALLOWLIST_REQUIRED');
    this.binding = { ...binding, environmentUrl: url.origin }; this.tokenProvider = tokenProvider; this.fetch = fetchImpl;
  }
  async request(route, body) {
    const token = await this.tokenProvider(); if (!token) throw new Error('ACCESS_TOKEN_REQUIRED');
    const result = await this.fetch(this.binding.environmentUrl + '/api/data/v9.2/' + route, {
      method: body ? 'POST' : 'GET', redirect: 'error', signal: AbortSignal.timeout(30000),
      headers: { Authorization: 'Bearer ' + token, Accept: 'application/json', 'Content-Type': 'application/json', 'OData-Version': '4.0', 'OData-MaxVersion': '4.0' },
      body: body ? JSON.stringify(body) : undefined
    });
    if (!result.ok) throw new Error(result.status === 401 || result.status === 403 ? 'DATAVERSE_ACCESS_DENIED' : 'DATAVERSE_REQUEST_FAILED');
    const text = await result.text(); if (text.length > 1000000) throw new Error('RESPONSE_TOO_LARGE');
    return JSON.parse(text);
  }
  async verify() {
    const identity = await this.request('WhoAmI');
    if (identity.OrganizationId?.toLowerCase() !== this.binding.organizationId.toLowerCase()) throw new Error('ENVIRONMENT_MISMATCH');
    return { organizationId: identity.OrganizationId, userId: identity.UserId };
  }
  async invoke(operation, queueKey, data, fields, requestId) {
    if (!operations.has(operation)) throw new Error('OPERATION_NOT_EXPOSED');
    if (!this.binding.queueKeys.includes(queueKey)) throw new Error('QUEUE_NOT_BOUND');
    if (!uuid.test(requestId)) throw new Error('REQUEST_ID_INVALID');
    const dataJson = JSON.stringify(data);
    if (Buffer.byteLength(dataJson) > 131072) throw new Error('INPUT_TOO_LARGE');
    await this.verify();
    // The request ID is supplied once by the caller; this client never silently retries a mutation.
    const input = { QueueKey: queueKey, RequestId: requestId, DataJson: dataJson, ItemId: fields.ItemId || '', AttemptId: fields.AttemptId || '', Generation: fields.Generation || 0, ExpectedVersion: String(fields.ExpectedVersion || '') };
    const output = await this.request('qmcp_WQ_' + operation, input);
    if (typeof output.ResultJson !== 'string') throw new Error('API_BINDING_INVALID');
    return JSON.parse(output.ResultJson);
  }
}
