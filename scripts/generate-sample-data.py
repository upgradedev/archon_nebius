"""
Generate synthetic Greek business documents for Archon sample data.

Creates realistic but entirely fictional invoices, payroll summaries,
and expense receipts in PDF format. No real data is used.

Usage:
    python scripts/generate-sample-data.py
"""

import os
import random
from pathlib import Path
from datetime import date, timedelta

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
except ImportError:
    print("Install reportlab: pip install reportlab")
    raise

OUTPUT_DIR = Path(__file__).parent.parent / "sample-data"

VENDORS = [
    ("Ελληνικά Τηλεπικοινωνία ΑΕ", "EL123456789"),
    ("Δυναμική Πληροφορική ΕΠΕ", "EL987654321"),
    ("Αθηναϊκή Ενέργεια ΑΕ", "EL456789123"),
    ("Γενική Εφοδιαστική ΟΕ", "EL321654987"),
    ("Σύγχρονες Υπηρεσίες ΑΕ", "EL654321098"),
]

COMPANY = ("Archon Λογισμικό ΙΚΕ", "EL800123456")

random.seed(42)


def random_date(year: int = 2026, month: int = 4) -> date:
    day = random.randint(1, 28)
    return date(year, month, day)


def fmt_eur(amount: float) -> str:
    return f"€{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def create_invoice(path: Path, vendor: tuple, amount: float, inv_num: str, period_date: date):
    c = canvas.Canvas(str(path), pagesize=A4)
    w, h = A4

    c.setFont("Helvetica-Bold", 16)
    c.drawString(2 * cm, h - 2 * cm, "ΤΙΜΟΛΟΓΙΟ ΠΑΡΟΧΗΣ ΥΠΗΡΕΣΙΩΝ")
    c.setFont("Helvetica", 10)
    c.drawString(2 * cm, h - 2.8 * cm, f"Αριθμός: {inv_num}")
    c.drawString(2 * cm, h - 3.4 * cm, f"Ημερομηνία: {period_date.strftime('%d/%m/%Y')}")

    c.setFont("Helvetica-Bold", 11)
    c.drawString(2 * cm, h - 4.5 * cm, "ΠΩΛΗΤΗΣ:")
    c.setFont("Helvetica", 10)
    c.drawString(2 * cm, h - 5.1 * cm, vendor[0])
    c.drawString(2 * cm, h - 5.7 * cm, f"ΑΦΜ: {vendor[1]}")

    c.setFont("Helvetica-Bold", 11)
    c.drawString(10 * cm, h - 4.5 * cm, "ΑΓΟΡΑΣΤΗΣ:")
    c.setFont("Helvetica", 10)
    c.drawString(10 * cm, h - 5.1 * cm, COMPANY[0])
    c.drawString(10 * cm, h - 5.7 * cm, f"ΑΦΜ: {COMPANY[1]}")

    vat_rate = 0.24
    net = amount / (1 + vat_rate)
    vat = amount - net

    c.setFont("Helvetica-Bold", 10)
    c.drawString(2 * cm, h - 8 * cm, "Περιγραφή")
    c.drawString(14 * cm, h - 8 * cm, "Αξία")
    c.line(2 * cm, h - 8.3 * cm, 19 * cm, h - 8.3 * cm)

    c.setFont("Helvetica", 10)
    c.drawString(2 * cm, h - 9 * cm, "Παροχή υπηρεσιών")
    c.drawString(14 * cm, h - 9 * cm, fmt_eur(net))

    c.line(2 * cm, h - 9.5 * cm, 19 * cm, h - 9.5 * cm)
    c.drawString(12 * cm, h - 10.2 * cm, f"Καθαρή Αξία:")
    c.drawString(16 * cm, h - 10.2 * cm, fmt_eur(net))
    c.drawString(12 * cm, h - 10.8 * cm, f"ΦΠΑ 24%:")
    c.drawString(16 * cm, h - 10.8 * cm, fmt_eur(vat))

    c.setFont("Helvetica-Bold", 11)
    c.drawString(12 * cm, h - 11.5 * cm, "ΣΥΝΟΛΟ:")
    c.drawString(16 * cm, h - 11.5 * cm, fmt_eur(amount))

    c.save()


def create_payroll(path: Path, month: str, employees: list[dict]):
    c = canvas.Canvas(str(path), pagesize=A4)
    w, h = A4

    c.setFont("Helvetica-Bold", 16)
    c.drawString(2 * cm, h - 2 * cm, "ΜΙΣΘΟΔΟΣΙΑ")
    c.setFont("Helvetica", 12)
    c.drawString(2 * cm, h - 2.8 * cm, f"Περίοδος: {month}")
    c.drawString(2 * cm, h - 3.4 * cm, f"Εταιρεία: {COMPANY[0]}  ΑΦΜ: {COMPANY[1]}")

    y = h - 5 * cm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(2 * cm, y, "Εργαζόμενος")
    c.drawString(10 * cm, y, "Ειδικότητα")
    c.drawString(15 * cm, y, "Μικτές Αποδοχές")
    c.line(2 * cm, y - 0.3 * cm, 19 * cm, y - 0.3 * cm)

    c.setFont("Helvetica", 10)
    total = 0.0
    for i, emp in enumerate(employees):
        y -= 0.8 * cm
        c.drawString(2 * cm, y, emp["name"])
        c.drawString(10 * cm, y, emp["role"])
        c.drawString(15 * cm, y, fmt_eur(emp["salary"]))
        total += emp["salary"]

    c.line(2 * cm, y - 0.3 * cm, 19 * cm, y - 0.3 * cm)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(12 * cm, y - 1 * cm, "ΣΥΝΟΛΟ ΜΙΣΘΟΔΟΣΙΑΣ:")
    c.drawString(16 * cm, y - 1 * cm, fmt_eur(total))

    c.save()


def main():
    (OUTPUT_DIR / "invoices").mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "payroll").mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "expenses").mkdir(parents=True, exist_ok=True)

    period_date = date(2026, 4, 1)

    # 8 vendor invoices
    for i, vendor in enumerate(VENDORS):
        for j in range(1, 3):
            amount = round(random.uniform(500, 8000), 2)
            inv_num = f"INV-2026-{i+1:02d}{j:02d}"
            path = OUTPUT_DIR / "invoices" / f"invoice_{i+1}_{j}.pdf"
            create_invoice(path, vendor, amount, inv_num, random_date(2026, 4))
            print(f"Created {path}")

    # 1 payroll report
    employees = [
        {"name": "Γιώργος Παπαδόπουλος", "role": "Προγραμματιστής", "salary": 2800.00},
        {"name": "Μαρία Κωνσταντίνου",   "role": "Λογίστρια",      "salary": 2400.00},
        {"name": "Νίκος Αλεξίου",         "role": "Διευθυντής",     "salary": 3500.00},
        {"name": "Ελένη Σταυρίδη",        "role": "Γραμματέας",     "salary": 1800.00},
        {"name": "Κώστας Βλάχος",         "role": "Τεχνικός",       "salary": 2200.00},
    ]
    payroll_path = OUTPUT_DIR / "payroll" / "payroll_2026_04.pdf"
    create_payroll(payroll_path, "Απρίλιος 2026", employees)
    print(f"Created {payroll_path}")

    print(f"\nDone. Generated documents in {OUTPUT_DIR}")
    print("Upload them via the Archon UI to test the pipeline.")


if __name__ == "__main__":
    main()
