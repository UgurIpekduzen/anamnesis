from starlette.testclient import TestClient

import api.main as api_main


def test_every_response_carries_the_security_headers():
    response = TestClient(api_main.app).get("/health")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"


def test_the_content_security_policy_is_enforced():
    # It ran report-only first and showed no violation on the live app (sign-in,
    # sign-out, chat, saving a fact), so it is enforced now (APPCE-119).
    response = TestClient(api_main.app).get("/health")

    assert "content-security-policy-report-only" not in response.headers
    policy = response.headers["content-security-policy"]
    assert "default-src 'self'" in policy
    assert "frame-ancestors 'none'" in policy
    # What Google sign-in needs, and nothing broader.
    assert "https://accounts.google.com/gsi/client" in policy
    assert "'unsafe-eval'" not in policy


def test_an_error_response_carries_them_too():
    response = TestClient(api_main.app).get("/tenants")  # 401: no token

    assert response.status_code == 401
    assert response.headers["x-content-type-options"] == "nosniff"
