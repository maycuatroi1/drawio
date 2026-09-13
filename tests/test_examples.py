import runpy
from pathlib import Path

import pytest

from drawio import Document


@pytest.mark.parametrize(
    "example,output,pages",
    [
        ("draw-flow-diagrams.py", "shopping.drawio", 1),
        ("mermaid-to-drawio.py", "sample.drawio", 1),
        ("complex-example.py", "extended.drawio", 2),
        ("native_document.py", "output/publishing.drawio", 2),
    ],
)
def test_examples_produce_real_xml(example, output, pages, monkeypatch):
    def reject_browser(*args, **kwargs):
        pytest.fail("Examples must not launch a browser")

    monkeypatch.setattr("webbrowser.open", reject_browser)
    repo_root = Path(__file__).resolve().parents[1]
    runpy.run_path(str(repo_root / "examples" / example), run_name="__main__")
    doc = Document.load(output)
    assert len(doc.pages) == pages
    doc.validate(check_bounds=True)
