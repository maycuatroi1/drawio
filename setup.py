"""Python setup.py for drawio package"""

import io
import os

from setuptools import find_packages, setup


def read(*paths, **kwargs):
    """Read the contents of a text file safely.
    >>> read("drawio", "VERSION")
    '0.1.0'
    >>> read("README.md")
    ...
    """

    content = ""
    with io.open(
        os.path.join(os.path.dirname(__file__), *paths),
        encoding=kwargs.get("encoding", "utf8"),
    ) as open_file:
        content = open_file.read().strip()
    return content


def read_requirements(path):
    return [
        line.strip()
        for line in read(path).split("\n")
        if line.strip() and not line.startswith(('"', "#", "-", "git+"))
    ]


setup(
    name="drawio-python",
    version=read("drawio", "VERSION"),
    description=(
        "Build, check and export editable draw.io diagrams in Python; made for people and agents"
    ),
    url="https://github.com/maycuatroi1/drawio/",
    long_description=read("README.md"),
    long_description_content_type="text/markdown",
    author="Nguyen Anh Binh",
    packages=find_packages(exclude=["tests", ".github"]),
    python_requires=">=3.9",
    include_package_data=True,
    install_requires=read_requirements("requirements.txt"),
    entry_points={"console_scripts": ["drawio = drawio.__main__:main"]},
    extras_require={
        "test": read_requirements("requirements-test.txt"),
        "render": ["Pillow>=9.1"],
        "browser-render": ["playwright>=1.40"],
        "browser": ["selenium>=4", "webdriver-manager>=4"],
        "pdf": ["graphviz>=0.20"],
        "excel": ["pandas>=1.5", "xlsxwriter>=3"],
        "docs": ["mkdocs>=1.5"],
    },
)
