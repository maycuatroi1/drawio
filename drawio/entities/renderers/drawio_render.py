"""Native .drawio rendering. Browser automation is not part of file creation."""

import webbrowser

from drawio.entities.renderers.base_render import BaseRender


class DrawIORender(BaseRender):
    file_type = "drawio"

    def _render(self, graph, output_file, show=False):
        document = graph.to_document()
        result = document.save(output_file, overwrite=True)
        if show:
            webbrowser.open(document.to_url())
        return str(result)
