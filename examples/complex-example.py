"""Add a page without rebuilding an existing document."""

from drawio import Document

if __name__ == "__main__":
    initial = Document()
    initial.add_page("Original").box("Keep this page", 40, 40)
    initial.save("original.drawio", overwrite=True)

    document = Document.load("original.drawio")
    page = document.add_page("Additional Details")
    group = page.container("Content", 40, 40, 320, 280)
    page.box("Text", 20, 70, 280, 70, parent=group)
    page.box("Images", 20, 170, 280, 70, parent=group)
    document.validate(check_bounds=True)
    print(document.save("extended.drawio", overwrite=True))
