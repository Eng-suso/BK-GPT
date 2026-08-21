from operator import add
from typing import Annotated

from backend.graphs.canvas_edit.state import CanvasState


class CanvasPatchEditState(CanvasState):
    patch_steps: Annotated[list[dict], add]
