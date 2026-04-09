from app.api import routes
from app.schemas.config import BackupRestoreRequest, ConfigApplyRequest, ConfigValidationRequest
from app.schemas.onion import OnionDeleteRequest, OnionServiceCreateRequest
from app.services.tunator_service import TunatorService


def test_health_endpoint_function() -> None:
    response = routes.health()
    assert response.status == 'ok'


def test_config_preview_and_apply_functions(service: TunatorService) -> None:
    preview = routes.preview_config(ConfigValidationRequest(updates={'SOCKSPort': '9057'}), service)
    assert preview.valid is True
    assert 'SOCKSPort 9057' in preview.diff

    apply_payload = ConfigApplyRequest(updates={'SOCKSPort': '9057'})
    applied = routes.apply_config(apply_payload, service)
    assert applied['success'] is True


def test_backup_restore_function(service: TunatorService) -> None:
    service.apply_config({'SOCKSPort': '9058'})
    backups = routes.list_backups(service)
    assert backups.items

    restored = routes.restore_backup(BackupRestoreRequest(backup_name=backups.items[0].name), service)
    assert restored['success'] is True


def test_onion_create_delete_functions(service: TunatorService) -> None:
    created = routes.create_onion(
        OnionServiceCreateRequest(name='site-routes', public_port=80, target_host='127.0.0.1', target_port=3000, access_password='segredo123'),
        service,
    )
    assert created.success is True

    deleted = routes.delete_onion('site-routes', OnionDeleteRequest(remove_directory=False), service)
    assert deleted.removed is True
