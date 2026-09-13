"""Build two editable tabs with nested blocks and routed connectors."""

from pathlib import Path

from drawio import Document


def build_document():
    doc = Document()
    page = doc.add_page("Publishing Workflow", id="publishing", width=1200, height=700)
    page.text("Publishing Workflow", 40, 25, 1080, 45, style={"fontSize": 28, "fontStyle": 1})
    drafts = page.box("Drafts", 40, 180, 220, 100, id="drafts")
    submissions = page.box("Submissions", 40, 380, 220, 100, id="submissions")
    review = page.box(
        "Editorial Review", 350, 270, 230, 120, id="review", style={"fillColor": "#e7effb"}
    )
    library = page.container(
        "Publication Library", 700, 130, 430, 440, id="library", style={"fillColor": "#f3f6fa"}
    )
    catalog = page.container("Catalog", 20, 70, 390, 240, parent=library, id="catalog")
    page.box("Articles", 20, 65, 350, 60, parent=catalog)
    page.box("Images", 20, 150, 350, 60, parent=catalog)
    page.box("Publication History", 20, 345, 390, 65, parent=library)
    page.connect(
        drafts,
        review,
        "submit",
        source_port=(1, 0.5),
        target_port=(0, 0.25),
        waypoints=[(305, 230), (305, 300)],
    )
    page.connect(
        submissions,
        review,
        "submit",
        source_port=(1, 0.5),
        target_port=(0, 0.75),
        waypoints=[(320, 430), (320, 360)],
    )
    page.connect(review, library, "publish", source_port=(1, 0.5), target_port=(0, 0.5))

    lifecycle = doc.add_page("Review Lifecycle", id="lifecycle", width=1100, height=600)
    lifecycle.text("Review Lifecycle", 40, 25, 1000, 45, style={"fontSize": 28, "fontStyle": 1})
    draft = lifecycle.box("Draft", 40, 180, id="draft")
    reviewing = lifecycle.box("In Review", 430, 180, id="reviewing", style={"fillColor": "#e7effb"})
    published = lifecycle.box("Published", 820, 180, id="published", style={"fillColor": "#e7f2ed"})
    lifecycle.connect(draft, reviewing, "request review")
    lifecycle.connect(reviewing, published, "approve")
    lifecycle.connect(
        reviewing,
        draft,
        "revise",
        dashed=True,
        source_port=(0.5, 1),
        target_port=(0.5, 1),
        waypoints=[(530, 400), (140, 400)],
    )
    doc.validate(check_bounds=True)
    return doc


if __name__ == "__main__":
    output = Path("output")
    output.mkdir(exist_ok=True)
    print(build_document().save(output / "publishing.drawio", overwrite=True))
