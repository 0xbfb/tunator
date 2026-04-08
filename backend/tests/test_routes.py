from fastapi.testclient import TestClient


def test_health_endpoint(client: TestClient) -> None:
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


def test_environment_endpoint_exposes_local_runtime_info(client: TestClient) -> None:
    response = client.get('/api/environment')
    assert response.status_code == 200
    payload = response.json()
    assert payload['service_available'] is False
    assert payload['tor_source'] in {'missing', 'project-bundled', 'explicit-env'}
    assert payload['supported_platform'] in {True, False}


def test_preview_and_apply_config_endpoints(client: TestClient) -> None:
    preview = client.post('/api/config/preview', json={'updates': {'SOCKSPort': '9055'}})
    assert preview.status_code == 200
    assert preview.json()['valid'] is True
    assert 'SOCKSPort 9055' in preview.json()['diff']

    apply_res = client.post('/api/config/apply', json={'updates': {'SOCKSPort': '9055'}})
    assert apply_res.status_code == 200
    assert apply_res.json()['success'] is True


def test_backups_list_endpoint(client: TestClient) -> None:
    client.post('/api/config/apply', json={'updates': {'SOCKSPort': '9056'}})
    response = client.get('/api/config/backups')
    assert response.status_code == 200
    assert 'items' in response.json()


def test_onion_create_and_delete_endpoint(client: TestClient) -> None:
    create = client.post('/api/onions', json={
        'name': 'meu-site',
        'public_port': 80,
        'target_host': '127.0.0.1',
        'target_port': 3000,
        'access_password': 'segredo123',
    })
    assert create.status_code == 200
    payload = create.json()
    assert payload['item']['name'] == 'meu-site'

    delete = client.request('DELETE', '/api/onions/meu-site', json={'remove_directory': False})
    assert delete.status_code == 200


def test_logs_endpoint(client: TestClient) -> None:
    response = client.get('/api/logs')
    assert response.status_code == 200
    assert response.json()['entries']
    entry = response.json()['entries'][0]
    assert 'raw' in entry
    assert 'message' in entry
