"""Unit tests for the inline job runner (JOB_RUNNER_BACKEND=inline).

The inline runner executes the extraction/analysis pipelines as isolated
subprocesses inside the backend Endpoint (fallback for zero AI-Jobs quota) and
tracks status in Object Storage. All subprocess + storage + thread I/O is mocked."""
from unittest.mock import MagicMock, patch

from services import nebius


def test_submit_inline_extraction_spawns_thread_and_marks_running():
    with patch("services.nebius.threading.Thread") as T, \
         patch("services.nebius._write_inline_status") as W:
        job = nebius._submit_inline_job("up-1", "2026-01")
    assert job["id"].startswith("inline-ext-")
    assert job["status"] == "running"
    assert job["period"] == "2026-01"
    T.assert_called_once()
    T.return_value.start.assert_called_once()
    W.assert_called_once_with(job["id"], "running", "2026-01")


def test_submit_inline_analysis_spawns_thread():
    with patch("services.nebius.threading.Thread") as T, \
         patch("services.nebius._write_inline_status"):
        job = nebius._submit_inline_analysis_job("2026-01")
    assert job["id"].startswith("inline-ana-")
    assert job["status"] == "running"
    T.return_value.start.assert_called_once()


def test_run_inline_marks_completed_on_success():
    with patch("subprocess.run", return_value=MagicMock(returncode=0, stderr="", stdout="")), \
         patch("services.nebius._write_inline_status") as W:
        nebius._run_inline("inline-ext-1", "/app/jobs/extraction", {"UPLOAD_ID": "u"}, "2026-01")
    W.assert_called_once_with("inline-ext-1", "completed", "2026-01")


def test_run_inline_marks_failed_with_stderr_tail():
    with patch("subprocess.run", return_value=MagicMock(returncode=2, stderr="Traceback: boom", stdout="")), \
         patch("services.nebius._write_inline_status") as W:
        nebius._run_inline("inline-ext-1", "/app/jobs/extraction", {}, "2026-01")
    args = W.call_args[0]
    assert args[1] == "failed" and "boom" in args[3]


def test_run_inline_never_raises_on_subprocess_crash():
    with patch("subprocess.run", side_effect=OSError("no python")), \
         patch("services.nebius._write_inline_status") as W:
        nebius._run_inline("inline-ana-1", "/app/jobs/analysis", {}, "2026-01")
    assert W.call_args[0][1] == "failed"  # crash recorded, not propagated


def test_get_inline_status_completed():
    with patch("services.storage.download_json",
               return_value={"status": "completed", "updatedAt": "2026-07-14T00:00:00+00:00"}):
        st = nebius._get_inline_job_status("inline-ana-1")
    assert st["status"] == "completed" and st["progress"] == 100
    assert st["completedAt"]


def test_get_inline_status_failed_surfaces_error():
    with patch("services.storage.download_json",
               return_value={"status": "failed", "errorMessage": "boom", "updatedAt": "t"}):
        st = nebius._get_inline_job_status("inline-ext-1")
    assert st["status"] == "failed" and st["errorMessage"] == "boom"


def test_get_inline_status_no_marker_is_pending_not_error():
    with patch("services.storage.download_json", side_effect=Exception("NoSuchKey")):
        st = nebius._get_inline_job_status("inline-ext-x")
    assert st["status"] == "pending" and st["errorMessage"] is None


def test_get_job_status_routes_inline_prefix_regardless_of_backend(monkeypatch):
    monkeypatch.setattr(nebius, "JOB_RUNNER_BACKEND", "nebius")
    with patch("services.nebius._get_inline_job_status", return_value={"status": "running"}) as g:
        nebius.get_job_status("inline-ext-abc")
    g.assert_called_once()


def test_submit_dispatch_selects_inline(monkeypatch):
    monkeypatch.setattr(nebius, "JOB_RUNNER_BACKEND", "inline")
    with patch("services.nebius._submit_inline_job", return_value={"id": "inline-ext-1"}) as s:
        nebius.submit_extraction_job("u", "2026-01")
    s.assert_called_once_with("u", "2026-01")
    with patch("services.nebius._submit_inline_analysis_job", return_value={"id": "inline-ana-1"}) as a:
        nebius.submit_analysis_job("2026-01")
    a.assert_called_once_with("2026-01")
