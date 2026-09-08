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
  action: "ADD_ITEMS";
  items: Array<{ productId: string; name: string; quantity: number }>;
};

export type Cart = {
  cycle_id: string;
  cutoff_at: string;
  group_name: string;
  currency: string;
  subtotal: number;
  lines: Array<{ id: string; product_id: string; name: string; sku: string; unit: string; quantity: number; unit_price: number; line_total: number }>;
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
