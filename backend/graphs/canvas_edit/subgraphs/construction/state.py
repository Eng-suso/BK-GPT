from operator import add
from typing import Annotated

from backend.graphs.canvas_edit.state import CanvasState


class CanvasConstructionState(CanvasState):
    construction_steps: Annotated[list[dict], add]
