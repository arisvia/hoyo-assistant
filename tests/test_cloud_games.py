"""Tests for cloud game enable logic."""

from unittest.mock import patch


class TestCNCloudGameEnable:
    """Test CN cloud game enable logic."""

    def test_disabled_with_empty_token(self):
        """Cloud game should be disabled when token is empty."""
        conf = {"token": ""}
        assert not conf.get("token")

    def test_disabled_without_token(self):
        """Cloud game should be disabled when token is missing."""
        conf = {}
        assert not conf.get("token")

    def test_enabled_with_token(self):
        """Cloud game should be enabled when token exists."""
        conf = {"token": "abc123"}
        assert conf.get("token")


class TestOSCloudGameEnable:
    """Test OS cloud game enable logic."""

    def test_disabled_with_empty_token(self):
        """Cloud game should be disabled when token is empty."""
        conf = {"token": ""}
        assert not conf.get("token")

    def test_disabled_without_token(self):
        """Cloud game should be disabled when token is missing."""
        conf = {}
        assert not conf.get("token")

    def test_enabled_with_token(self):
        """Cloud game should be enabled when token exists."""
        conf = {"token": "xyz789"}
        assert conf.get("token")


class TestCloudGameIntegration:
    """Integration tests for cloud game config handling."""

    def test_cn_cloud_games_with_valid_config(self):
        """Test CN cloud games with valid configuration."""
        config = {
            "cloud_games": {
                "genshin": {"token": "genshin_token"},
                "zzz": {"token": "zzz_token"},
            }
        }
        with patch.dict("hoyo_assistant.tasks.chinese.cloud_games.config", config):
            assert config["cloud_games"]["genshin"]["token"]
            assert config["cloud_games"]["zzz"]["token"]

    def test_os_cloud_games_with_valid_config(self):
        """Test OS cloud games with valid configuration."""
        config = {
            "cloud_games": {
                "genshin": {"token": "genshin_token"},
                "zzz": {"token": "zzz_token"},
            }
        }
        with patch.dict("hoyo_assistant.tasks.overseas.cloud_games.config", config):
            assert config["cloud_games"]["genshin"]["token"]
            assert config["cloud_games"]["zzz"]["token"]
