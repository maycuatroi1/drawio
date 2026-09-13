"""A small flowchart importer; unsupported syntax fails instead of losing edges."""

import json
import re

from drawio.entities.base_entity import BaseEntity
from drawio.entities.graph.graph import Graph
from drawio.entities.graph.node import Node

_SHAPES = [
    ("((", "))", "circle"),
    ("[[", "]]", "rectangle"),
    ("[", "]", "rectangle"),
    ("(", ")", "ellipse"),
    ("{", "}", "diamond"),
]
_ID = re.compile(r"[A-Za-z0-9_](?:[\w.]|-(?![-|>]))*")
_ARROW = re.compile(r"\s*(?:--\s*\|([^|]*)\|\s*-->|-->(?:\s*\|([^|]*)\|)?)\s*")


def _statements(text):
    start, depth, quoted, escaped = 0, 0, False, False
    for i, char in enumerate(text):
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[({":
            depth += 1
        elif char in "])}":
            depth -= 1
        elif char in ";\n" and depth == 0:
            yield text[start:i].strip()
            start = i + 1
    yield text[start:].strip()


class MermaidController(BaseEntity):
    valid_graph_types = ["flowchart", "graph"]

    def load(self, data):
        if not isinstance(data, str):
            raise TypeError("Mermaid input must be a string")
        data = "\n".join(line for line in data.splitlines() if not line.lstrip().startswith("%%"))
        header = re.match(r"\s*(flowchart|graph)\s+(TD|TB|BT|LR|RL)\b\s*;?", data)
        if header is None:
            raise ValueError("Expected a flowchart or graph header with a direction")
        graph = Graph(graph_type=header[1])
        for statement in _statements(data[header.end() :]):
            if not statement:
                continue
            parent, pos = self._node(statement, 0, graph)
            while statement[pos:].strip():
                arrow = _ARROW.match(statement, pos)
                if arrow is None:
                    raise ValueError(f"Unsupported Mermaid syntax: {statement[pos:]}")
                child, pos = self._node(statement, arrow.end(), graph)
                label = arrow[1] if arrow[1] is not None else arrow[2]
                if label:
                    parent >> label >> child
                else:
                    parent >> child
                parent = child
        if not graph.nodes:
            raise ValueError("The flowchart contains no nodes")
        return graph

    @staticmethod
    def _node(text, pos, graph):
        while pos < len(text) and text[pos].isspace():
            pos += 1
        match = _ID.match(text, pos)
        if match is None:
            raise ValueError(f"Expected a node at: {text[pos:]}")
        id, pos = match[0], match.end()
        while pos < len(text) and text[pos].isspace():
            pos += 1
        label, shape, explicit = id, "rectangle", False
        for opening, closing, candidate_shape in _SHAPES:
            if text.startswith(opening, pos):
                explicit, shape = True, candidate_shape
                start = pos + len(opening)
                if text.startswith('"', start):
                    try:
                        label, consumed = json.JSONDecoder().raw_decode(text[start:])
                    except ValueError as exc:
                        raise ValueError("Invalid quoted Mermaid label") from exc
                    end = start + consumed
                    if not text.startswith(closing, end):
                        raise ValueError("Missing closing shape delimiter")
                else:
                    end = text.find(closing, start)
                    if end < 0:
                        raise ValueError("Missing closing shape delimiter")
                    label = text[start:end]
                pos = end + len(closing)
                break
        node = graph.get_node(id)
        if node is None:
            node = graph.add_node(Node(label, id=id, shape=shape))
        elif explicit:
            node.name, node.shape = label, shape
        return node, pos
