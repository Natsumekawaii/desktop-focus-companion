"""Behavioral gates for provenance, release safety and bounded smoke processes."""

from __future__ import annotations

import json
import re
import subprocess
import textwrap
from pathlib import Path

import pytest

from app import __version__
from scripts import build_support
from scripts.build_support import payload_digest, source_digest, verify_manifest
from scripts.publish_release import assert_identical_assets, notes_body

ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = "powershell.exe"


def test_manifest_rejects_stale_source_version_and_tampered_payload(tmp_path):
    (tmp_path / "app.exe").write_bytes(b"payload")
    manifest = {
        "version": __version__,
        "source_sha256": "source",
        "payload_sha256": payload_digest(tmp_path),
    }
    path = tmp_path / "build-manifest.json"
    path.write_text(json.dumps(manifest))
    verify_manifest(tmp_path, expected_source="source")
    with pytest.raises(ValueError, match="stale"):
        verify_manifest(tmp_path, expected_source="new-source")
    (tmp_path / "app.exe").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="payload"):
        verify_manifest(tmp_path, expected_source="source")
    manifest["version"] = "0.0.0"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="stale"):
        verify_manifest(tmp_path, expected_source="source")


def test_source_digest_includes_new_files_but_excludes_caches_and_artifacts(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "a.py").write_text("old")
    before = source_digest(tmp_path)
    (tmp_path / "app" / "__pycache__").mkdir()
    (tmp_path / "app" / "__pycache__" / "cache.pyc").write_bytes(b"cache")
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "old.exe").write_bytes(b"old")
    assert source_digest(tmp_path) == before
    (tmp_path / "app" / "new.py").write_text("new")
    assert source_digest(tmp_path) != before


def test_release_assets_are_idempotent_or_fail_without_mutation():
    assets = {"installer.exe": "abc", "SHA256SUMS.txt": "def"}
    assert_identical_assets(assets, dict(assets))
    for remote in ({}, {"installer.exe": "old"}, {**assets, "extra.zip": "xyz"}):
        with pytest.raises(ValueError, match="Refusing"):
            assert_identical_assets(assets, remote)
    script = (ROOT / "scripts/publish_release.py").read_text(encoding="utf-8")
    assert "--clobber" not in script
    assert "'edit'" not in script


def test_preflight_rejects_version_and_notes_before_build(monkeypatch, tmp_path):
    monkeypatch.setattr(build_support, "ROOT", tmp_path)
    (tmp_path / "toolchain.json").write_text(
        json.dumps({"python": "3.12.10", "inno_setup": "6.7.3"})
    )
    monkeypatch.setattr(build_support.platform, "python_version", lambda: "3.12.10")
    with pytest.raises(ValueError, match="Tag"):
        build_support.preflight(tag="v9.9.9")
    with pytest.raises(ValueError, match="notes"):
        build_support.preflight()
    monkeypatch.setattr(build_support.platform, "python_version", lambda: "0.0.0")
    with pytest.raises(RuntimeError, match="Python"):
        build_support.preflight()


def test_bilingual_notes_remain_complete():
    body = notes_body(f"v{__version__}", "owner/repository", "a" * 40)
    assert body.startswith("[English]")
    assert f"v{__version__}.zh-CN.md" in body
    assert "## Downloads" in body and "## 下载" not in body


def test_release_bootstrap_verifies_compiler_and_keeps_the_requested_tag():
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "choco install" not in workflow
    assert "https://github.com/jrsoftware/issrc/releases/download/" in workflow
    assert "Get-FileHash $installer -Algorithm SHA256" in workflow
    assert workflow.index("checksum mismatch") < workflow.index("Start-Process")
    assert "/CURRENTUSER" in workflow and "WaitForExit(120000)" in workflow
    assert "workflow_dispatch:" in workflow
    assert "ref: refs/tags/${{ inputs.tag || github.ref_name }}" in workflow
    assert 'git rev-parse "$($env:RELEASE_TAG)^{commit}"' in workflow
    assert "RELEASE_REVISION: ${{ steps.source.outputs.revision }}" in workflow
    assert "git tag -f" not in workflow


def powershell(body):
    helper = ROOT / "scripts" / "installer_safety.ps1"
    return subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            f"$ErrorActionPreference='Stop'; . '{helper}'; " + body + "; exit 0",
        ],
        capture_output=True,
        text=True,
        errors="replace",
        timeout=15,
        check=False,
    )


def test_reboot_queue_compares_pairs_and_only_blocks_new_application_paths():
    body = r"""
    $before = @('\??\C:\Test\app\old.dll', '', '\??\C:\Other\old.dll', '')
    Assert-PendingQueueSafe $before $before @('C:\Test\app')
    Assert-PendingQueueSafe $before @('\??\C:\Other\new.dll', '') @('C:\Test\app')
    try { Assert-PendingQueueSafe @() @('\??\C:\Test\app\new.dll', '') @('C:\Test\app'); exit 5 }
    catch { if ($_ -notmatch 'New application/test') { throw } }
    try { Assert-PendingQueueSafe @() @('C:\Other\x', '!\??\C:\Test\app\y') @('C:\Test\app'); exit 6 }
    catch { if ($_ -notmatch 'New application/test') { throw } }
    Assert-PendingQueueSafe @() @('C:\Test\application\unrelated', '') @('C:\Test\app')
    try { ConvertTo-PendingPairs @('orphan'); exit 7 }
    catch { if ($_ -notmatch 'Malformed') { throw } }
    """
    result = powershell(body)
    assert result.returncode == 0, result.stdout + result.stderr


def test_owned_process_timeout_is_bounded():
    result = powershell("""
    $child = Start-Process powershell.exe -ArgumentList @('-NoProfile', '-Command', 'Start-Sleep 10') -WindowStyle Hidden -PassThru
    try { Wait-OwnedProcess $child 100; exit 5 }
    catch { if ($_ -notmatch 'exceeded') { throw } }
    if (-not $child.WaitForExit(3000)) { throw 'Child survived timeout' }
    """)
    assert result.returncode == 0, result.stdout + result.stderr


def test_powershell_scripts_parse_without_running_builds():
    for name in (
        "dev.ps1",
        "quality.ps1",
        "build.ps1",
        "build-installer.ps1",
        "scripts/installer_safety.ps1",
    ):
        result = powershell(f"""
        $parseErrors = $null
        [System.Management.Automation.Language.Parser]::ParseFile('{ROOT / name}', [ref]$null, [ref]$parseErrors) | Out-Null
        if ($parseErrors) {{ throw ($parseErrors | Out-String) }}
        """)
        assert result.returncode == 0, result.stdout + result.stderr


def test_release_powershell_blocks_parse_without_executing_downloads():
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    blocks = re.findall(r"(?m)^        run: \|\n((?:          [^\n]*\n|\n)+)", workflow)
    assert len(blocks) >= 5
    for block in blocks:
        script = textwrap.dedent(block)
        result = powershell(
            "$script = @'\n" + script + "\n'@\n"
            "$parseErrors = $null\n"
            "[System.Management.Automation.Language.Parser]::ParseInput("
            "$script, [ref]$null, [ref]$parseErrors) | Out-Null\n"
            "if ($parseErrors) { throw ($parseErrors | Out-String) }"
        )
        assert result.returncode == 0, result.stdout + result.stderr
