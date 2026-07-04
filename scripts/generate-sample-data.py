"""
Generate synthetic sample documents for local development and CI testing.

Covers all Archon document types:
  invoice, payroll_register, bank_confirmation, payslip, account_statement

All entities are fictional and locale-neutral. Output goes to
sample-data/generated/ (gitignored — the script is committed, the PDFs are not).

Usage:
    pip install reportlab
    python scripts/generate-sample-data.py
"""

from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

OUT = Path(__file__).parent.parent / "sample-data" / "generated"
W, H = A4


def _c(filename: str) -> canvas.Canvas:
    OUT.mkdir(parents=True, exist_ok=True)
    return canvas.Canvas(str(OUT / filename), pagesize=A4)


def t(c, x, y, s, size=10, bold=False):
    c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    c.drawString(x * cm, H - y * cm, s)


def ln(c, x1, y1, x2, y2):
    c.line(x1 * cm, H - y1 * cm, x2 * cm, H - y2 * cm)


# ── 1. Toll / motorway services invoice ──────────────────────────────────────
def gen_toll_invoice():
    c = _c("toll_invoice_202601.pdf")
    t(c, 2, 2, "Meridian Tollways Ltd", 14, bold=True)
    t(c, 2, 2.9, "Tax ID: 094506571  |  Tax Office: Central")
    t(c, 2, 3.7, "12 Riverside Avenue, Metro City")
    t(c, 2, 5.2, "SERVICES INVOICE", 13, bold=True)
    t(c, 2, 6.1, "Invoice No: TOLL-202601-0042")
    t(c, 2, 6.9, "Issue Date: 31/01/2026")
    t(c, 2, 7.7, "Due Date:   14/02/2026")
    t(c, 2, 9, "CUSTOMER:", bold=True)
    t(c, 2, 9.8, "Northwind Foods Ltd  |  Tax ID: 801234567")
    t(c, 2, 10.6, "115 Central Boulevard, Metro City")
    ln(c, 2, 11.5, 19, 11.5)
    t(c, 2, 12.2, "DESCRIPTION", bold=True)
    t(c, 15, 12.2, "AMOUNT (€)", bold=True)
    ln(c, 2, 12.7, 19, 12.7)
    t(c, 2, 13.4, "Toll charges January 2026 — motorway network")
    t(c, 15, 13.4, "85,40")
    ln(c, 2, 14.5, 19, 14.5)
    t(c, 2, 15.2, "Net Amount:")
    t(c, 15, 15.2, "68,87")
    t(c, 2, 16.0, "VAT 24%:")
    t(c, 15, 16.0, "16,53")
    t(c, 2, 16.8, "TOTAL:", bold=True)
    t(c, 15, 16.8, "85,40", bold=True)
    c.save()
    print("  + toll_invoice_202601.pdf")


# ── 2. Anthropic SaaS invoice (USD, reverse charge) ───────────────────────────
def gen_anthropic():
    c = _c("anthropic_invoice_202601.pdf")
    t(c, 2, 2, "Anthropic, PBC", 14, bold=True)
    t(c, 2, 2.9, "548 Market St PMB 90375, San Francisco CA 94104, USA")
    t(c, 12, 2, "INVOICE", 16, bold=True)
    t(c, 12, 2.9, "Invoice #: INV-BF69A412-0042")
    t(c, 12, 3.7, "Date: January 31, 2026")
    t(c, 12, 4.5, "Due: February 14, 2026")
    t(c, 2, 5.5, "Bill To:", bold=True)
    t(c, 2, 6.3, "Northwind Foods Ltd  |  VAT: 801234567")
    t(c, 2, 7.1, "Metro City")
    ln(c, 2, 8, 19, 8)
    t(c, 2, 8.7, "DESCRIPTION", bold=True)
    t(c, 15, 8.7, "AMOUNT", bold=True)
    ln(c, 2, 9.1, 19, 9.1)
    t(c, 2, 9.8, "Claude API usage — January 2026")
    t(c, 15, 9.8, "USD 312.44")
    t(c, 2, 10.6, "  claude-opus-4: 1.2M tokens in / 0.3M out")
    t(c, 2, 11.4, "  claude-sonnet-4: 8.1M tokens in / 2.1M out")
    ln(c, 2, 12.2, 19, 12.2)
    t(c, 2, 12.9, "Subtotal:")
    t(c, 15, 12.9, "USD 312.44")
    t(c, 2, 13.7, "VAT: 0.00  (Reverse Charge — B2B cross-border)")
    t(c, 2, 14.5, "TOTAL:", bold=True)
    t(c, 15, 14.5, "USD 312.44", bold=True)
    t(c, 2, 15.5, "EUR equivalent at rate 1.0412:  EUR 300.07")
    c.save()
    print("  + anthropic_invoice_202601.pdf")


# ── 3. AWS cloud invoice (USD) ────────────────────────────────────────────────
def gen_aws():
    c = _c("aws_invoice_202601.pdf")
    t(c, 2, 2, "Amazon Web Services EMEA SARL", 13, bold=True)
    t(c, 2, 2.9, "38 Avenue John F. Kennedy, L-1855 Luxembourg  |  VAT: LU26859887")
    t(c, 12, 2, "AWS Invoice", 14, bold=True)
    t(c, 12, 2.9, "Invoice ID: EUIN26-99001")
    t(c, 12, 3.7, "Invoice Date: 2026-02-01")
    t(c, 2, 5, "Billed To:", bold=True)
    t(c, 2, 5.8, "Northwind Foods Ltd  |  VAT: 801234567")
    ln(c, 2, 7, 19, 7)
    t(c, 2, 7.7, "Service", bold=True)
    t(c, 15, 7.7, "Amount (USD)", bold=True)
    ln(c, 2, 8.1, 19, 8.1)
    t(c, 2, 8.8, "Amazon EC2")
    t(c, 15, 8.8, "156.78")
    t(c, 2, 9.6, "Amazon S3")
    t(c, 15, 9.6, "12.34")
    t(c, 2, 10.4, "Amazon RDS")
    t(c, 15, 10.4, "87.50")
    ln(c, 2, 11.2, 19, 11.2)
    t(c, 2, 11.9, "Total (USD):", bold=True)
    t(c, 15, 11.9, "256.62", bold=True)
    t(c, 2, 12.7, "EUR amount (rate 1.0412):  EUR 246.48")
    t(c, 2, 13.5, "VAT: 0.00  (Reverse Charge — B2B cross-border)")
    c.save()
    print("  + aws_invoice_202601.pdf")


# ── 4. Payroll register ───────────────────────────────────────────────────────
def gen_payroll_register():
    c = _c("payroll_register_202601.pdf")
    t(c, 2, 2, "Northwind Foods Ltd", 14, bold=True)
    t(c, 2, 2.9, "Tax ID: 801234567  |  Reg No: 12345/01/2021")
    t(c, 2, 4.5, "PAYROLL REGISTER — JANUARY 2026", 13, bold=True)
    t(c, 2, 5.4, "Period: 01/01/2026 – 31/01/2026  |  Pay date: 31/01/2026")
    ln(c, 2, 6.5, 19, 6.5)
    t(c, 2, 7.2, "EMPLOYEE / CODE", bold=True)
    t(c, 9, 7.2, "GROSS", bold=True)
    t(c, 12, 7.2, "NET", bold=True)
    t(c, 15.5, 7.2, "EMPLOYER COST", bold=True)
    ln(c, 2, 7.7, 19, 7.7)
    t(c, 2, 8.4, "Anders Meyer  EMP-001")
    t(c, 9, 8.4, "1.800,00")
    t(c, 12, 8.4, "1.312,44")
    t(c, 15.5, 8.4, "2.268,00")
    t(c, 2, 9.2, "Maria Silva  EMP-002")
    t(c, 9, 9.2, "1.500,00")
    t(c, 12, 9.2, "1.090,50")
    t(c, 15.5, 9.2, "1.890,00")
    t(c, 2, 10.0, "Diego Rossi  EMP-003")
    t(c, 9, 10.0, "2.200,00")
    t(c, 12, 10.0, "1.591,80")
    t(c, 15.5, 10.0, "2.772,00")
    ln(c, 2, 10.8, 19, 10.8)
    t(c, 2, 11.5, "TOTALS  (3 employees):", bold=True)
    t(c, 9, 11.5, "5.500,00", bold=True)
    t(c, 12, 11.5, "3.994,74", bold=True)
    t(c, 15.5, 11.5, "6.930,00", bold=True)
    t(c, 2, 13.0, "Deductions breakdown:")
    t(c, 2, 13.8, "  Employee social security (16%): 880,00")
    t(c, 2, 14.6, "  Employer social security (26%): 1.430,00")
    t(c, 2, 15.4, "  Income tax withheld: 625,26")
    t(c, 2, 17.0, "Payroll Officer: A. Meyer", bold=True)
    c.save()
    print("  + payroll_register_202601.pdf")


# ── 5. Bank payroll confirmation ──────────────────────────────────────────────
def gen_bank_confirmation():
    c = _c("bank_confirmation_202601.pdf")
    t(c, 2, 2, "ZENITH BANK", 14, bold=True)
    t(c, 2, 2.9, "BATCH PAYROLL PAYMENT CONFIRMATION", 12, bold=True)
    ln(c, 2, 4, 19, 4)
    t(c, 2, 4.8, "Company:  Northwind Foods Ltd  |  Tax ID: 801234567")
    t(c, 2, 5.6, "Debit Account:  ****-0000-0001")
    t(c, 2, 6.4, "Execution Date: 31/01/2026")
    t(c, 2, 7.2, "Reference: PAYROLL-202601-REF")
    ln(c, 2, 8.2, 19, 8.2)
    t(c, 2, 8.9, "BENEFICIARY", bold=True)
    t(c, 10, 8.9, "ACCOUNT", bold=True)
    t(c, 16, 8.9, "AMOUNT (€)", bold=True)
    ln(c, 2, 9.3, 19, 9.3)
    t(c, 2, 10.0, "Anders Meyer")
    t(c, 10, 10.0, "****...0001")
    t(c, 16, 10.0, "1.312,44")
    t(c, 2, 10.8, "Maria Silva")
    t(c, 10, 10.8, "****...0002")
    t(c, 16, 10.8, "1.090,50")
    t(c, 2, 11.6, "Diego Rossi")
    t(c, 10, 11.6, "****...0003")
    t(c, 16, 11.6, "1.591,80")
    ln(c, 2, 12.4, 19, 12.4)
    t(c, 2, 13.1, "TOTAL TRANSFER AMOUNT:", bold=True)
    t(c, 16, 13.1, "3.994,74", bold=True)
    t(c, 2, 14.1, "Transaction Status: EXECUTED")
    t(c, 2, 14.9, "Transaction No: TXN-20260131-44821")
    c.save()
    print("  + bank_confirmation_202601.pdf")


# ── 6. Individual payslip ─────────────────────────────────────────────────────
def gen_payslip():
    c = _c("payslip_emp001_202601.pdf")
    t(c, 2, 2, "PAYSLIP", 13, bold=True)
    t(c, 2, 2.9, "Northwind Foods Ltd  |  Tax ID: 801234567")
    ln(c, 2, 3.8, 19, 3.8)
    t(c, 2, 4.6, "EMPLOYEE: Anders Meyer")
    t(c, 2, 5.4, "EMPLOYEE CODE: EMP-001")
    t(c, 2, 6.2, "PERIOD: January 2026")
    ln(c, 2, 7.2, 19, 7.2)
    t(c, 2, 7.9, "EARNINGS", bold=True)
    t(c, 2, 8.7, "Base salary")
    t(c, 15, 8.7, "1.800,00")
    ln(c, 2, 9.5, 19, 9.5)
    t(c, 2, 10.2, "Gross pay:", bold=True)
    t(c, 15, 10.2, "1.800,00", bold=True)
    t(c, 2, 11.4, "DEDUCTIONS", bold=True)
    t(c, 2, 12.2, "Employee social security (16%)")
    t(c, 15, 12.2, "-288,00")
    t(c, 2, 13.0, "Income tax")
    t(c, 15, 13.0, "-199,56")
    ln(c, 2, 13.8, 19, 13.8)
    t(c, 2, 14.5, "NET PAY:", bold=True)
    t(c, 15, 14.5, "1.312,44", bold=True)
    ln(c, 2, 15.5, 19, 15.5)
    t(c, 2, 16.2, "EMPLOYER COST:", bold=True)
    t(c, 15, 16.2, "2.268,00", bold=True)
    t(c, 2, 17.0, "  (Gross 1.800 + employer social security 26%: 468,00)")
    c.save()
    print("  + payslip_emp001_202601.pdf")


# ── 7. Vendor account statement (Google Cloud) ────────────────────────────────
def gen_statement():
    c = _c("google_statement_202601.pdf")
    t(c, 2, 2, "GOOGLE CLOUD EMEA LIMITED", 13, bold=True)
    t(c, 2, 2.9, "70 Sir John Rogerson's Quay, Dublin 2, Ireland  |  VAT: IE6388047V")
    t(c, 2, 4.5, "STATEMENT OF ACCOUNT", 12, bold=True)
    t(c, 2, 5.3, "Customer: Northwind Foods Ltd  |  VAT: 801234567")
    t(c, 2, 6.1, "Statement Period: 01/01/2026 – 31/01/2026")
    ln(c, 2, 7.1, 19, 7.1)
    t(c, 2, 7.8, "DOCUMENT #", bold=True)
    t(c, 7, 7.8, "DATE", bold=True)
    t(c, 10.5, 7.8, "DUE DATE", bold=True)
    t(c, 14, 7.8, "AMOUNT", bold=True)
    t(c, 17, 7.8, "BALANCE", bold=True)
    ln(c, 2, 8.3, 19, 8.3)
    t(c, 2, 9.0, "5537606065")
    t(c, 7, 9.0, "01/12/2025")
    t(c, 10.5, 9.0, "15/01/2026")
    t(c, 14, 9.0, "EUR 198.44")
    t(c, 17, 9.0, "0.00")
    t(c, 2, 9.8, "5561234001")
    t(c, 7, 9.8, "01/01/2026")
    t(c, 10.5, 9.8, "15/02/2026")
    t(c, 14, 9.8, "EUR 211.30")
    t(c, 17, 9.8, "211.30")
    t(c, 2, 10.6, "5561234002")
    t(c, 7, 10.6, "15/01/2026")
    t(c, 10.5, 10.6, "01/03/2026")
    t(c, 14, 10.6, "EUR 45.00")
    t(c, 17, 10.6, "45.00")
    ln(c, 2, 11.4, 19, 11.4)
    t(c, 2, 12.1, "Statement Balance:", bold=True)
    t(c, 17, 12.1, "EUR 256.30", bold=True)
    t(c, 2, 12.9, "Overdue (> 30 days):", bold=True)
    t(c, 17, 12.9, "EUR 0.00", bold=True)
    c.save()
    print("  + google_statement_202601.pdf")


if __name__ == "__main__":
    print(f"Generating synthetic sample documents → {OUT}/")
    gen_toll_invoice()
    gen_anthropic()
    gen_aws()
    gen_payroll_register()
    gen_bank_confirmation()
    gen_payslip()
    gen_statement()
    print(f"\nDone — 7 PDFs written to {OUT}/")
    print("These cover: invoice, account_statement, payroll_register,")
    print("bank_confirmation, payslip — all Archon doc types.")
