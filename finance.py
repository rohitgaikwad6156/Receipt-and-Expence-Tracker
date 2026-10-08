from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import csv
import io
import uuid

CATEGORIES = ("Food & Drinks", "Groceries", "Transport", "Shopping", "Bills", "Health", "Entertainment", "Travel", "Other")
CURRENCIES = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}

def to_minor(value):
    try:
        value = Decimal(str(value))
        if not value.is_finite() or value < 0:
            raise ValueError("Amount must be non-negative and finite")
        return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("Invalid amount") from exc

def money(minor, currency="INR"):
    return f"{CURRENCIES.get(currency, currency + ' ')}{Decimal(minor) / 100:,.2f}"

def make_expense(merchant, amount, spent_on=None, category="Other", source="Manual", notes="", items=None, currency="INR"):
    merchant = str(merchant).strip()
    if not merchant:
        raise ValueError("Merchant is required")
    minor = to_minor(amount)
    if minor <= 0:
        raise ValueError("Amount must be greater than zero")
    spent_on = spent_on or date.today()
    if isinstance(spent_on, str):
        spent_on = date.fromisoformat(spent_on)
    return {"id": str(uuid.uuid4()), "date": spent_on.isoformat(), "merchant": merchant[:120],
            "category": category if category in CATEGORIES else "Other", "amount_minor": minor,
            "source": source, "notes": str(notes)[:400], "items": items or [], "currency": currency}

def parse_receipt(raw, currency):
    if not isinstance(raw, dict):
        raise ValueError("Receipt was not readable")
    detected = str(raw.get("currency") or currency).upper().strip()
    if detected != currency:
        raise ValueError("Receipt currency differs from ledger; automatic conversion is disabled")
    if raw.get("total") is None:
        raise ValueError("Receipt total is unreadable; enter manually")
    total = to_minor(raw["total"])
    if total <= 0:
        raise ValueError("Total must be positive")
    items = []
    for item in raw.get("items") or []:
        if isinstance(item, dict) and item.get("amount") is not None:
            try:
                items.append({"name": str(item.get("name") or "Item")[:90], "amount_minor": to_minor(item["amount"])})
            except ValueError:
                continue
    try:
        spent = date.fromisoformat(raw["date"]) if raw.get("date") else None
    except (ValueError, TypeError):
        spent = None
    category = raw.get("category")
    return {"merchant": str(raw.get("merchant") or "Unknown merchant")[:120],
            "date": spent, "category": category if category in CATEGORIES else "Other",
            "amount_minor": total, "items": items}

def split_equal(total, people):
    if not people or len(set(people)) != len(people):
        raise ValueError("Enter distinct participants")
    base, remainder = divmod(total, len(people))
    return {person: base + (i < remainder) for i, person in enumerate(people)}

def split_by_item(total, items, assignments, people):
    if not items:
        raise ValueError("No itemized charges")
    shares = dict.fromkeys(people, 0)
    for i, item in enumerate(items):
        selected = assignments.get(i, [])
        if not selected or any(p not in shares for p in selected):
            raise ValueError("Assign every item to one or more participants")
        for person, amount in split_equal(item["amount_minor"], selected).items():
            shares[person] += amount
    adjustment = total - sum(shares.values())
    weights = {p: max(0, amount) for p, amount in shares.items()}
    weight_sum = sum(weights.values())
    if weight_sum:
        positive = abs(adjustment)
        base = {p: positive * weights[p] // weight_sum for p in people}
        rem = {p: positive * weights[p] % weight_sum for p in people}
        missing = positive - sum(base.values())
        for p in sorted(people, key=lambda p: (-rem[p], people.index(p)))[:missing]:
            base[p] += 1
        for p in people:
            shares[p] += base[p] if adjustment >= 0 else -base[p]
    else:
        for p, amount in split_equal(abs(adjustment), people).items():
            shares[p] += amount if adjustment >= 0 else -amount
    if any(x < 0 for x in shares.values()):
        raise ValueError("Negative share; use equal split")
    assert sum(shares.values()) == total
    return shares

def expense_csv(records):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Date", "Merchant", "Category", "Amount", "Currency", "Source", "Notes"])
    for r in records:
        def safe(value):
            value = str(value)
            return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value
        writer.writerow([r["date"], safe(r["merchant"]), r["category"], f'{r["amount_minor"] / 100:.2f}', r["currency"], r["source"], safe(r["notes"])])
    return out.getvalue()

def expense_summary(records, currency, name=""):
    lines = [f"ReceiptWise expense report for {name}", f"Total spent: {money(sum(r['amount_minor'] for r in records), currency)}", f"Expenses: {len(records)}", ""]
    for r in sorted(records, key=lambda r: r["date"], reverse=True):
        lines.append(f'{r["date"]} | {r["merchant"]} | {r["category"]} | {money(r["amount_minor"], currency)}')
    return "\n".join(lines)
