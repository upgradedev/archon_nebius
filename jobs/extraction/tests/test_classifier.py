"""
Extraction ClassifierAgent — deterministic keyword refinement of doc_type.
Only UNKNOWN/PAYROLL docs are reclassified.

FINDING (documented by test_greek_accented_text_is_not_matched): `_search_text`
normalises via NFD + `.encode("ascii", "ignore")`, which DROPS every non-ASCII
character — including all Greek letters. So the Greek entries in the keyword
sets are effectively dead; only the ASCII keywords ("payroll register",
"social security", "payslip", "batch payment", ...) and ASCII vendor names
("eurobank") match.
These tests therefore assert the real (ASCII-only) behaviour.
"""
from agents import classifier
from models.document import DocType


def test_bank_confirmation_from_ascii_keyword(doc):
    out = classifier.run([doc(doc_type=DocType.UNKNOWN, notes="Monthly batch payment confirmation")])
    assert out[0].doc_type == DocType.BANK_CONFIRMATION


def test_bank_confirmation_from_vendor_name(doc):
    out = classifier.run([doc(doc_type=DocType.UNKNOWN, vendor_name="Eurobank", notes="transfer")])
    assert out[0].doc_type == DocType.BANK_CONFIRMATION


def test_register_from_social_security_keyword(doc):
    out = classifier.run([doc(doc_type=DocType.PAYROLL, notes="employer social security contributions")])
    assert out[0].doc_type == DocType.PAYROLL_REGISTER


def test_payslip_keyword(doc):
    out = classifier.run([doc(doc_type=DocType.UNKNOWN, notes="employee pay slip for January")])
    assert out[0].doc_type == DocType.PAYSLIP


def test_generic_payroll_kept_when_subtype_indeterminate(doc):
    out = classifier.run([doc(doc_type=DocType.UNKNOWN, notes="monthly salary run")])
    assert out[0].doc_type == DocType.PAYROLL


def test_sales_keyword(doc):
    out = classifier.run([doc(doc_type=DocType.UNKNOWN, notes="this is a sales invoice")])
    assert out[0].doc_type == DocType.SALES


def test_no_keyword_stays_unknown(doc):
    out = classifier.run([doc(doc_type=DocType.UNKNOWN, notes="random text")])
    assert out[0].doc_type == DocType.UNKNOWN


def test_greek_accented_text_is_not_matched(doc):
    # Greek-only notes are stripped to whitespace by the ascii-ignore normaliser,
    # so no Greek keyword can fire. Documents the latent limitation.
    out = classifier.run([doc(doc_type=DocType.UNKNOWN, notes="Μισθοδοτική κατάσταση εργοδότη")])
    assert out[0].doc_type == DocType.UNKNOWN


def test_already_typed_docs_not_touched(doc):
    out = classifier.run([doc(doc_type=DocType.INVOICE, notes="payroll register social security")])
    assert out[0].doc_type == DocType.INVOICE
