"""Tests for MaintenanceService database operations."""

from unittest.mock import MagicMock, patch

import pytest

from cbpos.core.services.maintenance_service import MaintenanceService


class TestMaintenanceService:
    """Unit tests for MaintenanceService."""

    def test_get_database_info_returns_dict(self, db_session):
        """Test that get_database_info returns expected keys."""
        info = MaintenanceService.get_database_info()
        assert "size" in info
        assert "products" in info
        assert "customers" in info
        assert "sales" in info

    def test_get_database_info_counts_are_integers(self, db_session):
        """Test that counts are non-negative integers."""
        info = MaintenanceService.get_database_info()
        assert isinstance(info["products"], int)
        assert isinstance(info["customers"], int)
        assert isinstance(info["sales"], int)
        assert info["products"] >= 0
        assert info["customers"] >= 0
        assert info["sales"] >= 0

    def test_integrity_check_passes(self, db_session):
        """Test that integrity check passes on a healthy database."""
        ok, message = MaintenanceService.integrity_check()
        assert ok is True
        assert message == "ok"

    def test_vacuum_database(self, tmp_path):
        """Test vacuum returns size info dict."""
        # Create a temporary database file for vacuum test
        db_file = tmp_path / "cbpos.db"
        db_file.write_text("x" * 1000)

        mock_conn = MagicMock()
        mock_engine = MagicMock()
        mock_engine.raw_connection.return_value = mock_conn

        with (
            patch("cbpos.core.services.maintenance_service.Config") as mock_config,
            patch("cbpos.core.services.maintenance_service.Database") as mock_db_cls,
        ):
            mock_config.BASE_DIR = tmp_path
            mock_config.DATA_DIR = tmp_path
            mock_db_cls.return_value = MagicMock(engine=mock_engine)

            result = MaintenanceService.vacuum_database()

        assert "size_before" in result
        assert "size_after" in result
        assert "saved" in result
        mock_conn.execute.assert_called_once_with("VACUUM")
        mock_conn.close.assert_called_once()

    def test_vacuum_closes_connection_on_error(self, tmp_path):
        """Test that vacuum closes the raw connection even on error."""
        db_file = tmp_path / "cbpos.db"
        db_file.write_text("x" * 100)

        mock_conn = MagicMock()
        mock_conn.execute.side_effect = Exception("vacuum error")
        mock_engine = MagicMock()
        mock_engine.raw_connection.return_value = mock_conn

        with (
            patch("cbpos.core.services.maintenance_service.Config") as mock_config,
            patch("cbpos.core.services.maintenance_service.Database") as mock_db_cls,
        ):
            mock_config.BASE_DIR = tmp_path
            mock_config.DATA_DIR = tmp_path
            mock_db_cls.return_value = MagicMock(engine=mock_engine)

            with pytest.raises(Exception, match="vacuum error"):
                MaintenanceService.vacuum_database()

        mock_conn.close.assert_called_once()

    def test_issue_839_network_mode_vacuum_refused(self, monkeypatch):
        """vacuum_database raises MaintenanceError('network_mode') when db_mode is network."""
        from cbpos.core.services.config_service import ConfigService
        from cbpos.core.services.maintenance_service import MaintenanceError

        monkeypatch.setattr(ConfigService, "get", lambda key, default=None: "network" if key == "db_mode" else default)
        with pytest.raises(MaintenanceError) as exc:
            MaintenanceService.vacuum_database()
        assert exc.value.code == "network_mode"

    def test_issue_839_network_mode_integrity_check_refused(self, monkeypatch):
        """integrity_check raises MaintenanceError('network_mode') when db_mode is network."""
        from cbpos.core.services.config_service import ConfigService
        from cbpos.core.services.maintenance_service import MaintenanceError

        monkeypatch.setattr(ConfigService, "get", lambda key, default=None: "network" if key == "db_mode" else default)
        with pytest.raises(MaintenanceError) as exc:
            MaintenanceService.integrity_check()
        assert exc.value.code == "network_mode"

    def test_issue_839_network_mode_database_info_refused(self, monkeypatch):
        """get_database_info raises MaintenanceError('network_mode') when db_mode is network."""
        from cbpos.core.services.config_service import ConfigService
        from cbpos.core.services.maintenance_service import MaintenanceError

        monkeypatch.setattr(ConfigService, "get", lambda key, default=None: "network" if key == "db_mode" else default)
        with pytest.raises(MaintenanceError) as exc:
            MaintenanceService.get_database_info()
        assert exc.value.code == "network_mode"
