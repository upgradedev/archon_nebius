import os
import pathlib
import subprocess
import tempfile
import shutil

def test_redeploy_sh_uses_registry_password():
    # Find paths
    root = pathlib.Path(__file__).parent.parent.parent
    redeploy_sh_path = root / "nebius" / "redeploy.sh"
    env_path = root / ".env"
    env_backup_path = root / ".env.backup_test"

    assert redeploy_sh_path.exists(), f"redeploy.sh not found at {redeploy_sh_path}"

    # 1. Verify file content statically first
    content = redeploy_sh_path.read_text(encoding="utf-8")
    assert '--registry-password "${NEBIUS_REGISTRY_PASSWORD:-$RUNTIME_IAM_TOKEN}"' in content
    # Native-HTTPS contract: plain uvicorn image on 8000, TLS terminated by Nebius.
    # No Caddy image, no DuckDNS repoint, no self-signed chain.
    assert "backend/Dockerfile.endpoint" in content
    assert "Dockerfile.https" not in content
    assert "--container-port 8000" in content
    assert "duckdns.org" not in content
    assert "CADDY_DOMAIN" not in content
    # Reads the managed HTTPS URL from status.public_endpoints (not a raw public IP).
    assert "public_endpoints" in content

    # 2. Run execution integration test with mocked CLI
    # Backup existing .env if present
    has_env = env_path.exists()
    if has_env:
        shutil.copy(env_path, env_backup_path)

    # Create temporary sandbox directory for mock binary and logs
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_dir_path = pathlib.Path(tmpdir)
        log_file = tmp_dir_path / "nebius_calls.log"
        mock_bin_dir = tmp_dir_path / "bin"
        mock_bin_dir.mkdir()

        # Write test .env
        test_env_content = """
NEBIUS_PROJECT_ID=test-project-123
NEBIUS_SUBNET_ID=test-subnet-456
NEBIUS_BUCKET_NAME=test-bucket
NEBIUS_REGISTRY=cr.test.nebius.cloud
NEBIUS_REGISTRY_PATH=test-path
EXTRACTION_JOB_IMAGE=test-image
NEBIUS_REGISTRY_PASSWORD=static-key-token-999
NEBIUS_SA_ID=sa-123
NEBIUS_SA_KEY_ID=key-456
NEBIUS_SA_KEY_B64=ZmFrZS1rZXk=
POSTGRES_HOST=pg-host
POSTGRES_PORT=5432
POSTGRES_DB=db
POSTGRES_USER=user
POSTGRES_PASSWORD=pass
NEBIUS_INFERENCE_BASE_URL=https://api.studio.nebius.ai/v1
NEBIUS_INFERENCE_API_KEY=inf-key
STORAGE_ENDPOINT_URL=https://storage.test.nebius.cloud
AWS_ACCESS_KEY_ID=test-key-id
AWS_SECRET_ACCESS_KEY=test-secret-key
        """
        with open(env_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(test_env_content.strip())

        # 1. Create the mock logic entirely in native Bash
        log_file_rel = "nebius_calls_test.log"
        log_file_abs = root / log_file_rel
        
        # Clean up any leftover test log
        if log_file_abs.exists():
            log_file_abs.unlink()

        mock_sh_path = mock_bin_dir / "nebius"
        mock_sh_script = f"""#!/usr/bin/env bash
# Write arguments to log
echo "$@" >> "{log_file_rel}"

# Mock outputs
if [[ "$*" == *"iam get-access-token"* ]]; then
  echo "temporary-iam-token-000"
elif [[ "$*" == *"endpoint list"* ]]; then
  echo "[]"
elif [[ "$*" == *"endpoint get-by-name"* ]]; then
  echo '{{"status": {{"public_endpoints": ["https://ep-test.eu-west1.nebius.cloud"]}}}}'
fi
"""
        with open(mock_sh_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(mock_sh_script)
            
        try:
            os.chmod(mock_sh_path, 0o755)
        except Exception:
            pass

        # Prepare environment with mock PATH
        env = os.environ.copy()
        env["PATH"] = str(mock_bin_dir) + os.pathsep + env.get("PATH", "")
        env["BUILD"] = "false"

        try:
            # Execute redeploy.sh inside bash
            result = subprocess.run(
                ["bash", "nebius/redeploy.sh"],
                cwd=str(root),
                env=env,
                capture_output=True,
                text=True,
                check=True
            )
            
            # Assertions on CLI invocations (inside try to read before finally cleans it up)
            assert log_file_abs.exists(), "Mock nebius CLI was never called"
            calls = log_file_abs.read_text(encoding="utf-8").splitlines()
            
            # Verify that nebius endpoint create was called with correct registry credentials
            create_call = None
            for call in calls:
                if "endpoint create" in call or ("ai" in call and "endpoint" in call and "create" in call):
                    create_call = call
                    break
            
            assert create_call is not None, "nebius ai endpoint create was not called"
            # Ensure our mock static-key password was passed instead of the temporary IAM token fallback
            assert "--registry-password static-key-token-999" in create_call
            assert "--registry-username iam" in create_call
            # Native-HTTPS deploy contract: HTTP port 8000, no public IP, no DuckDNS/Caddy env.
            assert "--container-port 8000" in create_call
            assert "--public" not in create_call
            assert "DUCKDNS" not in create_call
            assert "CADDY_DOMAIN" not in create_call

            # The managed HTTPS URL was read from status.public_endpoints.
            assert any("endpoint get-by-name" in c for c in calls), "managed URL was never read"
        finally:
            # Cleanup: Restore original .env and delete test log
            if env_path.exists():
                env_path.unlink()
            if has_env and env_backup_path.exists():
                shutil.move(env_backup_path, env_path)
            if log_file_abs.exists():
                log_file_abs.unlink()
