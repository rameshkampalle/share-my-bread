import type { AssistantResponse, Product } from "./types";

// Recover selectable recommendations only from exact, known catalogue SKUs or product IDs.
// This never creates a cart mutation or skips the member's item selection.
export function withCatalogueRecommendations(response: AssistantResponse, products: Product[]): AssistantResponse {
  if (response.responseType !== "ANSWER" || response.proposal || response.candidates?.length) return response;
  const tokens = new Set(response.message.toUpperCase().match(/[A-Z0-9]+(?:-[A-Z0-9]+)+/g) ?? []);
  const matches = products.filter(product => tokens.has(product.sku.toUpperCase()) || tokens.has(product.id.toUpperCase()));
  if (!matches.length) return response;
  return { ...response, candidates: matches.map(product => ({ productId: product.id, name: product.name, quantity: 1 })) };
}
