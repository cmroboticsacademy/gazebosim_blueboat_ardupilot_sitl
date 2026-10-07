"""Static and pure-math tests for the Mission 4 findings map."""

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "gz_ws/src/move_blueboat"


def load_geo_module():
    path = PKG / "move_blueboat/mission4_geo.py"
    spec = importlib.util.spec_from_file_location("mission4_geo_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class Mission4FindingsTests(unittest.TestCase):
    def test_replay_odom_axes_map_directly_to_east_and_north(self):
        geo = load_geo_module()
        lat0 = 40.595009
        lon0 = -79.999740

        lat, lon = geo.local_to_wgs84(0.0, 0.0, lat0, lon0, 0.0)
        self.assertAlmostEqual(lat, lat0, places=10)
        self.assertAlmostEqual(lon, lon0, places=10)

        _, east_lon = geo.local_to_wgs84(
            10.0, 0.0, lat0, lon0, 0.0
        )
        north_lat, _ = geo.local_to_wgs84(
            0.0, 10.0, lat0, lon0, 0.0
        )
        self.assertGreater(east_lon, lon0)
        self.assertGreater(north_lat, lat0)

    def test_web_node_contract_and_assets_are_installed(self):
        setup = (PKG / "setup.py").read_text()
        node = (PKG / "move_blueboat/mission4_findings_web.py").read_text()
        launch = (PKG / "launch/mission4_findings.launch.py").read_text()
        index = (PKG / "findings_web/index.html").read_text()
        app = (PKG / "findings_web/app.js").read_text()

        self.assertIn("findings_web/*", setup)
        self.assertIn("mission4_findings_web:main", setup)
        self.assertIn('"/clicked_point"', node)
        for boat in ("blueboat", "blueboat2", "blueboat3", "blueboat4"):
            self.assertIn(f'"/model/{boat}/odometry"', node)
        self.assertIn('executable="mission4_findings_web"', launch)
        self.assertIn(
            'DeclareLaunchArgument("heading_deg", default_value="0.0")',
            launch,
        )
        self.assertIn("World_Imagery", app)
        self.assertIn("/api/state", app)
        self.assertIn("Publish Point", index)

    def test_findings_polling_does_not_overwrite_unsaved_form(self):
        app = (PKG / "findings_web/app.js").read_text()

        self.assertIn("var formDirty = false;", app)
        self.assertIn("} else if (!formDirty) {", app)
        self.assertIn("function markFormDirty()", app)
        self.assertIn('formMessage.textContent = "Unsaved changes.";', app)
        self.assertIn("&& !formDirty", app)
        self.assertIn("formDirty = false;", app)


if __name__ == "__main__":
    unittest.main()
