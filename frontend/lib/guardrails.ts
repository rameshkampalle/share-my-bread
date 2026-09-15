/** Server-only helper. Call exclusively from the assistant route. */
export class GuardrailUnavailable extends Error {}

export async function checkRail(stage: 'input' | 'output', text: string): Promise<{ status: 'passed' | 'modified' | 'blocked'; text: string }> {
  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  const secret = process.env.GUARDRAILS_API_SECRET;
  if (!baseUrl || !secret) throw new GuardrailUnavailable();
  try {
    const response = await fetch(`${baseUrl.replace(/\/$/, '')}/api/guardrails/check`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'X-Guardrails-Secret': secret },
      body: JSON.stringify({ stage, text }), cache: 'no-store', redirect: 'error',
      signal: AbortSignal.timeout(20000),
    });
    if (!response.ok) throw new GuardrailUnavailable();
    const result = await response.json();
    if (!result || !['passed', 'modified', 'blocked'].includes(result.status) || typeof result.text !== 'string') {
      throw new GuardrailUnavailable();
    }
    if (result.status !== 'blocked' && (!result.text.trim() || (result.status === 'passed' && result.text !== text))) {
      throw new GuardrailUnavailable();
    }
    return result;
  } catch {
    throw new GuardrailUnavailable();
  }
}
