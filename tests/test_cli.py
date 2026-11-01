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


def broken_file(tmp_path):
    doc = Document()
    page = doc.add_page("Broken", id="broken")
    page.box("A plain label that is much too long for this small box", 20, 20, 120, 40)
    a = page.box("A", 20, 200, 100, 50, id="a")
    b = page.box("B", 400, 200, 100, 50, id="b")
    page.box("In the way", 200, 190, 100, 70, id="wall")
    page.connect(a, b, id="ab")
    path = tmp_path / "broken.drawio"
    doc.save(path)
    return path


def test_cli_lint_json_and_exit_status(tmp_path, capsys):
    path = broken_file(tmp_path)
    assert main(["lint", str(path), "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    found = {i["code"] for i in report["issues"]}
    assert {"text-overflow", "edge-crosses-shape"} <= found
    assert report["summary"]["warning"] >= 2
    assert main(["lint", str(path), "--fail-on", "error"]) == 0
    out = capsys.readouterr().out
    assert "fix:" in out and "warning" in out
    assert main(["lint", str(path), "--fit", "nonsense"]) == 1


def test_cli_render_inspect_fit_layout_merge(tmp_path, capsys):
    path = broken_file(tmp_path)
    assert main(["render", str(path), "-o", str(tmp_path / "out.svg"), "--json"]) == 0
    rendered = json.loads(capsys.readouterr().out)[0]
    assert rendered["backend"] in ("native", "desktop") and (tmp_path / "out.svg").exists()
    assert main(["render", str(path), "--backend", "native", "--all-pages", "-f", "svg"]) == 0
    assert (tmp_path / "broken" / "broken.svg").exists()
    capsys.readouterr()
    assert main(["inspect", str(path), "--json"]) == 0
    pages = json.loads(capsys.readouterr().out)
    assert pages[0]["connectors"][0]["source"] == "a" and len(pages[0]["shapes"]) == 4
    assert main(["inspect", str(path)]) == 0
    assert "edge  ab" in capsys.readouterr().out
    fixed = tmp_path / "fixed.drawio"
    assert main(["fit", str(path), "--autosize", "-o", str(fixed), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["autosized"] == ["n1"]
    assert main(["layout", str(path), "-o", str(tmp_path / "laid.drawio")]) == 0
    assert main(["merge", str(tmp_path / "m.drawio"), str(path), str(fixed), "--json"]) == 0
    capsys.readouterr()
    assert len(Document.load(tmp_path / "m.drawio").pages) == 2


def test_cli_shapes_doctor_skill(tmp_path, capsys):
    assert main(["shapes", "--json"]) == 0
    assert "cylinder" in json.loads(capsys.readouterr().out)["shapes"]
    assert main(["doctor", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert "native (svg)" in report["backends"]
    assert main(["skill", "show"]) == 0
    assert "name: drawio" in capsys.readouterr().out
    assert main(["skill", "install", "--dest", str(tmp_path / "skills")]) == 0
    installed = tmp_path / "skills" / "drawio"
    assert (installed / "SKILL.md").exists() and (installed / "references" / "api.md").exists()
    assert main(["skill", "install", "--dest", str(tmp_path / "skills")]) == 1
    assert "--force" in capsys.readouterr().err
    assert main(["skill", "install", "--dest", str(tmp_path / "skills"), "--force"]) == 0


def test_cli_lint_select_ignore_and_info_lines(tmp_path, capsys):
    doc = Document()
    page = doc.add_page("Wide", id="wide")
    page.box("tiny", 0, 0, 2000, 100, style={"fontSize": 48, "ellipse": 1})
    path = tmp_path / "wide.drawio"
    doc.save(path)
    assert main(["lint", str(path), "--fit", "8.15x4.85in"]) == 0
    out = capsys.readouterr().out
    assert "aspect" not in out and "-v shows the info lines" in out
    assert main(["lint", str(path), "--fit", "8.15x4.85in", "-v"]) == 0
    assert "[aspect]" in capsys.readouterr().out
    assert main(["lint", str(path), "--json", "--ignore", "aspect,style-ignored"]) == 0
    assert json.loads(capsys.readouterr().out)["issues"] == []
