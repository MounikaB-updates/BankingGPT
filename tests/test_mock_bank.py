from fastapi.testclient import TestClient

from banking_gpt.mock_bank import app

client = TestClient(app)


def test_search_page() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Member ID" in response.text


def test_member_details() -> None:
    response = client.get("/members/12345")
    assert response.status_code == 200
    assert "$1,250.00" in response.text
    assert "Alex Example" in response.text
    assert "Active" in response.text
    assert "Recent Transactions" in response.text


def test_recent_transactions() -> None:
    response = client.get("/members/12345/transactions")
    assert response.status_code == 200
    assert "Payroll deposit" in response.text
    assert "+$2,400.00" in response.text


def test_no_recent_transactions_is_business_outcome() -> None:
    response = client.get("/members/40800/transactions")
    assert response.status_code == 200
    assert "no-recent-transactions" in response.text


def test_legacy_tenant_shells_use_different_frame_ids() -> None:
    northstar = client.get("/legacy/northstar")
    harbor = client.get("/legacy/harbor")
    assert 'id="core-frame"' in northstar.text
    assert 'id="banking-workspace"' in harbor.text


def test_legacy_member_page_is_rendered_inside_frame_route() -> None:
    response = client.get("/legacy/northstar/members/12345")
    assert response.status_code == 200
    assert "legacy-checking-balance" in response.text
    assert "$1,250.00" in response.text


def test_member_not_found_is_explicit() -> None:
    response = client.get("/members/99999")
    assert response.status_code == 404
    assert "member-not-found" in response.text


def test_permission_denied_is_explicit() -> None:
    response = client.get("/members/40300")
    assert response.status_code == 403
    assert "permission-denied" in response.text


def test_session_expiry_can_resume() -> None:
    expired = client.get("/members/40800")
    resumed = client.get("/members/40800?resumed=true")
    assert "session-expired" in expired.text
    assert resumed.status_code == 200
    assert "$408.00" in resumed.text


def test_transient_error_can_retry() -> None:
    failed = client.get("/members/50000")
    retried = client.get("/members/50000?retried=true")
    assert failed.status_code == 503
    assert "transient-load-error" in failed.text
    assert "$500.00" in retried.text


def test_known_interstitial_can_continue() -> None:
    notice = client.get("/members/77777")
    continued = client.get("/members/77777?continued=true")
    assert "known-interstitial" in notice.text
    assert "$777.77" in continued.text


def test_unknown_error_has_no_automatic_resolution() -> None:
    response = client.get("/members/66666")
    assert response.status_code == 500
    assert "unknown-application-error" in response.text
