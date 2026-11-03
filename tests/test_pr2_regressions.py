import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "controller"))
sys.path.insert(0, str(ROOT / "tests"))

import cdn_controller
from cdn_controller import CDN
from paths import Hop, Route
from run_scenarios import parse_args, pick_congested_server


class AdaptiveScenarioTests(unittest.TestCase):
    def test_adaptive_scenario_rejects_static_mode(self):
        with patch.object(sys, "argv", ["run_scenarios.py", "adaptive-congestion", "--mode", "static"]):
            with self.assertRaises(SystemExit) as error:
                parse_args()
        self.assertEqual(error.exception.code, 2)

    def test_random_congestion_seed_replays_the_same_condition(self):
        self.assertEqual([pick_congested_server(seed) for seed in (42, 43, 44, 45)],
                         [None, None, "srv3", "srv2"])


class RouteVisualizerTests(unittest.TestCase):
    def test_visualizer_renders_route_data_as_text_not_html(self):
        page = (ROOT / "tools" / "route_map.html").read_text(encoding="utf-8")
        self.assertNotIn("card.innerHTML", page)
        self.assertIn("heading.textContent = route.name", page)

    def test_flow_move_updates_latest_route_event(self):
        old_route = SimpleNamespace(name="srv1-direct", server="srv1", hops=[])
        new_route = SimpleNamespace(name="srv1-backup", server="srv1", hops=[])
        flow = SimpleNamespace(ip="10.0.0.1", port=4321, route=old_route)
        controller = CDN.__new__(CDN)
        controller.last_route_event = None
        controller.install = lambda _flow: None
        controller.remove_rules = lambda *_args, **_kwargs: None
        controller.logger = SimpleNamespace(info=lambda *_args: None)

        with patch.object(cdn_controller.time, "time", return_value=123.0):
            controller.move(flow, new_route, "path degraded")

        self.assertEqual(controller.last_route_event, {
            "time": 123.0,
            "client": "10.0.0.1",
            "server": "srv1",
            "route": "srv1-backup",
        })

    def test_switch_reconnect_clears_only_its_stale_down_ports(self):
        route = Route("test", "srv1", [Hop(1, 5, None, 100e6), Hop(2, 1, 2, 100e6)])
        route.ports_down = {(1, 5), (2, 1)}

        route.clear_switch_ports(1)

        self.assertEqual(route.ports_down, {(2, 1)})


if __name__ == "__main__":
    unittest.main()
