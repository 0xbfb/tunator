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


def test_read_config_endpoint(client: TestClient) -> None:
    response = client.get('/api/config')
    assert response.status_code == 200
    payload = response.json()
    assert payload['parsed']['SOCKSPort'] == '9050'
    assert payload['base_options']['SOCKSPort'] == '9050'


def test_validate_config_endpoint(client: TestClient) -> None:
    response = client.post('/api/config/validate', json={'updates': {'SOCKSPort': '9055'}})
    assert response.status_code == 200
    assert response.json()['valid'] is True


def test_apply_config_rejects_invalid_update(client: TestClient) -> None:
    response = client.post('/api/config/apply', json={'updates': {'UnknownOption': '1'}})
    assert response.status_code == 400
    assert response.json()['detail']['success'] is False


def test_onion_create_and_list_endpoints(client: TestClient) -> None:
    create = client.post('/api/onions', json={
        'name': 'meu-site',
        'public_port': 80,
        'target_host': '127.0.0.1',
        'target_port': 3000,
    })
    assert create.status_code == 200
    payload = create.json()
    assert payload['item']['name'] == 'meu-site'

    listing = client.get('/api/onions')
    assert listing.status_code == 200
    assert listing.json()['items']


def test_logs_endpoint(client: TestClient) -> None:
    response = client.get('/api/logs')
    assert response.status_code == 200
    assert response.json()['entries']
