"""
EventLinkerAgent — groups the three payroll subtypes into one PayrollEvent per
company+period. This is the fusion step that makes the ~72% workforce-cost gap visible.
"""
from agents import event_linker
from models.document import DocType


def test_no_payroll_docs_returns_empty(doc):
    assert event_linker.run([doc(doc_type=DocType.INVOICE)]) == []


def test_links_three_subtypes_into_complete_event(doc):
    docs = [
        doc(source_file="bank.pdf", doc_type=DocType.BANK_CONFIRMATION,
            recipient_name="Acme", issue_date="2026-01-28", total_amount=10_000),
        doc(source_file="reg.pdf", doc_type=DocType.PAYROLL_REGISTER,
            recipient_name="Acme", issue_date="2026-01-31", total_amount=10_000),
        doc(source_file="s1.pdf", doc_type=DocType.PAYSLIP,
            recipient_name="Acme", issue_date="2026-01-31", total_amount=5_000),
    ]
    events = event_linker.run(docs)
    # same company, different days of same month → grouped by YYYY-MM... but the
    # group key uses each doc's own period; days differ only within Jan → 2026-01
    ev = next(e for e in events if e.is_complete)
    assert ev.company_name == "Acme"
    assert ev.bank_confirmation is not None
    assert ev.payroll_register is not None
    assert len(ev.payslips) == 1


def test_incomplete_event_when_only_bank(doc):
    events = event_linker.run([doc(doc_type=DocType.BANK_CONFIRMATION,
                                   recipient_name="Acme", total_amount=10_000)])
    assert len(events) == 1
    assert events[0].is_complete is False


def test_pick_one_prefers_highest_confidence(doc):
    docs = [
        doc(source_file="r1.pdf", doc_type=DocType.PAYROLL_REGISTER,
            recipient_name="Acme", issue_date="2026-01-31", confidence=0.6, total_amount=1),
        doc(source_file="r2.pdf", doc_type=DocType.PAYROLL_REGISTER,
            recipient_name="Acme", issue_date="2026-01-31", confidence=0.95, total_amount=2),
    ]
    ev = event_linker.run(docs)[0]
    assert ev.payroll_register.source_file == "r2.pdf"


def test_groups_separate_companies(doc):
    docs = [
        doc(source_file="a.pdf", doc_type=DocType.BANK_CONFIRMATION,
            recipient_name="Alpha", issue_date="2026-01-10", total_amount=1),
        doc(source_file="b.pdf", doc_type=DocType.BANK_CONFIRMATION,
            recipient_name="Beta", issue_date="2026-01-10", total_amount=2),
    ]
    events = event_linker.run(docs)
    assert {e.company_name for e in events} == {"Alpha", "Beta"}


def test_period_unknown_when_no_issue_date(doc):
    ev = event_linker.run([doc(doc_type=DocType.PAYSLIP, recipient_name="Acme",
                               issue_date=None, total_amount=5_000)])[0]
    assert ev.period == "unknown"


def test_period_from_partial_or_bad_date(doc):
    # non-ISO but length>=7 → first 7 chars used
    ev = event_linker.run([doc(doc_type=DocType.PAYSLIP, recipient_name="Acme",
                               issue_date="2026-01-XX", total_amount=1)])[0]
    assert ev.period == "2026-01"


def test_company_falls_back_to_vendor_name(doc):
    ev = event_linker.run([doc(doc_type=DocType.PAYSLIP, recipient_name=None,
                               vendor_name="VendorCo", issue_date="2026-01-15", total_amount=1)])[0]
    assert ev.company_name == "VendorCo"
