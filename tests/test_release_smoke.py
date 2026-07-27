import json
import runpy
from pathlib import Path


def test_release_smoke_certifies_every_app_profile(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    module = runpy.run_path(
        Path(__file__).parents[1] / "scripts/release_smoke.py",
        run_name="release_smoke",
    )
    module["main"]()

    report = json.loads((tmp_path / "artifacts/guardian/release-evidence.json").read_text())
    assert report["release_ready"] is True
    assert report["checks"] == {
        "api_health": True,
        "legacy_health": True,
        "product_health": True,
    }
    assert report["blocking_severities"] == ["severity-1", "severity-2"]
    assert report["artifact_identity"]["guardian_version"] == 2
    assert all(len(digest) == 64 for digest in report["artifact_identity"]["files"].values())
