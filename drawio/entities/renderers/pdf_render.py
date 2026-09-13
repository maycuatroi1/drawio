import re

from drawio.entities.graph.graph import Graph
from drawio.entities.renderers.base_render import BaseRender


class PDFRender(BaseRender):
    file_type = "pdf"

    def __init__(self):
        super().__init__()

    def _render(self, graph: "Graph", output_file: str, show: bool = False):
        """Render to pdf using pygraphviz"""

        try:
            import graphviz
        except ImportError as exc:
            raise RuntimeError(
                "PDF export requires 'pip install drawio-python[pdf]' and the Graphviz dot executable"
            ) from exc

        from pathlib import Path

        graph._complete_edges()
        visual_graph = graphviz.Digraph(name=graph.name, engine="dot", filename=output_file)

        for node in graph.nodes:
            node_name = self.__format_node_name(node.name)
            visual_graph.node(
                name=node.id,
                label=node_name,
                color="blue",
                fontcolor="white",
                shape=node.shape,
                style="filled",
            )

        for edge in graph.edges:
            visual_graph.edge(
                tail_name=edge.parent.id,
                head_name=edge.child.id,
                label=edge.label,
                color="red",
            )

        output_file_name = str(Path(output_file).with_suffix(""))
        visual_graph.format = "pdf"
        visual_graph.render(output_file_name, view=self.show)

        return output_file

    def __format_node_name(self, name):
        """Resolve buggy lke `fa:fa-car Car`

        In this case, return `Car`"""

        rgx = r"fa:fa-\w+ "
        return re.sub(rgx, "", name)
