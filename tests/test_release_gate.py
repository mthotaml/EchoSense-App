from scripts import release_gate


def test_release_gate_stops_after_first_failure(monkeypatch) -> None:
    calls = []

    def completed(arguments, *, cwd, check, env):
        calls.append((arguments, cwd, check, env["ECHOSENSE_PYTHON"]))
        return type("Result", (), {"returncode": 7})()

    monkeypatch.setattr(release_gate.subprocess, "run", completed)

    result = release_gate._command("failing-check", ["false"])

    assert result["passed"] is False
    assert result["return_code"] == 7
    assert calls == [(["false"], release_gate.ROOT, False, release_gate.sys.executable)]
