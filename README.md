# P2P Hackathon MCP Server

In-memory MCP server for the P2P AI Agent hackathon, with a lightweight JSON-file
persistence layer so state survives a Render cold start mid-demo. **No database
required.**

## Run

```bash
python3 server.py
```

Transport: `stdio` (wire directly into GEP P2P agent tool nodes).

## Persistence

State (carts, reqs, POs, GRs, invoices) is written to `p2p_state.json` next to
`server.py` after every mutating call and reloaded on startup. This protects a
live demo from Render's free-tier ~15 min idle spin-down wiping in-memory state
between the pitch and the walkthrough. Call `demo_reset` to clear it for a clean
re-run.

## Tools (34 total)

### Catalog Agent
| Tool | Description |
|---|---|
| `catalog_search` | Search catalog by keyword, category, max_price |
| `catalog_get_item` | Get item details by item_id |
| `cart_create` | Create a new empty cart → returns `cart_id` |
| `cart_add_item` | Add item+qty to a cart |
| `cart_view` | View cart contents and total |
| `cart_flip` | Finalise cart → ready for requisition |

### Requisition Agent
| Tool | Description |
|---|---|
| `req_create` | Create requisition from flipped cart → returns `req_id` |
| `req_set_accounting` | Set cost_center + gl_account |
| `req_set_delivery` | Set deliver_to + need_by date |
| `req_submit` | Submit for approval → status: PENDING_APPROVAL. Computes an `approval_tier` (AUTO ≤$2k / MANAGER ≤$20k / DIRECTOR >$20k) from spend |
| `req_get_status` | Poll status |
| `req_get` | Get full details of a requisition (status, accounting, delivery, lines) — used for status-check lookups |
| `req_approve` | Approve → status: APPROVED. DIRECTOR-tier reqs approved without an `approver_note` come back with `audit_flag: true` |

### Order Agent
| Tool | Description |
|---|---|
| `order_create` | Create PO from approved req → returns `po_id` |
| `order_get` | Get full PO details |
| `order_finalize` | Issue PO to supplier → status: ISSUED |
| `order_get_status` | Check PO status |

### Goods Receipt Agent
| Tool | Description |
|---|---|
| `gr_create` | Create GR shell from issued PO → returns `gr_id` |
| `gr_record` | Record qty_received per line |
| `gr_confirm` | Confirm receipt + discrepancy check |
| `gr_get` | Get full GR details |

### Invoice Agent
| Tool | Description |
|---|---|
| `invoice_create` | Create invoice from confirmed GR → returns `inv_id`. Blocks duplicate invoicing against the same PO |
| `invoice_match` | Run 3-way match (PO vs GR vs Invoice, 2% tolerance) |
| `invoice_get_match_result` | Get per-line match deltas |
| `invoice_get` | Get full details of an invoice regardless of match status — used for status-check lookups |
| `invoice_approve` | Approve invoice |
| `invoice_finalize` | Finalise → emits InvoicePaid event, P2P cycle COMPLETE |

### Demo Tools
| Tool | Description |
|---|---|
| `demo_reset` | Clear all carts/reqs/POs/GRs/invoices for a clean re-run. Catalog is unaffected |

### Observability
| Tool | Description |
|---|---|
| `cart_list` / `req_list` / `order_list` / `gr_list` / `invoice_list` | List all records of that type (id, status, key totals), most-recent-first |
| `trace_chain` | Given ANY one of cart_id/req_id/po_id/gr_id/inv_id, walk the linked chain and return whichever of cart → req → PO → GR → invoice exist and are connected |

## Live Dashboard

`GET /dashboard` (same host/port as the MCP server, e.g.
`https://p2p-hackathon-mcp.onrender.com/dashboard`) renders a live, auto-refreshing
(every 5s) HTML view of every cart/requisition/PO/GR/invoice with status badges.
Keep it open on a second screen during the demo — it's the visible proof that the
agent is driving a real backend, not a scripted transcript. No new dependencies;
reuses the same `@mcp.custom_route` pattern as `/mcp-health`.

## Pre-seeded Catalog Items

| ID | Name | Price |
|---|---|---|
| ITEM-001 | HP Laptop 15.6" | $850 |
| ITEM-002 | Dell Laptop 14" | $780 |
| ITEM-003 | Office Chair Ergonomic | $220 |
| ITEM-004 | 24" Monitor Full HD | $310 |
| ITEM-005 | Wireless Keyboard & Mouse Combo | $55 |
| ITEM-006 | USB-C Docking Station | $130 |
| ITEM-007 | A4 Paper Ream 500 Sheets | $8 |
| ITEM-008 | Webcam HD 1080p | $75 |

## Happy Path Flow

```
catalog_search → cart_create → cart_add_item → cart_view → cart_flip
→ req_create → req_set_accounting → req_set_delivery → req_submit → req_approve
→ order_create → order_finalize → order_get_status
→ gr_create → gr_record → gr_confirm
→ invoice_create → invoice_match → invoice_approve → invoice_finalize
```

## QiStudio Agents (`main_agent.json`, `catalog_agent_fixed_1.json`, `req_agent.json`,
`order_agent.json`, `gr_agent.json`, `invoice_agent.json`)

Each domain agent is a 6-node pipeline (Intent Analyzer → Planner → Tool Executer →
Validator → Event Builder → Response Builder), routed by `main_agent.json`'s
router + rule node.

**Fixed a chaining bug**: the router previously invoked each downstream agent with
only the raw buyer message, never the structured event object (`cartFlipEvent`,
`reqApprovedEvent`, `poIssuedEvent`, `grConfirmedEvent`) that agent's Intent
Analyzer expected as a *required* input — so anything past the Catalog stage had
nothing to extract from. Fixed by making the event-object inputs optional on each
downstream agent, with the Intent Analyzer falling back to parsing the relevant
ID (`cart_id`/`req_id`/`po_id`/`gr_id`) out of the buyer's message or the
appended conversation history — the actual MCP tools (`req_create`,
`order_create`, `gr_create`, `invoice_create`) only ever needed that one ID,
since they look up the rest of the record server-side.

First attempt threaded the ID via a `flow.lastId` flow-scoped variable, which
turned out not to survive across separate user turns in the same QiStudio
session (flow variables there appear to be execution-scoped, not
session-scoped — confirmed by a live test where requisition creation still
came back asking for `cart_id` after cart creation succeeded in the same
conversation). Replaced with `{{thread.messages}}` — the conversation
transcript, which *is* built by `append`/`extend` on every node across every
turn and is therefore guaranteed to persist — passed into each downstream
agent's message input, with the Intent Analyzer instructed to scan it for the
most recent matching ID. `flow.lastId` is left wired as a redundant hint in
case it does persist in some invocation paths, but `thread.messages` is now the
primary mechanism.

Also fixed `gr_confirm` dropping `unit_price` from its output, which silently
priced every invoice line at 0 and made `invoice_match` always report MISMATCH.

**Second bug in the same area**: even after the above, RequisitionAgent,
OrderAgent, and InvoiceAgent's Intent Analyzer *user*-turn prompt only ever
referenced the (empty) upstream event object — `{{system.cartFlipEvent}}`,
`{{system.reqApprovedEvent}}`, `{{system.grConfirmedEvent}}` — and never
included `{{system.userQuery}}`. The fallback instructions added to the
*system* prompt told the model to look for an ID in the buyer's message, but
the user turn never actually contained that message, so there was nothing to
find no matter what the buyer typed. Fixed by adding `{{system.userQuery}}` to
all three user prompts, matching what GoodsReceiptAgent's template already did
correctly. Confirmed working end-to-end live (cart → CartFlipped → requisition
created and approved).

All six workflows are enabled (`isDisabled: false`). Re-import these JSONs into
QiStudio to pick up the fixes.

## Approval Architecture (current state)

Verified by code audit — worth knowing precisely before presenting this as a
feature to judges:

- `req_submit` computes an `approval_tier` (AUTO/MANAGER/DIRECTOR by spend) —
  **informational only**. `req_approve` always sets `APPROVED` unconditionally
  regardless of tier; the `audit_flag` it returns is never enforced anywhere.
- `order_finalize` and `invoice_approve` likewise always succeed —
  `invoice_approve` approves a MISMATCH invoice exactly like a MATCHED one.
- The only *real* gates are ordering preconditions, not human judgment:
  `order_create` requires the req be `APPROVED`, `gr_create` requires the PO be
  `ISSUED`, `invoice_finalize` requires the invoice be `APPROVED`.
- The **only** genuine human-in-the-loop pause in the system is the GR
  short-shipment path: `gr_validator` sets `recommendation: NEEDS_CLARIFICATION`
  on a quantity mismatch, which halts the chain (`routing.next_node: null`,
  `requires_approval: true`) and the response builder explicitly waits for the
  buyer's decision. This is real and demo-able today.
- `req_agent.json` has a parallel `ReqPendingApproval` event shape scaffolded,
  but nothing in `server.py` can currently trigger it (`req_approve` never
  fails) — it's unreachable dead code unless real gating is added later.

## Two more bugs found via the live dashboard

### Cart duplication

CatalogAgent was the *only* one of the five domain agents whose message input
from `main_agent.json` wasn't enriched with `{{thread.messages}}` (it was
treated as "the entry point, no continuity needed" — wrong, since it's
re-invoked on every cart-related turn, not just the first). Its own Planner
had no way to know a cart already existed, so it called `cart_create` fresh
on every `ADD_TO_CART`/`FULL_PURCHASE` turn — visibly confirmed on the
dashboard as two carts with identical contents a few minutes apart, one
`OPEN` and one `FLIPPED`. Fixed by enriching `main_agent.json`'s message input
to `catalogagent` the same way as the other four agents, and adding
`existing_cart_id` detection to CatalogAgent's Intent Analyzer/Planner/Tool
Executer so an open cart from earlier in the session is reused instead of
recreated.

### Agents could only create records, never look them up

Asking OrderAgent *"Get the details about PO-014E793A"* in a fresh session —
even with the PO ID right there in the message — failed with `req_id missing
from order intent`, `steps_completed: 0`, `no po_id generated`, even though
the dashboard proved that PO genuinely existed and was `ISSUED`. Root cause:
unlike CatalogAgent (which has `SEARCH_ONLY`/`ADD_TO_CART`/`FULL_PURCHASE`
branching), the Requisition/Order/GR/Invoice Planners were hardcoded to
*always* build a create-and-process pipeline, with no path for "the buyer is
just asking about an existing record." Fixed by adding a `mode`
(`PROCESS`/`STATUS_CHECK`) + `lookup_id` field to each of those four agents'
Intent Analyzer, and a Planner branch that builds a single-step read-only plan
(`req_get`/`order_get`/`gr_get`/`invoice_get`) when `mode == STATUS_CHECK`,
instead of the full create pipeline. `req_get` and `invoice_get` are new
tools added to `server.py` (the other two already existed) — deliberately
appended at the *end* of the tool list rather than inserted alongside their
siblings, since FastMCP's tool `toolId`s are order-dependent and every other
agent's already-working tool bindings depend on the existing tools keeping
their original position.