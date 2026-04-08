from fastapi import APIRouter, Depends, HTTPException, Request

from app.schemas.config import ConfigApplyRequest, ConfigReadResponse, ConfigValidationRequest, ConfigValidationResponse
from app.schemas.diagnostics import DiagnosticsResponse
from app.schemas.environment import EnvironmentInfo
from app.schemas.logs import LogResponse
from app.schemas.onion import (
    OnionServiceCreateRequest,
    OnionServiceCreateResponse,
    OnionServiceDeleteResponse,
    OnionServiceListResponse,
)
from app.schemas.service import HealthResponse, ServiceActionResponse, ServiceStatusResponse
from app.services.tunator_service import TunatorService

router = APIRouter()


def get_tunator_service(request: Request) -> TunatorService:
    return request.app.state.tunator


@router.get('/health', response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status='ok')


@router.get('/api/environment', response_model=EnvironmentInfo)
def environment(service: TunatorService = Depends(get_tunator_service)) -> EnvironmentInfo:
    return service.get_environment()


@router.get('/api/status', response_model=ServiceStatusResponse)
def status(service: TunatorService = Depends(get_tunator_service)) -> ServiceStatusResponse:
    return service.get_status()


@router.get('/api/config', response_model=ConfigReadResponse)
def read_config(service: TunatorService = Depends(get_tunator_service)) -> ConfigReadResponse:
    return service.read_config()


@router.post('/api/config/validate', response_model=ConfigValidationResponse)
def validate_config(
    payload: ConfigValidationRequest,
    service: TunatorService = Depends(get_tunator_service),
) -> ConfigValidationResponse:
    return service.validate_config(payload.updates)


@router.post('/api/config/apply')
def apply_config(
    payload: ConfigApplyRequest,
    service: TunatorService = Depends(get_tunator_service),
) -> dict:
    result = service.apply_config(payload.updates)
    if not result['success']:
        raise HTTPException(status_code=400, detail=result)
    return result


@router.get('/api/onions', response_model=OnionServiceListResponse)
def list_onions(service: TunatorService = Depends(get_tunator_service)) -> OnionServiceListResponse:
    return service.list_onion_services()


@router.post('/api/onions', response_model=OnionServiceCreateResponse)
def create_onion(
    payload: OnionServiceCreateRequest,
    service: TunatorService = Depends(get_tunator_service),
) -> OnionServiceCreateResponse:
    try:
        return service.create_onion_service(
            name=payload.name,
            public_port=payload.public_port,
            target_host=payload.target_host,
            target_port=payload.target_port,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={'success': False, 'message': str(exc)}) from exc


@router.delete('/api/onions/{name}', response_model=OnionServiceDeleteResponse)
def delete_onion(name: str, service: TunatorService = Depends(get_tunator_service)) -> OnionServiceDeleteResponse:
    try:
        return service.delete_onion_service(name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={'success': False, 'message': str(exc)}) from exc


@router.get('/api/logs', response_model=LogResponse)
def logs(service: TunatorService = Depends(get_tunator_service), limit: int = 200) -> LogResponse:
    return service.read_logs(limit=limit)


@router.post('/api/diagnostics/run', response_model=DiagnosticsResponse)
def run_diagnostics(service: TunatorService = Depends(get_tunator_service)) -> DiagnosticsResponse:
    return service.run_diagnostics()


@router.post('/api/service/start', response_model=ServiceActionResponse)
def start_service(service: TunatorService = Depends(get_tunator_service)) -> ServiceActionResponse:
    return service.start_service()


@router.post('/api/service/stop', response_model=ServiceActionResponse)
def stop_service(service: TunatorService = Depends(get_tunator_service)) -> ServiceActionResponse:
    return service.stop_service()


@router.post('/api/service/restart', response_model=ServiceActionResponse)
def restart_service(service: TunatorService = Depends(get_tunator_service)) -> ServiceActionResponse:
    return service.restart_service()
