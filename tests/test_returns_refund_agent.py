from unittest.mock import Mock, patch

from DemoAgents.ReturnsRefund import agent as returns_agent


def test_given_missing_cosmos_config_when_building_history_then_uses_inmemory(monkeypatch):
    monkeypatch.delenv("COSMOS_ENDPOINT", raising=False)
    monkeypatch.delenv("COSMOS_KEY", raising=False)

    provider = returns_agent._create_history_provider()

    assert provider.__class__.__name__ == "InMemoryHistoryProvider"


def test_given_cosmos_config_when_building_history_then_uses_cosmos(monkeypatch):
    monkeypatch.setenv("COSMOS_ENDPOINT", "https://localhost:8081")
    monkeypatch.setenv("COSMOS_KEY", "test-key")
    mock_provider = Mock()
    mock_cosmos_client = Mock()

    with (
        patch.object(returns_agent, "CosmosClient", return_value=mock_cosmos_client),
        patch.object(returns_agent, "CosmosHistoryProvider", return_value=mock_provider),
    ):
        provider = returns_agent._create_history_provider()

    assert provider is mock_provider
    mock_cosmos_client.create_database_if_not_exists.assert_called_once_with("hackathon2026")


def test_given_unavailable_cosmos_when_building_history_then_uses_inmemory(monkeypatch):
    monkeypatch.setenv("COSMOS_ENDPOINT", "https://localhost:8081")
    monkeypatch.setenv("COSMOS_KEY", "test-key")
    mock_cosmos_client = Mock()
    mock_cosmos_client.create_database_if_not_exists.side_effect = RuntimeError("unavailable")

    with patch.object(returns_agent, "CosmosClient", return_value=mock_cosmos_client):
        provider = returns_agent._create_history_provider()

    assert provider.__class__.__name__ == "InMemoryHistoryProvider"
