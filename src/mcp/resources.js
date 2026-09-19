import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { root } from './local.js';

const resources = [
  { name: 'architecture-v0-1', uri: 'qmcp://wq/architecture/v0.1', title: 'Work Queue architecture v0.1', description: 'Proposed architecture and implementation boundaries.', mimeType: 'text/markdown', file: 'docs/architecture.md' },
  { name: 'native-envelope-v1', uri: 'qmcp://wq/schema/native-envelope/v1', title: 'Native queue envelope schema v1', description: 'Bounded native queue envelope schema.', mimeType: 'application/json', file: 'templates/native-envelope.schema.json' },
  { name: 'extraction-output-v1', uri: 'qmcp://wq/schema/extraction-output/v1', title: 'Extraction output schema v1', description: 'Bounded extraction result schema.', mimeType: 'application/json', file: 'templates/extraction-output.schema.json' },
  { name: 'mail-contract-v1', uri: 'qmcp://wq/contract/mail.v1', title: 'Reference mail contract v1', description: 'Synthetic reference business contract and queue policy.', mimeType: 'application/json', file: 'config/reference.json' },
  { name: 'testing-v1', uri: 'qmcp://wq/testing/v1', title: 'Testing guidance v1', description: 'Cancellation, evidence, and test-isolation guidance.', mimeType: 'text/markdown', file: 'docs/test-cancellation.md' },
  { name: 'diagnostics-v1', uri: 'qmcp://wq/diagnostics/v1', title: 'Validation and diagnostics v1', description: 'Validation gates, evidence boundaries, and known limitations.', mimeType: 'text/markdown', file: 'docs/validation.md' }
];

const flowCatalog = JSON.parse(await readFile(path.join(root, 'templates/catalog.json'), 'utf8'));
for (const file of [...flowCatalog.customerFlows, ...flowCatalog.frameworkFlows]) {
  const flowName = path.basename(file, '.json');
  resources.push({
    name: `flow-${flowName.toLowerCase()}`,
    uri: `qmcp://wq/flow/${flowName}/v1`,
    title: `${flowName} reference flow v1`,
    description: `Versioned ${flowName} reference flow source.`,
    mimeType: 'application/json',
    file: `templates/flows/${file}`
  });
}

export function registerResources(server) {
  for (const resource of resources) {
    server.registerResource(resource.name, resource.uri, {
      title: resource.title,
      description: resource.description,
      mimeType: resource.mimeType
    }, async uri => ({
      contents: [{
        uri: uri.href,
        mimeType: resource.mimeType,
        text: await readFile(path.join(root, resource.file), 'utf8')
      }]
    }));
  }
  return resources.map(({ name, uri, title }) => ({ name, uri, title }));
}
