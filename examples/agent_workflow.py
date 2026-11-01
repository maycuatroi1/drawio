"""Build a diagram, lay it out automatically, check it and export it.

The loop an agent follows: build, lint, render, look, fix.
"""

from pathlib import Path

from drawio import Document, Theme
from drawio.layout import layered
from drawio.lint import check
from drawio.render import render
from drawio.shapes import color

out = Path("output")
out.mkdir(exist_ok=True)

doc = Document(theme=Theme.drawio())
page = doc.add_page("Order flow", id="order-flow")
web = page.box("Web shop", 0, 0, 140, 60, id="web", shape="rounded", style=color("blue"))
api = page.box("Orders API", 0, 0, 140, 60, id="api", style=color("blue"))
check_stock = page.box("In stock?", 0, 0, 140, 90, id="stock", shape="rhombus")
db = page.box("Orders DB", 0, 0, 140, 80, id="db", shape="cylinder", style=color("yellow"))
mail = page.box("Back-order e-mail", 0, 0, 140, 60, id="mail", style=color("orange"))
page.connect(web, api, "POST /orders", id="web-api")
page.connect(api, check_stock, id="api-stock")
page.connect(check_stock, db, "yes", id="stock-db")
page.connect(check_stock, mail, "no", id="stock-mail", dashed=True)

layered(page, direction="down", rank_gap=70, gap=60)
page.fit()
doc.validate(check_bounds=True)
doc.save(out / "order-flow.drawio", overwrite=True)

for issue in check(doc):
    print(f"{issue.code}: {issue.message} Fix: {issue.hint}")
print(render(doc, out / "order-flow.svg", backend="native").path)
