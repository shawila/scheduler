from unittest.mock import patch, MagicMock
import pytest
from app.google_calendar import build_oauth_flow, SCOPES


class TestBuildOAuthFlow:
    def test_builds_flow_from_client_config_not_file(self, monkeypatch):
        monkeypatch.setenv('GOOGLE_CLIENT_ID', 'env-client-id')
        monkeypatch.setenv('GOOGLE_CLIENT_SECRET', 'env-client-secret')
        with patch('app.google_calendar.Flow.from_client_config') as mock_from_config, \
             patch('app.google_calendar.Flow.from_client_secrets_file') as mock_from_file:
            build_oauth_flow()
        mock_from_config.assert_called_once()
        mock_from_file.assert_not_called()

    def test_passes_client_id_and_secret_from_env(self, monkeypatch):
        monkeypatch.setenv('GOOGLE_CLIENT_ID', 'env-client-id')
        monkeypatch.setenv('GOOGLE_CLIENT_SECRET', 'env-client-secret')
        with patch('app.google_calendar.Flow.from_client_config') as mock_from_config:
            build_oauth_flow()
        client_config = mock_from_config.call_args.args[0]
        web_config = client_config['web']
        assert web_config['client_id'] == 'env-client-id'
        assert web_config['client_secret'] == 'env-client-secret'

    def test_uses_given_redirect_uri_when_provided(self, monkeypatch):
        monkeypatch.setenv('GOOGLE_CLIENT_ID', 'env-client-id')
        monkeypatch.setenv('GOOGLE_CLIENT_SECRET', 'env-client-secret')
        with patch('app.google_calendar.Flow.from_client_config') as mock_from_config:
            build_oauth_flow(redirect_uri='https://example.com/custom-callback')
        assert mock_from_config.call_args.kwargs['redirect_uri'] == 'https://example.com/custom-callback'

    def test_falls_back_to_default_redirect_uri(self, monkeypatch):
        monkeypatch.setenv('GOOGLE_CLIENT_ID', 'env-client-id')
        monkeypatch.setenv('GOOGLE_CLIENT_SECRET', 'env-client-secret')
        monkeypatch.delenv('OAUTH_REDIRECT_URI', raising=False)
        with patch('app.google_calendar.Flow.from_client_config') as mock_from_config:
            build_oauth_flow()
        assert mock_from_config.call_args.kwargs['redirect_uri'] == 'http://localhost:5000/callback'

    def test_missing_client_id_raises(self, monkeypatch):
        monkeypatch.delenv('GOOGLE_CLIENT_ID', raising=False)
        monkeypatch.setenv('GOOGLE_CLIENT_SECRET', 'env-client-secret')
        with pytest.raises(KeyError):
            build_oauth_flow()

    def test_missing_client_secret_raises(self, monkeypatch):
        monkeypatch.setenv('GOOGLE_CLIENT_ID', 'env-client-id')
        monkeypatch.delenv('GOOGLE_CLIENT_SECRET', raising=False)
        with pytest.raises(KeyError):
            build_oauth_flow()
