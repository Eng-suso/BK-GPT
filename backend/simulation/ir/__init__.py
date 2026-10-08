"""Simulation IR: il modello di simulazione di DeliR e la sua traduzione verso il motore.

``compile_for_prosimos`` e ``model_from_request`` si caricano solo quando
servono: ``model_from_request`` importa ``backend.schemas.simulation``, che a
sua volta tipizza la ``model_patch`` della richiesta v1 con ``ir.patch``. Con
gli import diretti qui i due moduli si chiamerebbero in cerchio.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from backend.simulation.ir.model import SCHEMA_VERSION, SimulationModel

if TYPE_CHECKING:
    from backend.simulation.ir.compile import compile_for_prosimos
    from backend.simulation.ir.from_request import model_from_request

__all__ = ["SCHEMA_VERSION", "SimulationModel", "compile_for_prosimos", "model_from_request"]


def __getattr__(name: str) -> Any:
    if name == "compile_for_prosimos":
        from backend.simulation.ir.compile import compile_for_prosimos

        return compile_for_prosimos
    if name == "model_from_request":
        from backend.simulation.ir.from_request import model_from_request

        return model_from_request
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
