"""Legacy graph nodes and the ``>>`` connection DSL."""

from uuid import uuid4

from drawio.entities import config
from drawio.entities.graph.edge import Edge


class Node:
    def __init__(
        self,
        name,
        id=None,
        shape="ellipse",
        color="#000000",
        *,
        x=None,
        y=None,
        width=180,
        height=80,
    ):
        self.name = name
        self.id = id if id is not None else uuid4().hex
        self.children = []
        self.parents = []
        self.shape = shape
        self.color = color
        self.bg_color = "#FFFFFF"
        self.graph = config.GLOBAL_GRAPH
        self.x, self.y, self.width, self.height = x, y, width, height

    def _graph_for(self, other=None):
        from drawio.entities.graph.graph import Graph

        other_graph = other.graph if other is not None else None
        if self.graph is not None and other_graph is not None and self.graph is not other_graph:
            raise ValueError("Cannot connect nodes from different graphs")
        graph = self.graph or other_graph or Graph()
        graph.add_node(self)
        if other is not None:
            graph.add_node(other)
        return graph

    def __rshift__(self, other):
        if isinstance(other, Node):
            return self.add_child(other)
        if isinstance(other, list):
            for node in other:
                self.add_child(node)
            return None
        if isinstance(other, str):
            return self._graph_for().add_edge(Edge(self, None, other))
        return NotImplemented

    def add_child(self, child):
        if not isinstance(child, Node):
            raise TypeError("A child must be a Node")
        self._graph_for(child).add_edge(Edge(self, child))
        return child

    def add_parent(self, parent):
        parent.add_child(self)
        return parent

    def add_parent_edge(self, parent_edge):
        if parent_edge not in self.parents:
            self.parents.append(parent_edge)
        return parent_edge

    def __str__(self):
        return f"[{self.id}] - {self.name}"

    __repr__ = __str__

    def get_neighbours(self):
        return [edge.parent for edge in self.parents] + [
            edge.child for edge in self.children if edge.child is not None
        ]

    def get_edge(self, neighbour):
        return next(
            (
                edge
                for edge in self.parents + self.children
                if edge.parent is neighbour or edge.child is neighbour
            ),
            None,
        )

    def set_color(self, color, bg_color):
        self.color = color
        self.bg_color = bg_color
