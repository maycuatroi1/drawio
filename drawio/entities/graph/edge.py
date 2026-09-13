"""Legacy graph connections, compared by node identity rather than labels."""


class Edge:
    def __init__(self, parent, child, label=None):
        self.label = label
        self.parent = parent
        self.child = child

    def __rshift__(self, other):
        from drawio.entities.graph.node import Node

        if not isinstance(other, Node):
            return NotImplemented
        if self.child is not None:
            raise ValueError("This edge already has a target")
        graph = self.parent._graph_for(other)
        self.child = other
        graph.add_edge(self)
        return other

    def __repr__(self):
        child = self.child.name if self.child is not None else "?"
        if self.label:
            return f"{self.parent.name}--{self.label}-->{child}"
        return f"{self.parent.name}-->{child}"

    def __eq__(self, other):
        if not isinstance(other, Edge):
            return NotImplemented
        return (
            self.parent is other.parent and self.child is other.child and self.label == other.label
        )
