"""The existing Graph/Node DSL now saves files without opening Chrome."""

from drawio import Graph, Node


def build_graph():
    graph = Graph(name="Shopping")
    start = Node("Choose a gift", shape="rectangle")
    choice = Node("Compare options", shape="diamond")
    options = [Node(name, shape="rectangle") for name in ["Book", "Camera", "Bicycle"]]
    graph.add_nodes([start, choice, *options])
    start >> "browse" >> choice
    choice >> options
    return graph


if __name__ == "__main__":
    print(build_graph().render("shopping.drawio"))
