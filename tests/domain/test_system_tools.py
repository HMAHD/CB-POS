from unittest.mock import patch

from cbpos.infrastructure.system_tools import open_native_calculator


class TestOpenNativeCalculator:
    def test_darwin_launches_calculator_app(self):
        with (
            patch("platform.system", return_value="Darwin"),
            patch("subprocess.Popen") as mock_popen,
        ):
            assert open_native_calculator() is True
            mock_popen.assert_called_once_with(["open", "-a", "Calculator"])

    def test_windows_launches_calc_exe(self):
        with (
            patch("platform.system", return_value="Windows"),
            patch("subprocess.Popen") as mock_popen,
        ):
            assert open_native_calculator() is True
            mock_popen.assert_called_once_with(["calc.exe"], shell=True)

    def test_linux_launches_found_calculator(self):
        def fake_which(cmd):
            if cmd == "kcalc":
                return "/usr/bin/kcalc"
            return None

        with (
            patch("platform.system", return_value="Linux"),
            patch("shutil.which", side_effect=fake_which),
            patch("subprocess.Popen") as mock_popen,
        ):
            assert open_native_calculator() is True
            mock_popen.assert_called_once_with(["kcalc"])

    def test_linux_falls_back_to_xcalc_when_no_match(self):
        with (
            patch("platform.system", return_value="Linux"),
            patch("shutil.which", return_value=None),
            patch("subprocess.Popen") as mock_popen,
        ):
            assert open_native_calculator() is True
            mock_popen.assert_called_once_with(["xcalc"])

    def test_handles_exception_gracefully(self):
        with (
            patch("platform.system", return_value="Darwin"),
            patch("subprocess.Popen", side_effect=OSError("Binary not found")),
        ):
            assert open_native_calculator() is False
