import { expect, it } from "vitest";
import { withCatalogueRecommendations } from "@/lib/assistant-recommendations";
import type { AssistantResponse, Product } from "@/lib/types";
const products = [{ id: "bean-id", sku: "PULSE-004", name: "Kidney Beans" }] as Product[];
const answer: AssistantResponse = { responseType: "ANSWER", message: "Use Kidney Beans (SKU: PULSE-004). Would you like to add them?", requiresConfirmation: false, correlationId: "test" };
it("makes exact catalogue references selectable without creating a proposal", () => {
 const result = withCatalogueRecommendations(answer, products);
 expect(result.candidates).toEqual([{ productId: "bean-id", name: "Kidney Beans", quantity: 1 }]);
 expect(result.proposal).toBeUndefined(); expect(result.requiresConfirmation).toBe(false);
});
it("does not invent products or recover refused recommendations", () => {
 expect(withCatalogueRecommendations({...answer, message: "Use PULSE-0040 or MADEUP-001"}, products).candidates).toBeUndefined();
 expect(withCatalogueRecommendations({...answer, responseType: "REFUSAL"}, products).candidates).toBeUndefined();
});
it("preserves structured quantities and proposals", () => {
 const structured = {...answer, candidates: [{ productId: "bean-id", name: "Kidney Beans", quantity: 3 }]};
 expect(withCatalogueRecommendations(structured, products)).toBe(structured);
});
