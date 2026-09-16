// Executed inside the n8n Code node. Evidence comes from tool observations,
// never from the model's JSON response. The backend verifies signatures.
const steps = $json.intermediateSteps;
if (!Array.isArray(steps) || steps.length > 12) throw new Error('Invalid tool trace');
const evidence = [];
for (const step of steps) {
  if (step.action?.tool !== 'product_catalogue') throw new Error('Unexpected assistant tool');
  const observation = typeof step.observation === 'string' ? JSON.parse(step.observation) : step.observation;
  const results = Array.isArray(observation) ? observation : [observation];
  for (const result of results) {
    if (!result || typeof result.evidence !== 'string') throw new Error('Catalogue evidence missing');
    evidence.push(result.evidence);
  }
}
const value = JSON.parse($json.output);
if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Invalid assistant response');
if ('_guardrailEvidence' in value) throw new Error('Reserved response field');
value.correlationId = $('Normalize Agent Request').first().json.correlationId;
// Full schema, confirmation rules, and product grounding are enforced by backend.
return [{ json: { ...value, _guardrailEvidence: evidence } }];
