"""Le sole rotte senza credenziali dello studio: cio' che il cliente apre dal link.

Il codice del link arriva in un'intestazione, non nell'indirizzo: cosi' non
finisce nei log dei server ne' nella cronologia. Qualunque errore risponde con
lo stesso "non trovato", per non dire a chi prova codici se un link e' esistito.
"""
from fastapi import APIRouter, Header, Request, Response
from fastapi.responses import JSONResponse

from backend.api.errors import api_error_response
from backend.schemas.owner_dashboard import OwnerDashboard
from backend.workspace_services.owner_dashboard import DashboardNotFound, open_shared_dashboard

router = APIRouter(prefix="/v1/shared", tags=["shared"])

PRIVATE_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Robots-Tag": "noindex, nofollow",
}


@router.get("/process-dashboard", response_model=OwnerDashboard)
def get_shared_process_dashboard(
    request: Request,
    response: Response,
    x_delir_share_token: str = Header(default=""),
) -> OwnerDashboard | JSONResponse:
    """Il cruscotto del responsabile del processo, in sola lettura."""
    try:
        dashboard = open_shared_dashboard(x_delir_share_token)
    except DashboardNotFound:
        # Anche il "non trovato" non va in cache: lo stesso link puo' tornare valido.
        error = api_error_response(request, status_code=404, code="not_found", message="Link non valido o scaduto.")
        error.headers.update(PRIVATE_HEADERS)
        return error
    response.headers.update(PRIVATE_HEADERS)
    return dashboard
