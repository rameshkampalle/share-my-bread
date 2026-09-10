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
  member_subtotal: number;
  viewer_role: "MEMBER" | "ADMIN";
  lines: Array<{ id: string; product_id: string; name: string; sku: string; unit: string; quantity: number; unit_price: number; line_total: number; contributor_id: string; contributor_name: string; editable: boolean }>;
};

export type Workspace = {
  profile: { id: string; display_name: string; app_role: "MEMBER" | "ADMIN"; can_shop: boolean; can_deliver: boolean };
  groups: Array<{
    id: string;
    name: string;
    join_code: string;
    member_role: "MEMBER" | "COORDINATOR";
    coordinator_id: string;
    pickup_point_id: string | null;
    pickup_label: string | null;
    pickup_address: string | null;
    cycle: { id: string; status: string; cutoff_at: string; version: number; active_line_count: number; created_at: string; updated_at: string } | null;
    members: Array<{ id: string; display_name: string; app_role: "MEMBER" | "ADMIN"; member_role: "MEMBER" | "COORDINATOR"; reliability_state: string; joined_at: string; decision: string; decided_at: string | null }>;
  }>;
};

export type Journey = {
  cycle: { id: string; status: string; cutoff_at: string; group_name: string };
  authorization: { id: string; decision: string; snapshot_hash: string; decided_at: string } | null;
  order: { id: string; order_number: string; status: string; subtotal: number; finalized_at: string | null; created_at: string; updated_at: string } | null;
  order_lines: Array<{ id: string; product_snapshot: { name: string; sku: string; unit: string }; quantity: number; unit_price: number; total: number }>;
  allocations: Array<{ id: string; line_id: string; amount: number; basis: string }>;
  obligation: { id: string; amount_due: number; amount_collected: number; status: string; committed_at: string | null; updated_at: string } | null;
  group_obligations: Array<{ id: string; user_id: string; display_name: string; amount_due: number; amount_collected: number; status: string; items_collected: boolean; committed_at: string | null; updated_at: string }>;
  pending_commitments: number;
  pending_collections: number;
  pending_item_collections: number;
  member_decisions: Array<{ id: string; display_name: string; member_role: string; decision: string; decided_at: string | null }>;
  fulfilment_events: Array<{ id: string; old_status: string | null; new_status: string; source: string; note: string | null; created_at: string }>;
  audit_events: Array<{ id: string; action: string; entity_type: string; after_json: Record<string, unknown> | null; created_at: string }>;
  is_admin: boolean;
  is_coordinator: boolean;
  dev_fulfilment_mode: boolean;
};

export type OrderHistoryItem = {
  id: string;
  order_number: string;
  status: string;
  subtotal: number;
  finalized_at: string | null;
  created_at: string;
  updated_at: string;
  group_name: string;
  cash_status: string | null;
  amount_due: number | null;
  amount_collected: number | null;
  pending_item_collections: number;
  lines: Array<{ id: string; name: string; sku: string; unit: string; quantity: number; total: number }>;
};

export type NotificationFeed = {
  unread: number;
  items: Array<{ id: string; notification_type: string; title: string; message: string; aggregate_id: string | null; read_at: string | null; created_at: string }>;
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
    quantity?: number;
  }>;
};
