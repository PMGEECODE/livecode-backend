from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings

def test_cors_allowed_explicit_origin():
    client = TestClient(app)
    # Origin from settings.cors_origins (e.g. https://livecode-client.vercel.app or localhost)
    # Let's check settings.cors_origins first
    allowed = settings.cors_origins
    if allowed and allowed[0] != "*":
        origin = allowed[0]
        response = client.options(
            "/",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == origin
        assert response.headers.get("access-control-allow-credentials") == "true"

def test_cors_allowed_vercel_subdomain():
    client = TestClient(app)
    # A vercel subdomain should match our cors_regex
    vercel_origin = "https://my-awesome-preview-deployment-123.vercel.app"
    response = client.options(
        "/",
        headers={
            "Origin": vercel_origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    # If settings.cors_origins is "*", all origins are allowed via ".*" regex
    # If not, our regex accepts *.vercel.app subdomains
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == vercel_origin
    assert response.headers.get("access-control-allow-credentials") == "true"

def test_cors_allowed_localhost_dynamic_ports():
    client = TestClient(app)
    # Localhost on any port
    localhost_origin = "http://localhost:12345"
    response = client.options(
        "/",
        headers={
            "Origin": localhost_origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == localhost_origin

def test_cors_disallowed_arbitrary_origin():
    # If settings.cors_origins is wildcard *, all origins match.
    # Otherwise, an arbitrary untrusted site should be blocked.
    if "*" not in settings.cors_origins:
        client = TestClient(app)
        malicious_origin = "https://malicious-untrusted-site.com"
        response = client.options(
            "/",
            headers={
                "Origin": malicious_origin,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        # For blocked CORS options request, access-control-allow-origin header should not be present
        assert "access-control-allow-origin" not in response.headers
