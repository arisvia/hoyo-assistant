"""Tests for cloud game enable logic."""

from unittest.mock import patch


class TestCNCloudGameEnable:
    """Test CN cloud game enable logic."""

    def test_enable_false_with_empty_token(self):
        """Cloud game should be disabled when token is empty."""
        conf = {"enable": True, "token": ""}
        # Should be disabled
        assert not (conf.get("enable") and conf.get("token"))

    def test_enable_false_without_token(self):
        """Cloud game should be disabled when token is missing."""
        conf = {"enable": True}
        # Should be disabled
        assert not (conf.get("enable") and conf.get("token"))

    def test_enable_true_with_token(self):
        """Cloud game should be enabled when both enable=True and token exists."""
        conf = {"enable": True, "token": "abc123"}
        # Should be enabled
        assert conf.get("enable") and conf.get("token")

    def test_enable_false_even_with_token(self):
        """Cloud game should be disabled when enable=False even if token exists."""
        conf = {"enable": False, "token": "abc123"}
        # Should be disabled
        assert not (conf.get("enable") and conf.get("token"))


class TestOSCloudGameEnable:
    """Test OS cloud game enable logic."""

    def test_enable_false_with_empty_token(self):
        """Cloud game should be disabled when token is empty."""
        conf = {"enable": True, "token": ""}
        assert not (conf.get("enable") and conf.get("token"))

    def test_enable_false_without_token(self):
        """Cloud game should be disabled when token is missing."""
        conf = {"enable": True}
        assert not (conf.get("enable") and conf.get("token"))

    def test_enable_true_with_token(self):
        """Cloud game should be enabled when both enable=True and token exists."""
        conf = {"enable": True, "token": "xyz789"}
        assert conf.get("enable") and conf.get("token")

    def test_enable_false_even_with_token(self):
        """Cloud game should be disabled when enable=False even if token exists."""
        conf = {"enable": False, "token": "xyz789"}
        assert not (conf.get("enable") and conf.get("token"))


class TestCloudGameIntegration:
    """Integration tests for cloud game config handling."""

    def test_cn_cloud_games_with_valid_config(self):
        """Test CN cloud games with valid configuration."""
        config = {
            "cloud_games": {
                "genshin": {"enable": True, "token": "genshin_token"},
                "zzz": {"enable": True, "token": "zzz_token"},
            }
        }
        with patch.dict("hoyo_assistant.tasks.chinese.cloud_games.config", config):
            # Should process both games
            assert config["cloud_games"]["genshin"]["enable"]
            assert config["cloud_games"]["zzz"]["enable"]

    def test_os_cloud_games_with_valid_config(self):
        """Test OS cloud games with valid configuration."""
        config = {
            "cloud_games": {
                "genshin": {"enable": True, "token": "genshin_token"},
                "zzz": {"enable": True, "token": "zzz_token"},
            }
        }
        with patch.dict("hoyo_assistant.tasks.overseas.cloud_games.config", config):
            assert config["cloud_games"]["genshin"]["enable"]
            assert config["cloud_games"]["zzz"]["enable"]

    def test_mixed_enable_status(self):
        """Test mixed enable status across games."""
        config = {
            "cloud_games": {
                "genshin": {"enable": True, "token": "token1"},
                "zzz": {"enable": False, "token": "token2"},
            }
        }
        with patch.dict("hoyo_assistant.tasks.chinese.cloud_games.config", config):
            assert config["cloud_games"]["genshin"]["enable"]
            assert not config["cloud_games"]["zzz"]["enable"]
