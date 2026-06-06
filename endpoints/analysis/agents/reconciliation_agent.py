"""
ReconciliationAgent — cross-checks vendor invoices against vendor statements.

Single responsibility: for each vendor account_statement, compare the
document entries it references against the invoice documents we actually
have in the system. Surface missing documents and totals discrepancies.

This powers the Suppliers page: "Their statement says 4 invoices — we
only have 3 uploaded. Find the missing one."

Account statements are NOT included in P&L or cash flow; they are used
solely as an external reference for reconciliation.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from models.financial import ExtractedDoc, StatementEntry, VendorReconciliation

log = logging.getLogger("archon.reconciliation_agent")


def run(period: str, docs: list[ExtractedDoc]) -> list[VendorReconciliation]:
    statements = [d for d in docs if d.doc_type == "account_statement"]
    if not statements:
        log.info("No account statements found for period %s — skipping reconciliation", period)
        return []

    invoices = [d for d in docs if d.doc_type not in ("account_statement",)]

    # Build invoice lookup: vendor → invoice_number → doc
    vendor_invoices: dict[str, list[ExtractedDoc]] = defaultdict(list)
    for inv in invoices:
        key = _vendor_key(inv)
        vendor_invoices[key].append(inv)

    reconciliations: list[VendorReconciliation] = []
    for stmt in statements:
        rec = _reconcile(period, stmt, vendor_invoices.get(_vendor_key(stmt), []))
        reconciliations.append(rec)
        log.info(
            "Reconciliation vendor=%s reconciled=%s discrepancy=%.2f missing=%d",
            rec.vendor_name, rec.reconciled, rec.discrepancy_eur, len(rec.missing_in_system),
        )

    return reconciliations


def _reconcile(
    period: str,
    stmt: ExtractedDoc,
    our_invoices: list[ExtractedDoc],
) -> VendorReconciliation:
    # Parse statement entries (stored as raw dicts from extraction)
    stmt_entries: list[StatementEntry] = []
    raw_entries = stmt.statement_entries or []
    for e in raw_entries:
        try:
            stmt_entries.append(StatementEntry(
                document_number=e.get("document_number") or e.get("doc_number"),
                posting_date=e.get("posting_date") or e.get("date"),
                due_date=e.get("due_date"),
                original_amount=float(e.get("original_amount") or e.get("amount") or 0),
                remaining_amount=float(e.get("remaining_amount") or e.get("balance") or 0),
                is_overdue=bool(e.get("is_overdue") or e.get("overdue")),
            ))
        except Exception as exc:
            log.warning("Skipping malformed statement entry: %s", exc)

    stmt_doc_numbers = {e.document_number for e in stmt_entries if e.document_number}
    our_invoice_numbers = {inv.invoice_number for inv in our_invoices if inv.invoice_number}
    our_total = sum(inv.total_amount for inv in our_invoices)

    missing_in_system = sorted(stmt_doc_numbers - our_invoice_numbers)
    unmatched_uploads = sorted(our_invoice_numbers - stmt_doc_numbers)

    reconciled = len(missing_in_system) == 0
    discrepancy = (stmt.statement_balance or 0) - our_total

    return VendorReconciliation(
        vendor_name=stmt.vendor_name or "Unknown Vendor",
        vendor_tax_id=stmt.vendor_tax_id,
        period=period,
        statement_balance=stmt.statement_balance,
        statement_overdue=stmt.statement_overdue,
        statement_entries=stmt_entries,
        uploaded_invoices=sorted(our_invoice_numbers),
        uploaded_total=round(our_total, 2),
        missing_in_system=missing_in_system,
        unmatched_uploads=unmatched_uploads,
        reconciled=reconciled,
        discrepancy_eur=round(discrepancy, 2),
    )


def _vendor_key(doc: ExtractedDoc) -> str:
    return (doc.vendor_tax_id or doc.vendor_name or "").strip().lower()
