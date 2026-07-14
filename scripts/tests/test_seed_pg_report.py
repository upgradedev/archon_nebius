"""The seed report MUST carry the exact field names services/pg_sync.py reads,
otherwise the mirror would silently no-op on the seeded period (the very failure
mode this seed exists to disprove). This test locks the contract."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # scripts/

from seed_pg_report import build_report


def test_wrapper_shape():
    w = build_report("2099-12")
    assert set(w) >= {"jobId", "report", "generatedAt"}
    assert isinstance(w["report"], dict)


def test_relational_sections_present_and_nonempty():
    r = build_report("2099-12")["report"]
    assert r["payrollEvents"], "payrollEvents must be non-empty to exercise the mirror"
    assert r["employeeSummaries"], "employeeSummaries must be non-empty"
    assert r["validationResults"], "validationResults must be non-empty"


def test_field_names_match_pg_sync_reader():
    r = build_report("2099-12")["report"]
    # Field names pg_sync.materialize_report reads for each table.
    assert set(r["payrollEvents"][0]) >= {
        "company_name", "net_total", "gross_total",
        "employer_cost_total", "employee_count", "bank_confirmed",
    }
    assert set(r["employeeSummaries"][0]) >= {
        "employee_code", "employee_name", "gross_pay", "net_pay", "employer_cost",
    }
    assert set(r["validationResults"][0]) >= {
        "rule", "passed", "severity", "message", "source_files",
    }


def test_deterministic():
    assert build_report("2099-12") == build_report("2099-12")
