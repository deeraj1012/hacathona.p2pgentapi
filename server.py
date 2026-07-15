"""
P2P Hackathon MCP Server — fully in-memory, no database required.
Covers: Catalog, Requisition, Order, Goods Receipt, Invoice agents.
"""

from mcp.server.fastmcp import FastMCP
from datetime import datetime, timezone
import uuid, random

mcp = FastMCP("p2p-hackathon")

# ── In-memory state ───────────────────────────────────────────────────────────

CATALOG = [
    {"item_id": "ITEM-001", "name": "HP Laptop 15.6\"", "category": "Laptop", "unit_price": 850.00, "supplier_id": "SUP-HP", "supplier_name": "HP India Pvt Ltd", "stock": 50},
    {"item_id": "ITEM-002", "name": "Dell Laptop 14\"", "category": "Laptop", "unit_price": 780.00, "supplier_id": "SUP-DELL", "supplier_name": "Dell Technologies", "stock": 30},
    {"item_id": "ITEM-003", "name": "Office Chair Ergonomic", "category": "Furniture", "unit_price": 220.00, "supplier_id": "SUP-OFC", "supplier_name": "OfficeMax India", "stock": 100},
    {"item_id": "ITEM-004", "name": "24\" Monitor Full HD", "category": "Monitor", "unit_price": 310.00, "supplier_id": "SUP-LG", "supplier_name": "LG Electronics", "stock": 40},
    {"item_id": "ITEM-005", "name": "Wireless Keyboard & Mouse Combo", "category": "Peripherals", "unit_price": 55.00, "supplier_id": "SUP-LOG", "supplier_name": "Logitech India", "stock": 200},
    {"item_id": "ITEM-006", "name": "USB-C Docking Station", "category": "Peripherals", "unit_price": 130.00, "supplier_id": "SUP-LOG", "supplier_name": "Logitech India", "stock": 75},
    {"item_id": "ITEM-007", "name": "A4 Paper Ream 500 Sheets", "category": "Stationery", "unit_price": 8.00, "supplier_id": "SUP-STN", "supplier_name": "Classmate Supplies", "stock": 500},
    {"item_id": "ITEM-008", "name": "Webcam HD 1080p", "category": "Peripherals", "unit_price": 75.00, "supplier_id": "SUP-LOG", "supplier_name": "Logitech India", "stock": 60},
]

CARTS: dict = {}       # cart_id -> cart dict
REQS: dict = {}        # req_id -> req dict
ORDERS: dict = {}      # po_id -> po dict
GRS: dict = {}         # gr_id -> gr dict
INVOICES: dict = {}    # inv_id -> invoice dict

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _id(prefix: str) -> str:
    return f"{prefix}-{str(uuid.uuid4())[:8].upper()}"

# ── CATALOG TOOLS ─────────────────────────────────────────────────────────────

@mcp.tool()
def catalog_search(query: str, category: str = None, max_price: float = None) -> dict:
    """Search the GEP catalog for items matching a keyword query."""
    q = query.lower()
    results = []
    for item in CATALOG:
        if q in item["name"].lower() or (category and category.lower() in item["category"].lower()):
            if max_price is None or item["unit_price"] <= max_price:
                results.append(item)
    if not results:
        # fuzzy: match any word
        words = q.split()
        for item in CATALOG:
            if any(w in item["name"].lower() or w in item["category"].lower() for w in words):
                if max_price is None or item["unit_price"] <= max_price:
                    if item not in results:
                        results.append(item)
    return {"results": results, "count": len(results)}


@mcp.tool()
def catalog_get_item(item_id: str) -> dict:
    """Get detailed information for a specific catalog item by item_id."""
    for item in CATALOG:
        if item["item_id"] == item_id:
            return {"item": item}
    return {"error": f"Item {item_id} not found"}


@mcp.tool()
def cart_create(session_id: str = None) -> dict:
    """Create a new empty shopping cart. Returns cart_id."""
    cart_id = _id("CART")
    CARTS[cart_id] = {
        "cart_id": cart_id,
        "session_id": session_id or "default",
        "lines": [],
        "status": "OPEN",
        "created_at": _now(),
    }
    return {"cart_id": cart_id, "status": "OPEN"}


@mcp.tool()
def cart_add_item(cart_id: str, item_id: str, quantity: int) -> dict:
    """Add an item and quantity to an existing cart."""
    if cart_id not in CARTS:
        return {"error": f"Cart {cart_id} not found"}
    item = next((i for i in CATALOG if i["item_id"] == item_id), None)
    if not item:
        return {"error": f"Item {item_id} not found in catalog"}
    cart = CARTS[cart_id]
    # update existing line or add new
    for line in cart["lines"]:
        if line["item_id"] == item_id:
            line["quantity"] += quantity
            line["line_total"] = line["quantity"] * line["unit_price"]
            break
    else:
        cart["lines"].append({
            "line_id": _id("LINE"),
            "item_id": item_id,
            "item_name": item["name"],
            "unit_price": item["unit_price"],
            "quantity": quantity,
            "line_total": quantity * item["unit_price"],
            "supplier_id": item["supplier_id"],
        })
    cart["grand_total"] = sum(l["line_total"] for l in cart["lines"])
    return {"cart_id": cart_id, "lines_count": len(cart["lines"]), "grand_total": cart["grand_total"]}


@mcp.tool()
def cart_view(cart_id: str) -> dict:
    """View the current contents and total of a cart."""
    if cart_id not in CARTS:
        return {"error": f"Cart {cart_id} not found"}
    cart = CARTS[cart_id]
    cart["grand_total"] = sum(l["line_total"] for l in cart["lines"])
    return {"cart": cart}


@mcp.tool()
def cart_flip(cart_id: str) -> dict:
    """Finalise/flip the cart — locks it and makes it ready for requisition."""
    if cart_id not in CARTS:
        return {"error": f"Cart {cart_id} not found"}
    cart = CARTS[cart_id]
    if not cart["lines"]:
        return {"error": "Cannot flip an empty cart"}
    cart["status"] = "FLIPPED"
    cart["flipped_at"] = _now()
    cart["grand_total"] = sum(l["line_total"] for l in cart["lines"])
    return {
        "cart_id": cart_id,
        "status": "FLIPPED",
        "lines": cart["lines"],
        "grand_total": cart["grand_total"],
        "flipped_at": cart["flipped_at"],
        "event": {"type": "CART_FLIPPED", "cart_id": cart_id},
    }


# ── REQUISITION TOOLS ─────────────────────────────────────────────────────────

@mcp.tool()
def req_create(cart_id: str) -> dict:
    """Create a new requisition from a flipped cart. Returns req_id."""
    if cart_id not in CARTS:
        return {"error": f"Cart {cart_id} not found"}
    cart = CARTS[cart_id]
    if cart["status"] != "FLIPPED":
        return {"error": f"Cart must be FLIPPED before creating a requisition (current: {cart['status']})"}
    req_id = _id("REQ")
    REQS[req_id] = {
        "req_id": req_id,
        "cart_id": cart_id,
        "lines": cart["lines"],
        "grand_total": cart.get("grand_total", 0),
        "status": "DRAFT",
        "cost_center": None,
        "gl_account": None,
        "deliver_to": None,
        "need_by": None,
        "created_at": _now(),
    }
    return {"req_id": req_id, "status": "DRAFT", "grand_total": REQS[req_id]["grand_total"]}


@mcp.tool()
def req_set_accounting(req_id: str, cost_center: str, gl_account: str) -> dict:
    """Attach cost centre and GL account codes to a requisition."""
    if req_id not in REQS:
        return {"error": f"Requisition {req_id} not found"}
    REQS[req_id]["cost_center"] = cost_center
    REQS[req_id]["gl_account"] = gl_account
    return {"req_id": req_id, "cost_center": cost_center, "gl_account": gl_account, "updated": True}


@mcp.tool()
def req_set_delivery(req_id: str, deliver_to: str, need_by: str = None) -> dict:
    """Attach delivery address and need-by date to a requisition."""
    if req_id not in REQS:
        return {"error": f"Requisition {req_id} not found"}
    REQS[req_id]["deliver_to"] = deliver_to
    REQS[req_id]["need_by"] = need_by
    return {"req_id": req_id, "deliver_to": deliver_to, "need_by": need_by, "updated": True}


@mcp.tool()
def req_submit(req_id: str) -> dict:
    """Submit a requisition into the approval workflow."""
    if req_id not in REQS:
        return {"error": f"Requisition {req_id} not found"}
    req = REQS[req_id]
    req["status"] = "PENDING_APPROVAL"
    req["submitted_at"] = _now()
    return {"req_id": req_id, "status": "PENDING_APPROVAL", "submitted_at": req["submitted_at"]}


@mcp.tool()
def req_get_status(req_id: str) -> dict:
    """Poll the current approval status of a requisition."""
    if req_id not in REQS:
        return {"error": f"Requisition {req_id} not found"}
    req = REQS[req_id]
    return {"req_id": req_id, "status": req["status"], "cost_center": req["cost_center"],
            "gl_account": req["gl_account"], "deliver_to": req["deliver_to"],
            "need_by": req["need_by"], "grand_total": req["grand_total"]}


@mcp.tool()
def req_approve(req_id: str) -> dict:
    """Approve the requisition (auto-approve for demo). Status becomes APPROVED."""
    if req_id not in REQS:
        return {"error": f"Requisition {req_id} not found"}
    req = REQS[req_id]
    req["status"] = "APPROVED"
    req["approved_at"] = _now()
    return {
        "req_id": req_id,
        "status": "APPROVED",
        "approved_at": req["approved_at"],
        "lines": req["lines"],
        "grand_total": req["grand_total"],
    }


# ── ORDER TOOLS ───────────────────────────────────────────────────────────────

@mcp.tool()
def order_create(req_id: str) -> dict:
    """Create a Purchase Order from an approved requisition. Returns po_id."""
    if req_id not in REQS:
        return {"error": f"Requisition {req_id} not found"}
    req = REQS[req_id]
    if req["status"] != "APPROVED":
        return {"error": f"Requisition must be APPROVED (current: {req['status']})"}
    po_id = _id("PO")
    # Group lines by supplier
    supplier_id = req["lines"][0]["supplier_id"] if req["lines"] else "SUP-UNKNOWN"
    ORDERS[po_id] = {
        "po_id": po_id,
        "req_id": req_id,
        "supplier_id": supplier_id,
        "lines": req["lines"],
        "grand_total": req["grand_total"],
        "deliver_to": req["deliver_to"],
        "need_by": req["need_by"],
        "status": "DRAFT",
        "created_at": _now(),
    }
    return {"po_id": po_id, "status": "DRAFT", "supplier_id": supplier_id, "grand_total": req["grand_total"]}


@mcp.tool()
def order_get(po_id: str) -> dict:
    """Get full details of a Purchase Order."""
    if po_id not in ORDERS:
        return {"error": f"PO {po_id} not found"}
    return {"order": ORDERS[po_id]}


@mcp.tool()
def order_finalize(po_id: str) -> dict:
    """Lock and issue the PO to the supplier. Status becomes ISSUED."""
    if po_id not in ORDERS:
        return {"error": f"PO {po_id} not found"}
    po = ORDERS[po_id]
    po["status"] = "ISSUED"
    po["issued_at"] = _now()
    return {
        "po_id": po_id,
        "status": "ISSUED",
        "issued_at": po["issued_at"],
        "supplier_id": po["supplier_id"],
        "lines": po["lines"],
        "grand_total": po["grand_total"],
    }


@mcp.tool()
def order_get_status(po_id: str) -> dict:
    """Check the current status of a Purchase Order."""
    if po_id not in ORDERS:
        return {"error": f"PO {po_id} not found"}
    po = ORDERS[po_id]
    return {"po_id": po_id, "status": po["status"], "supplier_id": po["supplier_id"],
            "grand_total": po["grand_total"], "issued_at": po.get("issued_at")}


# ── GOODS RECEIPT TOOLS ───────────────────────────────────────────────────────

@mcp.tool()
def gr_create(po_id: str) -> dict:
    """Create a Goods Receipt shell from an issued PO. Returns gr_id."""
    if po_id not in ORDERS:
        return {"error": f"PO {po_id} not found"}
    po = ORDERS[po_id]
    if po["status"] != "ISSUED":
        return {"error": f"PO must be ISSUED (current: {po['status']})"}
    gr_id = _id("GR")
    GRS[gr_id] = {
        "gr_id": gr_id,
        "po_id": po_id,
        "lines": [
            {
                "po_line_id": line["line_id"],
                "item_id": line["item_id"],
                "item_name": line["item_name"],
                "qty_ordered": line["quantity"],
                "unit_price": line["unit_price"],
                "qty_received": None,
            }
            for line in po["lines"]
        ],
        "status": "OPEN",
        "created_at": _now(),
    }
    return {"gr_id": gr_id, "po_id": po_id, "status": "OPEN", "lines_count": len(GRS[gr_id]["lines"])}


@mcp.tool()
def gr_record(gr_id: str, receipts: list) -> dict:
    """
    Record received quantities for GR lines.
    receipts: list of {po_line_id, qty_received}
    """
    if gr_id not in GRS:
        return {"error": f"GR {gr_id} not found"}
    gr = GRS[gr_id]
    receipt_map = {r["po_line_id"]: r["qty_received"] for r in receipts}
    for line in gr["lines"]:
        if line["po_line_id"] in receipt_map:
            line["qty_received"] = receipt_map[line["po_line_id"]]
    gr["status"] = "RECORDED"
    return {"gr_id": gr_id, "status": "RECORDED", "lines": gr["lines"]}


@mcp.tool()
def gr_confirm(gr_id: str) -> dict:
    """Confirm receipt and run discrepancy check against ordered quantities."""
    if gr_id not in GRS:
        return {"error": f"GR {gr_id} not found"}
    gr = GRS[gr_id]
    mismatches = []
    lines_out = []
    total_received_value = 0.0
    for line in gr["lines"]:
        qty_recv = line["qty_received"] if line["qty_received"] is not None else 0
        qty_ord = line["qty_ordered"]
        diff = qty_recv - qty_ord
        discrepancy = None if diff == 0 else f"SHORT: {diff}" if diff < 0 else f"OVER: +{diff}"
        line_val = qty_recv * line["unit_price"]
        total_received_value += line_val
        lines_out.append({
            "po_line_id": line["po_line_id"],
            "item_name": line["item_name"],
            "qty_ordered": qty_ord,
            "qty_received": qty_recv,
            "discrepancy": discrepancy,
            "line_value": line_val,
        })
        if discrepancy:
            mismatches.append({"item_name": line["item_name"], "qty_ordered": qty_ord,
                                "qty_received": qty_recv, "shortfall": diff})
    gr_status = "CONFIRMED" if not mismatches else "EXCEPTION"
    gr["status"] = gr_status
    gr["confirmed_at"] = _now()
    gr["lines_out"] = lines_out
    gr["mismatches"] = mismatches
    gr["total_received_value"] = total_received_value
    return {
        "gr_id": gr_id,
        "po_id": gr["po_id"],
        "gr_status": gr_status,
        "lines_received": lines_out,
        "total_received_value": total_received_value,
        "mismatches": mismatches,
        "received_at": gr["confirmed_at"],
    }


@mcp.tool()
def gr_get(gr_id: str) -> dict:
    """Get full Goods Receipt details."""
    if gr_id not in GRS:
        return {"error": f"GR {gr_id} not found"}
    return {"gr": GRS[gr_id]}


# ── INVOICE TOOLS ─────────────────────────────────────────────────────────────

@mcp.tool()
def invoice_create(gr_id: str) -> dict:
    """Create an invoice from a confirmed Goods Receipt. Returns inv_id."""
    if gr_id not in GRS:
        return {"error": f"GR {gr_id} not found"}
    gr = GRS[gr_id]
    if gr["status"] not in ("CONFIRMED", "EXCEPTION"):
        return {"error": f"GR must be CONFIRMED or EXCEPTION (current: {gr['status']})"}
    po_id = gr["po_id"]
    po = ORDERS.get(po_id, {})
    inv_id = _id("INV")
    inv_number = f"INV-2024-{random.randint(1000, 9999)}"
    lines = []
    for line in gr.get("lines_out", gr["lines"]):
        qty = line.get("qty_received") or line.get("qty_ordered", 0)
        price = line.get("unit_price", 0)
        lines.append({
            "po_line_id": line.get("po_line_id"),
            "item_name": line.get("item_name"),
            "qty_invoiced": qty,
            "unit_price": price,
            "line_total": qty * price,
        })
    INVOICES[inv_id] = {
        "inv_id": inv_id,
        "inv_number": inv_number,
        "gr_id": gr_id,
        "po_id": po_id,
        "lines": lines,
        "inv_total": sum(l["line_total"] for l in lines),
        "match_status": None,
        "match_result": None,
        "status": "DRAFT",
        "created_at": _now(),
    }
    return {"inv_id": inv_id, "inv_number": inv_number, "status": "DRAFT",
            "inv_total": INVOICES[inv_id]["inv_total"]}


@mcp.tool()
def invoice_match(inv_id: str) -> dict:
    """Run 3-way match: PO vs GR vs Invoice. Tolerance within 2%."""
    if inv_id not in INVOICES:
        return {"error": f"Invoice {inv_id} not found"}
    inv = INVOICES[inv_id]
    gr = GRS.get(inv["gr_id"], {})
    po = ORDERS.get(inv["po_id"], {})

    po_line_map = {l["line_id"]: l for l in po.get("lines", [])}
    gr_line_map = {l.get("po_line_id"): l for l in gr.get("lines_out", gr.get("lines", []))}

    match_lines = []
    overall = "MATCHED"
    for inv_line in inv["lines"]:
        po_lid = inv_line["po_line_id"]
        po_line = po_line_map.get(po_lid, {})
        gr_line = gr_line_map.get(po_lid, {})

        po_qty = po_line.get("quantity", inv_line["qty_invoiced"])
        po_price = po_line.get("unit_price", inv_line["unit_price"])
        po_total = po_qty * po_price

        gr_qty = gr_line.get("qty_received", inv_line["qty_invoiced"])
        inv_total_line = inv_line["qty_invoiced"] * inv_line["unit_price"]

        delta_pct = abs(inv_total_line - po_total) / po_total * 100 if po_total else 0
        line_status = "MATCHED" if delta_pct <= 2.0 else "MISMATCH"
        if line_status == "MISMATCH":
            overall = "MISMATCH"

        match_lines.append({
            "item_name": inv_line["item_name"],
            "po_qty": po_qty, "po_price": po_price, "po_total": po_total,
            "gr_qty": gr_qty,
            "inv_qty": inv_line["qty_invoiced"], "inv_price": inv_line["unit_price"],
            "inv_total": inv_total_line,
            "delta_pct": round(delta_pct, 2),
            "status": line_status,
        })

    match_result = {"overall": overall, "lines": match_lines}
    inv["match_status"] = overall
    inv["match_result"] = match_result
    inv["status"] = "MATCHED" if overall == "MATCHED" else "MISMATCH"
    return {"inv_id": inv_id, "match_status": overall, "match_result": match_result}


@mcp.tool()
def invoice_get_match_result(inv_id: str) -> dict:
    """Get per-line match results with exact deltas for an invoice."""
    if inv_id not in INVOICES:
        return {"error": f"Invoice {inv_id} not found"}
    inv = INVOICES[inv_id]
    if not inv["match_result"]:
        return {"error": "Match not yet run — call invoice_match first"}
    return {"inv_id": inv_id, "inv_number": inv["inv_number"],
            "match_status": inv["match_status"], "match_result": inv["match_result"]}


@mcp.tool()
def invoice_approve(inv_id: str) -> dict:
    """Approve the invoice. MATCHED = auto-approved; MISMATCH = flagged but approved."""
    if inv_id not in INVOICES:
        return {"error": f"Invoice {inv_id} not found"}
    inv = INVOICES[inv_id]
    inv["status"] = "APPROVED"
    inv["approved_at"] = _now()
    note = "Auto-approved: 3-way match passed" if inv["match_status"] == "MATCHED" \
        else "Approved with flag: match discrepancy noted"
    return {"inv_id": inv_id, "status": "APPROVED", "approved_at": inv["approved_at"],
            "match_status": inv["match_status"], "note": note}


@mcp.tool()
def invoice_finalize(inv_id: str) -> dict:
    """Finalise invoice and emit InvoicePaid event — completes the P2P cycle."""
    if inv_id not in INVOICES:
        return {"error": f"Invoice {inv_id} not found"}
    inv = INVOICES[inv_id]
    if inv["status"] != "APPROVED":
        return {"error": f"Invoice must be APPROVED (current: {inv['status']})"}
    inv["status"] = "PAID"
    inv["paid_at"] = _now()
    return {
        "inv_id": inv_id,
        "inv_number": inv["inv_number"],
        "status": "PAID",
        "paid_at": inv["paid_at"],
        "inv_total": inv["inv_total"],
        "po_id": inv["po_id"],
        "gr_id": inv["gr_id"],
        "event": {"type": "INVOICE_PAID", "inv_id": inv_id, "amount": inv["inv_total"]},
        "p2p_cycle": "COMPLETE",
    }


# ── Health check (for Render / load balancers) ────────────────────────────────

@mcp.custom_route("/mcp-health", methods=["GET"])
async def health(request):
    from starlette.responses import JSONResponse
    return JSONResponse({"status": "ok", "tools": 25, "service": "p2p-hackathon-mcp"})


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", default="streamable-http", choices=["stdio", "sse", "streamable-http"])
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        # Serve MCP at root path so QiStudio can find it at base URL
        mcp.settings.streamable_http_path = "/"
        mcp.settings.sse_path = "/sse"
        mcp.settings.message_path = "/messages/"
        from mcp.server.fastmcp.server import TransportSecuritySettings
        mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
            allowed_hosts=["*"],
            allowed_origins=["*"],
        )
        mcp.run(transport=args.transport)
