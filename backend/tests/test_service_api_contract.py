from app.services.tunator_service import TunatorService


def test_health_like_status(service: TunatorService) -> None:
    status = service.get_status()
    assert status.source
    assert status.status in {'stopped', 'starting', 'running', 'failed', 'restarting', 'stopping'}


def test_environment_exposes_runtime_info(service: TunatorService) -> None:
    env = service.get_environment()
    assert env.tor_source in {'missing', 'project-bundled', 'explicit-env'}
    assert env.supported_platform in {True, False}


def test_preview_and_apply_config(service: TunatorService) -> None:
    preview = service.preview_config({'SOCKSPort': '9055'})
    assert preview['valid'] is True
    assert 'SOCKSPort 9055' in preview['diff']

    apply_res = service.apply_config({'SOCKSPort': '9055'})
    assert apply_res['success'] is True


def test_backups_and_restore(service: TunatorService) -> None:
    service.apply_config({'SOCKSPort': '9056'})
    backups = service.list_backups()
    assert backups
    restored = service.restore_backup(backups[0]['name'])
    assert restored['torrc_path']


def test_onion_create_and_delete(service: TunatorService) -> None:
    created = service.create_onion_service(
        name='meu-site',
        public_port=80,
        target_host='127.0.0.1',
        target_port=3000,
        access_password='segredo123',
    )
    assert created.item.name == 'meu-site'

    removed = service.delete_onion_service('meu-site', remove_directory=False)
    assert removed.removed is True


def test_logs_shape(service: TunatorService) -> None:
    logs = service.read_logs(limit=10)
    assert logs.entries
    assert logs.entries[0].raw
    assert hasattr(logs.entries[0], 'message')
