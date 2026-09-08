export type InventoryRow = {
  available_quantity: number;
  reserved_quantity: number;
  updated_at: string;
};

export type Product = {
  id: string;
  sku: string;
  name: string;
  description: string;
  category: string;
  brand: string | null;
  unit: string;
  price: number;
  currency: string;
  aliases: string[];
  dietary_tags: string[];
  image_url: string | null;
  inventory: InventoryRow | InventoryRow[] | null;
};

export type Proposal = {
  action: "ADD_ITEM" | "MERGE_ITEMS" | "SUBSTITUTE_ITEM";
  productId: string;
  quantity: number;
  replacesProductId?: string | null;
};

export type AssistantResponse = {
  responseType:
    | "ANSWER"
    | "CLARIFICATION"
    | "CART_PROPOSAL"
    | "NO_MATCH"
    | "REFUSAL"
    | "ERROR";
  message: string;
  requiresConfirmation: boolean;
  correlationId: string;
  proposal?: Proposal | null;
  candidates?: Array<{
    productId: string;
    name: string;
    similarityScore?: number | null;
  }>;
};
