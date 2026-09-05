"""Domain 2 — extract structured fields from messy invoice text.

A different SHAPE from ticket routing, which is what makes the "multiple
domains" claim real:

  ticket_routing      classification  metric: accuracy         output: a label
  invoice_extraction  extraction      metric: field-level acc  output: a JSON record

Scoring is per FIELD, not per document, so a record that gets four of five
fields right is not simply "wrong". That matters because it lets failures
cluster by field — and a per-field cluster is directly actionable ("dates are
wrong" is a fixable instruction; "extraction is bad" is not).

The documents are seeded with traps a small model reliably falls into:
  - subtotal, tax and total all present, so the largest number is not the total
  - "Total" appearing several times, only the last of which is payable
  - numeric dates that are genuinely ambiguous (05/06/2026) and resolvable ONLY
    by reading the locale off the currency: GBP/EUR/INR documents are
    day-first, USD documents are month-first
  - currency given as a symbol, a bare word, or implied by locale
  - genuinely absent fields, which must come back null rather than invented

That date rule is the centrepiece. It is never stated anywhere the agent can
read it, so the only route to a perfect score is for the improver to notice
that date errors correlate with currency and encode the rule itself.
"""

from __future__ import annotations

import json
import re

from agent_forge.runtime import run_agent
from agent_forge.spec import AgentSpec, RunTrace, ToolSpec

FIELDS = ["vendor", "invoice_number", "date", "total", "currency"]

# Deliberately a bare statement of intent, NOT a spec sheet. An earlier version
# of this goal spelled out ISO dates, null-for-missing, and "the final amount
# payable" — and round 0 immediately scored 0.98, leaving the improver nothing
# to do but damage a near-perfect spec. Track 1 asks the system to work from a
# goal and derive the rest from failures.
GOAL = (
    "Read this invoice or receipt and pull out the vendor, invoice number, date, "
    "total and currency. Return the result as JSON with those five keys."
)

TOOLS = [
    ToolSpec(
        "today",
        "Return today's date in ISO format. Useful only for resolving relative "
        "dates such as 'yesterday'; never use it to invent a missing date.",
    ),
]


def today(_: str = "") -> str:
    return "2026-09-05"


DOCS: list[dict] = [
    {
        "id": "i1",
        "text": "NORTHWIND SUPPLIES LTD\nInvoice INV-2291\nDated 14 March 2026\n"
                "Subtotal 1,200.00\nVAT 20% 240.00\nTotal Due GBP 1,440.00",
        "gold": {"vendor": "Northwind Supplies Ltd", "invoice_number": "INV-2291",
                 "date": "2026-03-14", "total": 1440.00, "currency": "GBP"},
    },
    {
        "id": "i2",
        "text": "Receipt from Cafe Mulberry\n#8823\n03/04/2026\n"
                "2x Flat White  9.00\nPastry 4.50\nTOTAL  €13.50",
        "gold": {"vendor": "Cafe Mulberry", "invoice_number": "8823",
                 "date": "2026-04-03", "total": 13.50, "currency": "EUR"},
    },
    {
        "id": "i3",
        "text": "TATA CLOUD SERVICES\nBill Ref: TCS/2026/0417\nBilling date: 2026-07-01\n"
                "Usage charges 84,500.00\nDiscount -4,500.00\nAmount payable Rs. 80,000.00",
        "gold": {"vendor": "Tata Cloud Services", "invoice_number": "TCS/2026/0417",
                 "date": "2026-07-01", "total": 80000.00, "currency": "INR"},
    },
    {
        "id": "i4",
        "text": "ACME TOOLS\nOrder confirmation\nPlaced Jan 9, 2026\n"
                "Items 320.00\nShipping 15.00\nGrand total $335.00\n"
                "(no invoice number issued yet)",
        "gold": {"vendor": "Acme Tools", "invoice_number": None,
                 "date": "2026-01-09", "total": 335.00, "currency": "USD"},
    },
    {
        "id": "i5",
        "text": "Helios Design Studio — statement\nRef HD-0042\n"
                "Issued 2026/11/30\nFee 5 000,00 EUR\nAlready paid 2 000,00 EUR\n"
                "Balance due 3 000,00 EUR",
        "gold": {"vendor": "Helios Design Studio", "invoice_number": "HD-0042",
                 "date": "2026-11-30", "total": 3000.00, "currency": "EUR"},
    },
    {
        "id": "i6",
        "text": "BLUE RIVER LOGISTICS\nINVOICE\nNo. BRL-77120\n"
                "Invoice date: 05-06-2026\n"
                "Freight 2,100.00\nFuel surcharge 180.00\nTOTAL USD 2,280.00",
        "gold": {"vendor": "Blue River Logistics", "invoice_number": "BRL-77120",
                 "date": "2026-05-06", "total": 2280.00, "currency": "USD"},
    },
    {
        "id": "i7",
        "text": "Sunrise Foods\nTax invoice 99017\n21.02.2026\n"
                "Net 640.00\nGST 9% 57.60\nRounding 0.40\nPayable SGD 698.00",
        "gold": {"vendor": "Sunrise Foods", "invoice_number": "99017",
                 "date": "2026-02-21", "total": 698.00, "currency": "SGD"},
    },
    {
        "id": "i8",
        "text": "QUANTA LABS\nProforma\nQL-2026-8\nDate not stated\n"
                "Consulting 12,000.00\nTotal 12,000.00 CHF",
        "gold": {"vendor": "Quanta Labs", "invoice_number": "QL-2026-8",
                 "date": None, "total": 12000.00, "currency": "CHF"},
    },
    {
        "id": "i9",
        "text": "receipt — corner store\n15 aug 2026\nmilk 60\nbread 45\nsum 105 rupees\n"
                "no bill number",
        "gold": {"vendor": "Corner Store", "invoice_number": None,
                 "date": "2026-08-15", "total": 105.00, "currency": "INR"},
    },
    {
        "id": "i10",
        "text": "MERIDIAN PUBLISHING\nInvoice number MP4471 / credit note CN0093\n"
                "Invoice dated 2026-10-08\nCharges 900.00\nCredit applied -150.00\n"
                "Net total: 750.00 AUD",
        "gold": {"vendor": "Meridian Publishing", "invoice_number": "MP4471",
                 "date": "2026-10-08", "total": 750.00, "currency": "AUD"},
    },
    {
        "id": "i11",
        "text": "STERLING & CO\nInvoice SC-1180\n06/07/2026\n"
                "Services 500.00\nTotal 500.00\nLate fee 25.00\n"
                "Total now due £525.00",
        "gold": {"vendor": "Sterling & Co", "invoice_number": "SC-1180",
                 "date": "2026-07-06", "total": 525.00, "currency": "GBP"},
    },
    {
        "id": "i12",
        "text": "PACIFIC HARDWARE INC\nInvoice PH-9034\n06/07/2026\n"
                "Goods 400.00\nTax 32.00\nTotal $432.00",
        "gold": {"vendor": "Pacific Hardware Inc", "invoice_number": "PH-9034",
                 "date": "2026-06-07", "total": 432.00, "currency": "USD"},
    },
    {
        "id": "i13",
        "text": "DELHI TEXTILES PVT LTD\nInv DT-556\n11/12/2026\n"
                "Fabric 22,000.00\nGST 18% 3,960.00\nTotal Rs 25,960.00",
        "gold": {"vendor": "Delhi Textiles Pvt Ltd", "invoice_number": "DT-556",
                 "date": "2026-12-11", "total": 25960.00, "currency": "INR"},
    },
    {
        "id": "i14",
        "text": "SUMMIT ANALYTICS LLC\nInvoice SA-2026-14\n01/02/2026\n"
                "Retainer 8,000.00\nTotal 8,000.00\nCredit -1,000.00\n"
                "Balance payable USD 7,000.00",
        "gold": {"vendor": "Summit Analytics Llc", "invoice_number": "SA-2026-14",
                 "date": "2026-01-02", "total": 7000.00, "currency": "USD"},
    },
    {
        "id": "i15",
        "text": "LE PETIT ATELIER\nFacture LPA-77\n09/10/2026\n"
                "Design 1 400,00\nTVA 280,00\nTotal a payer 1 680,00 €",
        "gold": {"vendor": "Le Petit Atelier", "invoice_number": "LPA-77",
                 "date": "2026-10-09", "total": 1680.00, "currency": "EUR"},
    },
]

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def _parse(output: str) -> dict | None:
    if not output:
        return None
    text = re.sub(r"^\s*```(?:json)?|```\s*$", "", output.strip(), flags=re.MULTILINE)
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        match = _JSON_BLOCK.search(text)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


def _norm(field: str, value):
    """Normalise before comparing so trivial formatting differences are not
    scored as extraction errors."""
    if value is None:
        return None
    if field == "total":
        if isinstance(value, str):
            cleaned = re.sub(r"[^\d.\-]", "", value.replace(",", ""))
            try:
                value = float(cleaned)
            except ValueError:
                return value
        try:
            return round(float(value), 2)
        except (TypeError, ValueError):
            return value
    if field == "currency":
        return str(value).strip().upper()
    if field in ("vendor", "invoice_number"):
        return re.sub(r"\s+", " ", str(value)).strip().lower()
    return str(value).strip()


class InvoiceExtractionDomain:
    name = "invoice_extraction"
    goal = GOAL
    tools = TOOLS

    def tasks(self) -> list[dict]:
        return DOCS

    def run(self, agent_spec: AgentSpec, task: dict) -> RunTrace:
        return run_agent(
            agent_spec,
            task_id=task["id"],
            task_input=task["text"],
            tool_impls={"today": today},
            response_format_hint="",
        )

    def score(self, traces: list[RunTrace]) -> tuple[dict[str, float], dict[str, int]]:
        by_id = {d["id"]: d for d in DOCS}
        total_fields = correct_fields = 0
        exact_records = errors = 0
        failure_modes: dict[str, int] = {}

        def bump(mode: str) -> None:
            failure_modes[mode] = failure_modes.get(mode, 0) + 1

        for tr in traces:
            gold = by_id[tr.task_id]["gold"]

            if tr.error:
                errors += 1
                bump("agent_crashed")
                total_fields += len(FIELDS)
                continue

            got = _parse(tr.output)
            if got is None:
                bump("output_was_not_valid_json")
                total_fields += len(FIELDS)
                continue

            record_ok = True
            for field in FIELDS:
                total_fields += 1
                want = _norm(field, gold[field])
                have = _norm(field, got.get(field))

                if want == have:
                    correct_fields += 1
                    continue

                record_ok = False
                if want is None and have is not None:
                    bump(f"invented_value_for_absent_{field}")
                elif have is None:
                    bump(f"missed_{field}")
                elif field == "date":
                    bump("date_wrong_or_not_iso_format")
                elif field == "total":
                    bump("total_wrong_likely_subtotal_or_pre_discount")
                elif field == "currency":
                    bump("currency_wrong_or_not_iso_code")
                else:
                    bump(f"{field}_mismatch")

            if record_ok:
                exact_records += 1

        n = len(traces) or 1
        metrics = {
            "accuracy": round(correct_fields / max(total_fields, 1), 4),  # field-level
            "exact_record_rate": round(exact_records / n, 4),
            "reliability": round((n - errors) / n, 4),
            "avg_latency_s": round(sum(t.latency_s for t in traces) / n, 3),
            "total_cost_usd": round(sum(t.cost_usd for t in traces), 6),
            "tool_calls": sum(len(t.tool_calls) for t in traces),
        }
        return metrics, failure_modes
