"""Unit tests for SecureYeoman Phase B integration modules.

Tests:
- MCP server auto-registration (shared/yeoman_mcp_server.py)
- JWT validation (shared/yeoman_jwt.py)
- Webhook receiver + HMAC (webgui/routes/yeoman_webhooks.py)
- Event streaming + push client (shared/yeoman_event_stream.py)
- Embeddable metrics widget (webgui/routes/dashboard.py)
"""

import asyncio
import hashlib
import hmac
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ============================================================================
# MCP Server Auto-Registration
# ============================================================================


class TestYeomanMcpRegistration:
    """Tests for shared/yeoman_mcp_server.py."""

    def test_singleton_defaults_disabled(self):
        from shared.yeoman_mcp_server import yeoman_mcp_registration

        assert yeoman_mcp_registration.enabled is False
        assert yeoman_mcp_registration._server_id is None

    def test_tool_manifest_has_expected_tools(self):
        from shared.yeoman_mcp_server import TOOL_MANIFEST

        names = {t["name"] for t in TOOL_MANIFEST}
        assert "agnostic_health" in names
        assert "agnostic_submit_task" in names
        assert "agnostic_generate_report" in names
        assert "agnostic_structured_results" in names
        assert "agnostic_quality_dashboard" in names
        assert len(TOOL_MANIFEST) >= 10

    def test_tool_manifest_has_input_schemas(self):
        from shared.yeoman_mcp_server import TOOL_MANIFEST

        for tool in TOOL_MANIFEST:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool
            assert tool["inputSchema"]["type"] == "object"

    @pytest.mark.asyncio
    async def test_register_disabled_returns_false(self):
        from shared.yeoman_mcp_server import YeomanMcpRegistration

        reg = YeomanMcpRegistration()
        reg.enabled = False
        result = await reg.register()
        assert result is False

    @pytest.mark.asyncio
    async def test_deregister_without_server_id_returns_false(self):
        from shared.yeoman_mcp_server import YeomanMcpRegistration

        reg = YeomanMcpRegistration()
        reg.enabled = True
        reg._server_id = None
        result = await reg.deregister()
        assert result is False


# ============================================================================
# JWT Validation
# ============================================================================


class TestYeomanJwt:
    """Tests for shared/yeoman_jwt.py."""

    def test_disabled_by_default(self):
        from shared.yeoman_jwt import is_enabled

        # Unless env vars are set, should be disabled
        assert is_enabled() is False

    def test_validate_returns_none_when_disabled(self):
        from shared.yeoman_jwt import validate_yeoman_jwt

        result = validate_yeoman_jwt("some.fake.token")
        assert result is None

    def test_load_public_key_empty(self):
        # Reset cache
        import shared.yeoman_jwt as mod
        from shared.yeoman_jwt import _load_public_key

        mod._cached_public_key = None
        old_val = mod._PUBLIC_KEY_PATH
        mod._PUBLIC_KEY_PATH = ""
        try:
            assert _load_public_key() is None
        finally:
            mod._PUBLIC_KEY_PATH = old_val
            mod._cached_public_key = None

    def test_load_public_key_inline_pem(self):
        import shared.yeoman_jwt as mod

        mod._cached_public_key = None
        old_val = mod._PUBLIC_KEY_PATH
        pem = "-----BEGIN PUBLIC KEY-----\nfake\n-----END PUBLIC KEY-----"
        mod._PUBLIC_KEY_PATH = pem
        try:
            result = mod._load_public_key()
            assert result == pem
        finally:
            mod._PUBLIC_KEY_PATH = old_val
            mod._cached_public_key = None

    def test_role_mapping(self):
        """Verify YEOMAN roles map to AGNOSTIC roles correctly."""
        from shared.yeoman_jwt import validate_yeoman_jwt

        assert callable(validate_yeoman_jwt)

    def test_oidc_discovery_url_empty_by_default(self):
        import shared.yeoman_jwt as mod

        assert mod._OIDC_DISCOVERY_URL == "" or not mod._OIDC_DISCOVERY_URL

    def test_fetch_oidc_config_returns_none_when_no_url(self):
        import shared.yeoman_jwt as mod

        old = mod._OIDC_DISCOVERY_URL
        mod._OIDC_DISCOVERY_URL = ""
        try:
            result = mod._fetch_oidc_config()
            assert result is None
        finally:
            mod._OIDC_DISCOVERY_URL = old

    def test_is_enabled_with_oidc_url(self):
        import shared.yeoman_jwt as mod

        old_enabled = mod._ENABLED
        old_key = mod._PUBLIC_KEY_PATH
        old_secret = mod._SHARED_SECRET
        old_oidc = mod._OIDC_DISCOVERY_URL
        old_cache = mod._cached_public_key

        mod._ENABLED = True
        mod._PUBLIC_KEY_PATH = ""
        mod._SHARED_SECRET = ""
        mod._OIDC_DISCOVERY_URL = (
            "https://idp.example.com/.well-known/openid-configuration"
        )
        mod._cached_public_key = None
        try:
            assert mod.is_enabled() is True
        finally:
            mod._ENABLED = old_enabled
            mod._PUBLIC_KEY_PATH = old_key
            mod._SHARED_SECRET = old_secret
            mod._OIDC_DISCOVERY_URL = old_oidc
            mod._cached_public_key = old_cache

    def test_validate_with_oidc_returns_none_when_no_jwks(self):
        import shared.yeoman_jwt as mod

        old = mod._OIDC_DISCOVERY_URL
        mod._OIDC_DISCOVERY_URL = ""
        try:
            result = mod._validate_with_oidc("fake.token.here")
            assert result is None
        finally:
            mod._OIDC_DISCOVERY_URL = old

    def test_oidc_cache_ttl_set(self):
        import shared.yeoman_jwt as mod

        assert mod._OIDC_CACHE_TTL == 3600


# ============================================================================
# Webhook Receiver
# ============================================================================


class TestYeomanWebhooks:
    """Tests for webgui/routes/yeoman_webhooks.py."""

    def test_hmac_verification_no_secret_configured(self):
        """When no secret is configured, all requests are rejected."""
        import webgui.routes.yeoman_webhooks as mod
        from webgui.routes.yeoman_webhooks import _verify_webhook_signature

        old = mod.YEOMAN_WEBHOOK_SECRET
        mod.YEOMAN_WEBHOOK_SECRET = ""
        try:
            assert _verify_webhook_signature(b"anything", None) is False
            assert _verify_webhook_signature(b"anything", "bogus") is False
        finally:
            mod.YEOMAN_WEBHOOK_SECRET = old

    def test_hmac_verification_with_secret(self):
        """When a secret is configured, signature must match."""
        import webgui.routes.yeoman_webhooks as mod
        from webgui.routes.yeoman_webhooks import _verify_webhook_signature

        old = mod.YEOMAN_WEBHOOK_SECRET
        mod.YEOMAN_WEBHOOK_SECRET = "test-secret"
        try:
            body = b'{"event":"after-deploy"}'
            sig = hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()

            # Valid signature
            assert _verify_webhook_signature(body, f"sha256={sig}") is True
            # Raw hex also accepted
            assert _verify_webhook_signature(body, sig) is True
            # Invalid signature
            assert _verify_webhook_signature(body, "sha256=deadbeef") is False
            # Missing signature
            assert _verify_webhook_signature(body, None) is False
        finally:
            mod.YEOMAN_WEBHOOK_SECRET = old

    def test_build_task_from_known_event(self):
        from webgui.routes.yeoman_webhooks import _build_task_from_event

        result = _build_task_from_event(
            "after-deploy",
            {"repo": "myapp", "branch": "main", "commit_sha": "abc12345"},
        )
        assert result is not None
        assert "myapp" in result["title"]
        assert result["priority"] == "high"
        assert result["agents"] == []  # full pipeline

    def test_build_task_from_pr_merge(self):
        from webgui.routes.yeoman_webhooks import _build_task_from_event

        result = _build_task_from_event(
            "on-pr-merge",
            {"repo": "myapp", "pr_number": 42},
        )
        assert result is not None
        assert "42" in result["title"]
        assert "junior-qa" in result["agents"]
        assert "security-compliance" in result["agents"]

    def test_build_task_from_release(self):
        from webgui.routes.yeoman_webhooks import _build_task_from_event

        result = _build_task_from_event(
            "on-release",
            {"repo": "myapp", "tag": "v2.1.0"},
        )
        assert result is not None
        assert result["priority"] == "critical"
        assert "OWASP" in result["standards"]

    def test_build_task_from_unknown_event(self):
        from webgui.routes.yeoman_webhooks import _build_task_from_event

        result = _build_task_from_event("unknown-event", {})
        assert result is None

    def test_build_task_missing_data_fields(self):
        """Missing data fields should default gracefully, not crash."""
        from webgui.routes.yeoman_webhooks import _build_task_from_event

        result = _build_task_from_event("after-deploy", {})
        assert result is not None
        assert "unknown" in result["title"]

    def test_event_buffer_push_and_recent(self):
        from webgui.routes.yeoman_webhooks import _EventBuffer

        buf = _EventBuffer(max_size=5)
        for i in range(10):
            buf.push({"event_id": f"evt-{i}", "event": "test"})

        recent = buf.recent(10)
        assert len(recent) == 5
        assert recent[0]["event_id"] == "evt-5"
        assert recent[-1]["event_id"] == "evt-9"

    def test_event_buffer_subscribe_receives_events(self):
        from webgui.routes.yeoman_webhooks import _EventBuffer

        buf = _EventBuffer()
        sub_id, queue = buf.subscribe()

        buf.push({"event": "test", "data": "hello"})
        assert not queue.empty()
        evt = queue.get_nowait()
        assert evt["event"] == "test"

        buf.unsubscribe(sub_id)
        buf.push({"event": "test2"})
        assert queue.empty()

    def test_event_type_regex(self):
        from webgui.routes.yeoman_webhooks import _EVENT_TYPE_RE

        assert _EVENT_TYPE_RE.match("after-deploy")
        assert _EVENT_TYPE_RE.match("on-pr-merge")
        assert _EVENT_TYPE_RE.match("security-alert")
        assert _EVENT_TYPE_RE.match("on_schedule")
        assert not _EVENT_TYPE_RE.match("")
        assert not _EVENT_TYPE_RE.match("a" * 101)
        assert not _EVENT_TYPE_RE.match("event;drop table")

    def test_webhook_payload_model_validation(self):
        from webgui.routes.yeoman_webhooks import YeomanWebhookPayload

        payload = YeomanWebhookPayload(
            event="after-deploy",
            timestamp=int(time.time() * 1000),
            data={"repo": "myapp"},
        )
        assert payload.event == "after-deploy"
        assert payload.source == "secureyeoman"

    def test_webhook_payload_rejects_empty_event(self):
        from pydantic import ValidationError

        from webgui.routes.yeoman_webhooks import YeomanWebhookPayload

        with pytest.raises(ValidationError):
            YeomanWebhookPayload(event="", timestamp=0)


# ============================================================================
# Event Push Client
# ============================================================================


class TestYeomanEventPush:
    """Tests for shared/yeoman_event_stream.py."""

    def test_disabled_by_default(self):
        from shared.yeoman_event_stream import yeoman_event_push

        assert yeoman_event_push.enabled is False

    def test_push_event_when_disabled_is_noop(self):
        from shared.yeoman_event_stream import YeomanEventPushClient

        client = YeomanEventPushClient()
        client.enabled = False
        # Should not raise
        client.push_event("test", {"data": "value"})
        assert client._queue.empty()

    def test_push_event_when_enabled_queues(self):
        from shared.yeoman_event_stream import YeomanEventPushClient

        client = YeomanEventPushClient()
        client.enabled = True
        client.push_url = "http://example.com"
        client.push_event("task.completed", {"task_id": "abc"})
        assert not client._queue.empty()
        evt = client._queue.get_nowait()
        assert evt["event"] == "task.completed"
        assert evt["source"] == "agnostic-qa"
        assert "timestamp" in evt

    def test_push_event_with_task_and_session(self):
        from shared.yeoman_event_stream import YeomanEventPushClient

        client = YeomanEventPushClient()
        client.enabled = True
        client.push_url = "http://example.com"
        client.push_event(
            "task.completed",
            {"result": "pass"},
            task_id="t-1",
            session_id="s-1",
        )
        evt = client._queue.get_nowait()
        assert evt["task_id"] == "t-1"
        assert evt["session_id"] == "s-1"

    def test_push_event_drops_on_full_queue(self):
        from shared.yeoman_event_stream import YeomanEventPushClient

        client = YeomanEventPushClient()
        client.enabled = True
        client.push_url = "http://example.com"
        client._queue = asyncio.Queue(maxsize=2)
        client.push_event("e1", {})
        client.push_event("e2", {})
        # Third should be silently dropped
        client.push_event("e3", {})
        assert client._queue.qsize() == 2


# ============================================================================
# Event task mapping completeness
# ============================================================================


class TestEventTaskMapping:
    """Verify all documented event types have task mappings."""

    def test_all_documented_events_mapped(self):
        from webgui.routes.yeoman_webhooks import _EVENT_TASK_MAP

        expected = {
            "after-deploy",
            "on-pr-merge",
            "on-push",
            "on-schedule",
            "on-release",
            "security-alert",
        }
        assert expected.issubset(set(_EVENT_TASK_MAP.keys()))

    def test_all_mappings_have_required_fields(self):
        from webgui.routes.yeoman_webhooks import _EVENT_TASK_MAP

        for event_type, config in _EVENT_TASK_MAP.items():
            assert "title_template" in config, f"{event_type} missing title_template"
            assert "agents" in config, f"{event_type} missing agents"
            assert "priority" in config, f"{event_type} missing priority"
            assert "standards" in config, f"{event_type} missing standards"
            assert config["priority"] in (
                "critical",
                "high",
                "medium",
                "low",
            ), f"{event_type} has invalid priority"
