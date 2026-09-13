import pytest

from drawio.itergrations.mermaid.mermaid_controller import MermaidController


def mermaid_to_drawio(mermaid_text):
    mermaid_controller = MermaidController()
    graph = mermaid_controller.load(mermaid_text)
    assert graph.nodes
    # drawio_file = graph.render(file_name="sample.drawio", show=False)
    print("Success building graph")


def test_mermaid_to_drawio_empty_input():
    mermaid_text = ""
    with pytest.raises(Exception):
        mermaid_to_drawio(mermaid_text)


def test_mermaid_to_drawio_valid_input():
    mermaid_text = """
    flowchart TD
    A[Christmas] -->|Get money| B((Go shopping))
    B --> C{Let me think}
    C --> D[Laptop]
    C --|Two|--> E[iPhone]
    C -->|Three| F[fa:fa-car Car]
    """
    mermaid_to_drawio(mermaid_text)


def test_mermaid_to_drawio_incorrect_input():
    mermaid_text = """
    Lorem ipsum dolor sit amet, consectetur adipiscing elit
    """
    with pytest.raises(Exception):
        mermaid_to_drawio(mermaid_text)


def test_mermaid_to_drawio_non_string_input():
    mermaid_text = 12345
    with pytest.raises(Exception):
        mermaid_to_drawio(mermaid_text)


def test_labels_shapes_and_edges_survive_native_render():
    graph = MermaidController().load("""flowchart TD
    A[Christmas] -->|Get money| B((Go shopping))
    B --> C{Let me think}
    C -->|One| D[Laptop]
    C -->|Two| E[iPhone]
    C -->|Three| F[Car]
    """)
    assert len(graph.nodes) == 6
    assert len(graph.edges) == 5
    assert graph.get_node("B").name == "Go shopping"
    assert graph.get_node("B").shape == "circle"
    assert graph.edges[0].label == "Get money"
    assert "Get money" in graph.to_draw_io_xml()


def test_chains_implicit_nodes_and_quoted_labels():
    graph = MermaidController().load('graph LR; A["Input [x]; value"] --> B --> C; C --> A')
    assert len(graph.nodes) == 3 and len(graph.edges) == 3
    assert graph.get_node("A").name == "Input [x]; value"


@pytest.mark.parametrize(
    "source",
    [
        "flowchart TD\nsubgraph Group\nA --> B\nend",
        "flowchart TD\nA -.-> B",
        "flowchart TD\nA[Unclosed",
        "flowchart TD\nA -->",
    ],
)
def test_unsupported_syntax_is_not_silently_dropped(source):
    with pytest.raises(ValueError):
        MermaidController().load(source)


def test_compact_edges_numeric_ids_and_hyphenated_ids():
    graph = MermaidController().load("flowchart LR; 0-->1-->node-0")
    assert len(graph.nodes) == 3 and len(graph.edges) == 2
    graph.to_document().validate()
