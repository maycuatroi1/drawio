import json
import subprocess
import sys

from drawio import Document
from drawio.cli import main


def test_cli_new_info_validate_url(tmp_path, capsys):
    p = tmp_path / "diagram.drawio"
    assert main(["new", str(p), "--name", "Overview"]) == 0
    capsys.readouterr()
    assert main(["validate", str(p), "--check-bounds"]) == 0
    assert "Valid: 1 page" in capsys.readouterr().out
    assert main(["info", str(p)]) == 0
    assert json.loads(capsys.readouterr().out)[0]["name"] == "Overview"
    assert main(["url", str(p)]) == 0
    assert "#R" in capsys.readouterr().out
    assert main(["new", str(p)]) == 1
    assert "drawio:" in capsys.readouterr().err
    assert main(["new", str(p), "--overwrite"]) == 0


def test_cli_failure_status(tmp_path, capsys):
    p = tmp_path / "broken.drawio"
    p.write_text("not XML")
    assert main(["validate", str(p)]) == 1
    assert "Invalid" in capsys.readouterr().err
    assert main(["info", str(tmp_path / "missing")]) == 1


def test_module_cli_exit_status(tmp_path):
    p = tmp_path / "valid.drawio"
    doc = Document()
    doc.add_page("One")
    doc.save(p)
    result = subprocess.run(
        [sys.executable, "-m", "drawio", "validate", str(p)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    result = subprocess.run(
        [sys.executable, "-m", "drawio", "validate", str(tmp_path / "missing")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
