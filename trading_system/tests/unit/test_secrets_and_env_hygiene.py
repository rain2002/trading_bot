import os
import re
import pytest

from trading_system.app.broker.groww import GrowwBrokerAdapter
from trading_system.app.broker.alpaca import AlpacaBrokerAdapter
from trading_system.app.notifications.notifier import QuantNotifier


def test_gitignore_firmly_ignores_secrets():
    """Asserts that .gitignore firmly blocks .env files and secret artifacts."""
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    gitignore_path = os.path.join(root_dir, ".gitignore")
    assert os.path.isfile(gitignore_path), ".gitignore must exist in project root"

    with open(gitignore_path, "r", encoding="utf-8") as f:
        content = f.read()

    lines = [line.strip() for line in content.splitlines() if line.strip() and not line.startswith("#")]
    assert ".env" in lines
    assert ".env.*" in lines or "*.env" in lines
    assert "!.env.example" in lines


def test_requirements_dependencies_pinned():
    """Asserts that requirements.txt has pinned deterministic versions (==) without floating >= operators."""
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    req_path = os.path.join(root_dir, "requirements.txt")
    assert os.path.isfile(req_path), "requirements.txt must exist in project root"

    with open(req_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    assert len(lines) > 10, "requirements.txt must contain required dependencies"

    floating_deps = []
    for dep in lines:
        if ">=" in dep or ">" in dep or "~=" in dep or "<=" in dep or "<" in dep:
            floating_deps.append(dep)
        elif "==" not in dep:
            floating_deps.append(dep)

    assert not floating_deps, f"Found unpinned or floating dependencies in requirements.txt: {floating_deps}"


def test_groww_broker_environment_variable_ingestion(monkeypatch):
    """Asserts Groww broker adapter ingests credentials from environment variables."""
    monkeypatch.setenv("GROWW_API_KEY", "env_groww_key_123")
    monkeypatch.setenv("GROWW_API_SECRET", "env_groww_secret_456")
    monkeypatch.setenv("GROWW_AUTH_TOKEN", "env_groww_token_789")
    monkeypatch.setenv("GROWW_BASE_URL", "https://api.custom-groww.in")

    adapter = GrowwBrokerAdapter(is_live=False)
    assert adapter.api_key == "env_groww_key_123"
    assert adapter.api_secret == "env_groww_secret_456"
    assert adapter.totp_secret == "env_groww_token_789"
    assert adapter.base_url == "https://api.custom-groww.in"


def test_alpaca_broker_environment_variable_ingestion(monkeypatch):
    """Asserts Alpaca broker adapter ingests credentials from environment variables."""
    monkeypatch.setenv("ALPACA_API_KEY", "env_alpaca_key_abc")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "env_alpaca_secret_def")
    monkeypatch.setenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

    adapter = AlpacaBrokerAdapter()
    assert adapter.api_key == "env_alpaca_key_abc"
    assert adapter.api_secret == "env_alpaca_secret_def"
    assert adapter.base_url == "https://paper-api.alpaca.markets"


def test_quant_notifier_environment_variable_ingestion(monkeypatch):
    """Asserts QuantNotifier ingests DISCORD_WEBHOOK_URL from environment variables."""
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/mock_test_url")
    notifier = QuantNotifier()
    assert notifier.discord_url == "https://discord.com/api/webhooks/mock_test_url"
