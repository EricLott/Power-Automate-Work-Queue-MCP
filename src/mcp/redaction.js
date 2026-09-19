const sensitiveKey = /authorization|access.?token|refresh.?token|client.?secret|password|credential|connection.?string|cookie|secret|token|headers?/i;
const untrustedContentKey = /^(?:input|body|bodyText|raw|rawContent|payload|content|mailBody)$/i;

/**
 * Project returned values before they cross the MCP boundary. This is a
 * field-based disclosure control, not an instruction sanitizer: remaining
 * business text is still untrusted data and must not be treated as commands.
 */
export function redactForAgent(value, key = '') {
  if (sensitiveKey.test(key)) return '[REDACTED]';
  if (untrustedContentKey.test(key)) return '[UNTRUSTED_CONTENT_REDACTED]';
  if (Array.isArray(value)) return value.map(item => redactForAgent(item));
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([name, child]) => [name, redactForAgent(child, name)]));
  }
  return value;
}
