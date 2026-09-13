"""Backward-compatible Graph API with an offline native XML renderer."""

import csv
import io
from pathlib import Path

from drawio.document import Document
from drawio.entities.base_entity import BaseEntity
from drawio.entities.drawio_config.drawio_config import DrawIOConfig

DRAWIO_SHAPES = {
    "table": "mxgraph.dfd.data",
    "circle": "ellipse",
    "oval": "ellipse",
    "diamond": "rhombus",
}


class Graph(BaseEntity):
    def __init__(self, single_node=None, graph_type="flowchart", name=None):
        super().__init__()
        self.name = name or "Graph Name"
        self.graph_type = graph_type
        self.nodes = []
        self.edges = []
        if single_node is not None:
            self.add_node(single_node)

    def add_nodes(self, nodes):
        for node in nodes:
            self.add_node(node)

    def add_node(self, node):
        if node.graph is not None and node.graph is not self:
            raise ValueError("Node already belongs to another graph")
        if not isinstance(node.id, str) or not node.id.strip():
            raise ValueError("Node ID must be a nonempty string")
        if any(n.id == node.id and n is not node for n in self.nodes):
            raise ValueError(f"Duplicate node ID: {node.id}")
        node.graph = self
        if node not in self.nodes:
            self.nodes.append(node)
        return node

    def add_edge(self, edge):
        self.add_node(edge.parent)
        if edge.child is not None:
            self.add_node(edge.child)
        existing = next((e for e in self.edges if e == edge), None)
        edge = existing if existing is not None else edge
        if existing is None:
            self.edges.append(edge)
        else:
            # Completing a pending labelled edge can duplicate an earlier edge.
            self.edges[:] = [e for e in self.edges if e is edge or e != edge]
            edge.parent.children[:] = [e for e in edge.parent.children if e is edge or e != edge]
            if edge.child is not None:
                edge.child.parents[:] = [e for e in edge.child.parents if e is edge or e != edge]
        if edge not in edge.parent.children:
            edge.parent.children.append(edge)
        if edge.child is not None:
            edge.child.add_parent_edge(edge)
        return edge

    def get_node(self, node_id):
        return next((node for node in self.nodes if node.id == node_id), None)

    def _complete_edges(self):
        for edge in self.edges:
            if edge.child is None:
                raise ValueError(f"Unfinished edge from {edge.parent.id}; add its target")
        return self.edges

    def to_draw_io(self):
        """Retain the legacy text format, distinct from native XML."""
        return "".join(
            f"{e.parent.name}->{e.label + '->' if e.label else ''}{e.child.name}\n"
            for e in self._complete_edges()
        )

    def to_draw_io_csv(self, drawio_config=None):
        """Retain CSV export with escaped labels and consistent column counts."""
        config = drawio_config if drawio_config is not None else DrawIOConfig()
        self._complete_edges()
        output = io.StringIO(newline="")
        output.write("## type:csv\n## Build with Drawio-python\n# style: shape=%shape%\n")
        output.write(config.to_config_string())
        writer = csv.writer(output, lineterminator="\n")
        for node in self.nodes:
            incoming = [e.parent.id for e in self.edges if e.child is node]
            outgoing = [e.child.id for e in self.edges if e.parent is node]
            writer.writerow(
                [
                    node.id,
                    node.name,
                    "",
                    DRAWIO_SHAPES.get(node.shape, node.shape),
                    ",".join(incoming),
                    ",".join(outgoing),
                    node.color,
                    node.bg_color,
                ]
            )
        return output.getvalue()

    def to_document(self):
        """Convert to a native document, using a simple grid for unpositioned nodes."""
        self._complete_edges()
        document = Document()
        page = document.add_page(self.name)
        positions = {}
        reserved_aliases = set(node.id for node in self.nodes)
        # A predictable fallback, including cycles and disconnected graphs.
        cell_width = max((node.width for node in self.nodes), default=180) + 80
        cell_height = max((node.height for node in self.nodes), default=80) + 90
        for i, node in enumerate(self.nodes):
            shape = DRAWIO_SHAPES.get(node.shape, node.shape)
            xml_id = node.id
            if xml_id in ("0", "1"):
                xml_id = f"node-{xml_id}"
                while xml_id in reserved_aliases:
                    xml_id = "node-" + xml_id
                reserved_aliases.add(xml_id)
            positions[node.id] = page.box(
                node.name,
                node.x if node.x is not None else 40 + (i % 3) * cell_width,
                node.y if node.y is not None else 40 + (i // 3) * cell_height,
                node.width,
                node.height,
                id=xml_id,
                style={"shape": shape, "fontColor": node.color, "fillColor": node.bg_color},
            )
        for edge in self.edges:
            page.connect(positions[edge.parent.id], positions[edge.child.id], edge.label or "")
        return document

    def to_draw_io_xml(self):
        return self.to_document().to_xml()

    def render(self, file_name, show=False):
        from drawio.entities.renderers import renderers

        file_type = Path(file_name).suffix.lstrip(".").lower()
        renderer_class = renderers.get(file_type)
        if renderer_class is None:
            raise NotImplementedError(f"File type '{file_type}' is not supported.")
        return renderer_class().render(graph=self, output_file=str(file_name), show=show)
