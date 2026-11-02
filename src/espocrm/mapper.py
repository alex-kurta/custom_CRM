"""
Fishbowl → EspoCRM field mapping (AGENTS.md §4).

Document actual mapping here; keep PII-safe, no secret logging.

Default maps (override after schema discovery):
  customer.name            → Account.name
  customer.accountNumber   → Account.accountNumber (if exists)
  customer.status / active → Account.type? + fishbowlId
  address (billing/shipping) → Account.billingAddress* / shippingAddress*
  part.num / description   → Product.sku / name / description, price
  so.num / status          → Opportunity or custom SalesOrder (future)
"""

from __future__ import annotations

from typing import Any


def _str(v: Any, default: str = "") -> str:
    if v is None:
        return default
    return str(v).strip()


def _first(d: dict, keys: list[str], default: Any = None) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return default


def _format_espo_datetime(v: Any) -> str | None:
    """Fishbowl datetime(6) → EspoCRM datetime 'YYYY-MM-DD HH:mm:ss' (no micros, no TZ)."""
    if v is None:
        return None
    # datetime object
    if hasattr(v, "strftime"):
        try:
            return v.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return str(v)[:19]
    s = str(v).strip()
    if not s:
        return None
    # handle '2020-08-14 08:55:13.229000' or ISO '2020-08-14T08:55:13.229000'
    # strip fractional seconds and TZ
    s = s.replace("T", " ")
    if "." in s:
        s = s.split(".")[0]
    # remove trailing Z or +00:00
    if s.endswith("Z"):
        s = s[:-1]
    if "+" in s:
        s = s.split("+")[0]
    # ensure length 19
    return s[:19] if len(s) >= 19 else s


# ---------------------------------------------------------------------------
# Customer → Account
# ---------------------------------------------------------------------------

def customer_to_account(customer: dict[str, Any], address: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Map Fishbowl customer row to EspoCRM Account payload.
    Required custom fields in EspoCRM: fishbowlId, fishbowlLastModified (create via admin UI if missing).
    """
    cid = _first(customer, ["id", "customerId", "customerID"], "")
    name = _first(customer, ["name", "customerName", "displayName"], f"Customer {cid}")
    account_number = _first(customer, ["number", "accountNumber", "num", "customerNum"], "")
    # Fishbowl customer may have def* fields; be permissive
    phone = _first(customer, ["phone", "mainPhone", "phoneNumber"], "")
    email = _first(customer, ["email", "mainEmail"], "")

    # EspoCRM Account has built-in fields: name, website, phoneNumber, email, billingAddress*, shippingAddress*
    # Custom fields discovered as cFishbowlId / cFishbowlLastModified (isCustom:true) via /Metadata
    payload: dict[str, Any] = {
        "name": _str(name),
        "cFishbowlId": str(cid),
        "fishbowlId": str(cid),  # keep alias for idempotent search fallback
    }
    if account_number:
        payload["accountNumber"] = _str(account_number)
    # Phone/email — EspoCRM API often expects phoneNumber/emailAddress (singular) as primary
    if phone:
        payload["phoneNumber"] = _str(phone)
    if email:
        payload["emailAddress"] = _str(email)

    # Fishbowl dateLastModified variants — format for EspoCRM (no micros)
    last_mod = _first(customer, ["dateLastModified", "lastModified", "dateModified", "modifiedDate"], None)
    fmt = _format_espo_datetime(last_mod)
    if fmt:
        payload["cFishbowlLastModified"] = fmt
        payload["fishbowlLastModified"] = fmt

    # Description / notes
    desc = _first(customer, ["note", "description", "memo"], "")
    if desc:
        payload["description"] = _str(desc)[:4000]

    # Address mapping — if address row provided
    if address:
        street = _first(address, ["street", "address1", "line1"], "")
        city = _first(address, ["city"], "")
        state = _first(address, ["state", "province"], "")
        postal = _first(address, ["zip", "zipCode", "postalCode"], "")
        country = _first(address, ["country"], "")
        # EspoCRM uses billingAddress* fields
        if street:
            payload["billingAddressStreet"] = _str(street)
        if city:
            payload["billingAddressCity"] = _str(city)
        if state:
            payload["billingAddressState"] = _str(state)
        if postal:
            payload["billingAddressPostalCode"] = _str(postal)
        if country:
            payload["billingAddressCountry"] = _str(country)

    return payload


# ---------------------------------------------------------------------------
# Vendor → Account (type Vendor) — optional, or separate entity
# ---------------------------------------------------------------------------

def vendor_to_account(vendor: dict[str, Any]) -> dict[str, Any]:
    vid = _first(vendor, ["id", "vendorId"], "")
    name = _first(vendor, ["name", "vendorName"], f"Vendor {vid}")
    payload: dict[str, Any] = {
        "name": _str(name),
        "cFishbowlId": f"vendor-{vid}",
        "fishbowlId": f"vendor-{vid}",
        "type": "Vendor",
    }
    last_mod = _first(vendor, ["dateLastModified", "lastModified"], None)
    fmt = _format_espo_datetime(last_mod)
    if fmt:
        payload["cFishbowlLastModified"] = fmt
        payload["fishbowlLastModified"] = fmt
    phone = _first(vendor, ["phone", "mainPhone"], "")
    if phone:
        payload["phoneNumber"] = _str(phone)
    return payload


# ---------------------------------------------------------------------------
# Part → Product
# ---------------------------------------------------------------------------

def part_to_product(part: dict[str, Any]) -> dict[str, Any]:
    pid = _first(part, ["id", "partId", "partID"], "")
    sku = _first(part, ["num", "partNum", "sku", "number"], str(pid))
    name = _first(part, ["description", "name", "partName"], str(sku))
    # Fishbowl part: description often is name; long description in details
    long_desc = _first(part, ["details", "longDescription", "memo"], "")

    payload: dict[str, Any] = {
        "name": _str(name)[:255] or _str(sku)[:255],
        "sku": _str(sku)[:100],
        "cFishbowlId": str(pid),
        "fishbowlId": str(pid),
    }
    if long_desc:
        payload["description"] = _str(long_desc)[:4000]

    # Pricing — Fishbowl part may have price fields: price, unitPrice, defaultPrice, salesPrice
    price = _first(part, ["price", "unitPrice", "defaultPrice", "salesPrice", "cost"], None)
    if price is not None:
        try:
            payload["price"] = float(price)
        except (TypeError, ValueError):
            pass

    # Quantity on hand — if joined via partinventory, but here just map if present
    qty = _first(part, ["qtyOnHand", "quantityOnHand", "onHand"], None)
    if qty is not None:
        try:
            payload["quantity"] = float(qty)
        except (TypeError, ValueError):
            pass

    last_mod = _first(part, ["dateLastModified", "lastModified"], None)
    fmt = _format_espo_datetime(last_mod)
    if fmt:
        payload["cFishbowlLastModified"] = fmt
        payload["fishbowlLastModified"] = fmt

    return payload


# ---------------------------------------------------------------------------
# Sales Order (sales_order) → Opportunity
# Source of truth: sales_order — grand total = totalPrice (most accurate)
#   so.id → Opportunity.cFishbowlId (Opportunity has only cFishbowlId, no LastModified)
#   so.num → Opportunity.name "SO {num}"
#   so.customerId → Account.cFishbowlId lookup → Opportunity.accountId
#   so.totalPrice → Opportunity.amount (fallback subTotal)
#   so.statusId → sostatus.name → Opportunity.stage (In Progress/Issued/Fulfilled etc.)
#   so.dateCreated/dateIssued → Opportunity.closeDate
# ---------------------------------------------------------------------------

# Fishbowl sostatus.id → EspoCRM Opportunity stage mapping (Espo default stages: Prospecting/Qualification/Proposal/Negotiation/Closed Won/Closed Lost)
_SOSTATUS_TO_STAGE = {
    10: "Proposal",        # Estimate
    20: "Qualification",   # Issued
    25: "Negotiation",     # In Progress — most common (~status 25)
    60: "Closed Won",      # Fulfilled
    85: "Closed Lost",     # Cancelled
    80: "Closed Lost",     # Voided
    70: "Closed Lost",     # Closed Short
    90: "Closed Lost",     # Expired
    95: "Closed Lost",     # Historical
}


def so_to_opportunity(so: dict[str, Any], account_id: str | None = None) -> dict[str, Any]:
    sid = _first(so, ["id", "soId"], "")
    num = _first(so, ["num", "soNum", "number"], str(sid))
    # Grand total: totalPrice is most accurate per user (sales_order source of truth)
    grand = _first(so, ["totalPrice", "grandTotal", "total", "amount"], None)
    if grand is None:
        grand = _first(so, ["subTotal"], 0)
    try:
        amount = float(grand or 0)
    except (TypeError, ValueError):
        amount = 0.0

    # Name: include billToName for readability if present
    bill_name = _str(so.get("billToName", ""))[:40]
    name = f"SO {num}" + (f" — {bill_name}" if bill_name else "")

    payload: dict[str, Any] = {
        "name": name[:255],
        "cFishbowlId": str(sid),
        "fishbowlId": str(sid),  # alias for search fallback
        "amount": amount,
    }
    # Customer linkage — caller may resolve customerId→Account.id via cFishbowlId
    if account_id:
        payload["accountId"] = account_id
    # Keep raw fishbowl customerId for debug/audit if account not yet resolved
    cid = so.get("customerId")
    if cid and not account_id:
        payload["description"] = f"Fishbowl customerId={cid} (account not yet linked)"

    # Status → stage
    status_name = _first(so, ["status", "statusName", "state"], "")
    status_id = so.get("statusId")
    if not status_name and status_id is not None:
        try:
            status_name = _SOSTATUS_TO_STAGE.get(int(status_id), "")
        except (TypeError, ValueError):
            status_name = ""
        if not status_name:
            status_name = "Qualification"
    if status_name:
        payload["stage"] = _str(status_name)[:100]
    else:
        payload["stage"] = "Qualification"

    # Close date: prefer dateIssued, else dateCreated, else dateFirstShip
    close = _first(so, ["dateIssued", "dateCreated", "dateFirstShip", "dateCompleted"], None)
    if close is not None:
        # Espo expects YYYY-MM-DD; pass through — API accepts datetime string
        payload["closeDate"] = str(close)[:10]

    # Audit details in description (expand if empty, append totals)
    details = []
    if so.get("subTotal") is not None:
        details.append(f"subTotal={so.get('subTotal')}")
    if so.get("totalTax") is not None:
        details.append(f"tax={so.get('totalTax')}")
    if so.get("customerPO"):
        details.append(f"PO={so.get('customerPO')}")
    if so.get("num"):
        details.append(f"SO#={so.get('num')}")
    if details:
        base_desc = _str(so.get("note", ""))[:2000]
        extra = " | ".join(details)
        payload["description"] = (base_desc + " | " + extra if base_desc else extra)[:4000]

    # Opportunity has no cFishbowlLastModified field (metadata confirms only cFishbowlId) — store in description if needed
    # Keep lastModified for idempotency check externally, but don't send unknown field
    # If custom field added later, uncomment:
    # last_mod = _first(so, ["dateLastModified", "lastModified"], None)
    # if last_mod is not None:
    #     payload["cFishbowlLastModified"] = str(last_mod)

    return payload


# ---------------------------------------------------------------------------
# Contact helper (Fishbowl customer contacts if any)
# ---------------------------------------------------------------------------

def contact_from_customer(customer: dict[str, Any]) -> dict[str, Any] | None:
    """
    If Fishbowl customer has contact fields inline, map to EspoCRM Contact.
    Returns None if no contact info present.
    """
    first = _first(customer, ["contactFirstName", "firstName", "contact"], "")
    last = _first(customer, ["contactLastName", "lastName"], "")
    email = _first(customer, ["contactEmail", "email"], "")
    if not (first or last or email):
        return None
    cid = _first(customer, ["id", "customerId"], "")
    return {
        "firstName": _str(first),
        "lastName": _str(last) or _str(customer.get("name", f"Customer {cid}")),
        "emailAddress": _str(email),
        "cFishbowlId": f"contact-{cid}",
        "fishbowlId": f"contact-{cid}",
        "accountName": _str(customer.get("name", "")),
    }
