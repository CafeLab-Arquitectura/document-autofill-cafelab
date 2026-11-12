def test_health_returns_up(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "UP"}


def test_unknown_route_uses_message_format(client):
    response = client.get("/no-existe")

    assert response.status_code == 404
    assert set(response.json()) == {"message"}
