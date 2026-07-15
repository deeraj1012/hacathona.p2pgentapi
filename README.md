# P2P Hackathon MCP Server

Fully in-memory MCP server for the P2P AI Agent hackathon. **No database required.**

## Run

```bash
python3 server.py
```

Transport: `stdio` (wire directly into GEP P2P agent tool nodes).

## Tools (25 total)

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
| `req_submit` | Submit for approval → status: PENDING_APPROVAL |
| `req_get_status` | Poll status |
| `req_approve` | Auto-approve → status: APPROVED |

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
| `invoice_create` | Create invoice from confirmed GR → returns `inv_id` |
| `invoice_match` | Run 3-way match (PO vs GR vs Invoice, 2% tolerance) |
| `invoice_get_match_result` | Get per-line match deltas |
| `invoice_approve` | Approve invoice |
| `invoice_finalize` | Finalise → emits InvoicePaid event, P2P cycle COMPLETE |

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