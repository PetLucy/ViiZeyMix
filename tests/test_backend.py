from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import MagicMock, call, patch
import os
import struct
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from audio_backend import (  # noqa: E402
    AudioNode,
    DspSession,
    MeterSession,
    PipeWireBackend,
    RoutingResult,
)


def port(port_id: int, node_id: int, direction: str, channel: str) -> dict:
    return {
        "id": port_id,
        "type": "PipeWire:Interface:Port",
        "info": {
            "props": {
                "node.id": node_id,
                "port.direction": direction,
                "audio.channel": channel,
                "port.name": f"{direction}_{channel}",
            }
        },
    }


class RoutingTests(TestCase):
    def setUp(self) -> None:
        self.backend = PipeWireBackend()
        self.state = [
            port(100, 10, "out", "FL"),
            port(101, 10, "out", "FR"),
            port(200, 20, "in", "FL"),
            port(201, 20, "in", "FR"),
        ]

    def test_stereo_ports_are_paired_by_channel(self) -> None:
        outputs = self.backend.ports_for_node(self.state, 10, "out")
        inputs = self.backend.ports_for_node(self.state, 20, "in")
        pairs = self.backend.pair_ports(outputs, inputs)
        self.assertEqual([(a.id, b.id) for a, b in pairs], [(100, 200), (101, 201)])

    def test_mono_source_fans_out_to_stereo_target(self) -> None:
        state = [port(100, 10, "out", "MONO"), *self.state[2:]]
        outputs = self.backend.ports_for_node(state, 10, "out")
        inputs = self.backend.ports_for_node(state, 20, "in")
        pairs = self.backend.pair_ports(outputs, inputs)
        self.assertEqual([(a.id, b.id) for a, b in pairs], [(100, 200), (100, 201)])

    def test_existing_routes_are_reconstructed_from_graph_links(self) -> None:
        state = [
            *self.state,
            {
                "id": 300,
                "type": "PipeWire:Interface:Link",
                "info": {"output-port-id": 100, "input-port-id": 200},
            },
            {
                "id": 301,
                "type": "PipeWire:Interface:Link",
                "info": {"output-port-id": 101, "input-port-id": 201},
            },
        ]
        self.assertTrue(self.backend.route_is_active(state, 10, 20))

    @patch("audio_backend.shutil.which", return_value="/usr/bin/tool")
    @patch("audio_backend.subprocess.run")
    def test_set_route_creates_lingering_links(self, run, _which) -> None:
        with patch.object(self.backend, "graph_state", return_value=self.state):
            result = self.backend.set_route(10, 20, True)
        self.assertTrue(result.success)
        self.assertEqual(result.changed_links, 2)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(commands, [["pw-link", "100", "200"], ["pw-link", "101", "201"]])

    def test_routes_use_filter_output_when_intellipan_dsp_is_active(self) -> None:
        process = MagicMock()
        process.poll.return_value = None
        self.backend.dsp_sessions[10] = DspSession(process, 30, "viizeymix_intellipan_10")
        with patch.object(
            self.backend,
            "_set_route_direct",
            return_value=RoutingResult(True, "ok", 2),
        ) as direct:
            result = self.backend.set_route(10, 20, True)
        self.assertTrue(result.success)
        direct.assert_called_once_with(30, 20, True)

    def test_enabling_intellipan_migrates_existing_routes_through_filter(self) -> None:
        process = MagicMock()
        process.poll.return_value = None
        session = DspSession(process, 30, "viizeymix_intellipan_10")
        self.backend.set_intellipan_state(10, "Color", -0.5, 0.25, {})
        with (
            patch.object(
                self.backend,
                "ensure_intellipan_dsp",
                return_value=(session, RoutingResult(True, "ready")),
            ),
            patch.object(
                self.backend,
                "_set_route_direct",
                return_value=RoutingResult(True, "ok", 2),
            ) as direct,
            patch.object(
                self.backend,
                "write_intellipan_control",
                return_value=RoutingResult(True, "updated"),
            ),
        ):
            result = self.backend.set_intellipan_dsp(10, "Color", -0.5, 0.25, [20])
        self.assertTrue(result.success)
        self.assertEqual(direct.call_args_list, [call(30, 20, True), call(10, 20, False)])

    def test_resetting_one_mode_keeps_other_active_mode_running(self) -> None:
        process = MagicMock()
        process.poll.return_value = None
        session = DspSession(process, 30, "viizeymix_intellipan_10")
        self.backend.dsp_sessions[10] = session
        self.backend.set_intellipan_state(10, "Color", -0.5, 0.25, {})
        self.backend.set_intellipan_state(10, "Modulation", 0.0, 0.0, {})
        with (
            patch.object(
                self.backend,
                "ensure_intellipan_dsp",
                return_value=(session, RoutingResult(True, "ready")),
            ),
            patch.object(
                self.backend,
                "write_intellipan_control",
                return_value=RoutingResult(True, "updated"),
            ) as write,
            patch.object(self.backend, "deactivate_intellipan_dsp") as deactivate,
        ):
            result = self.backend.set_intellipan_dsp(10, "Modulation", 0.0, 0.0, [20])
        self.assertTrue(result.success)
        write.assert_called_once_with(session, "Modulation", 0.0, 0.0)
        deactivate.assert_not_called()

    def test_resetting_last_active_mode_bypasses_processor(self) -> None:
        process = MagicMock()
        process.poll.return_value = None
        self.backend.dsp_sessions[10] = DspSession(process, 30, "viizeymix_intellipan_10")
        self.backend.set_intellipan_state(10, "Position", 0.0, 0.0, {})
        with patch.object(
            self.backend,
            "deactivate_intellipan_dsp",
            return_value=RoutingResult(True, "bypassed"),
        ) as deactivate:
            result = self.backend.set_intellipan_dsp(10, "Position", 0.0, 0.0, [20])
        self.assertTrue(result.success)
        deactivate.assert_called_once_with(10, [20])

    def test_virtual_sink_is_not_shown_as_a_physical_output(self) -> None:
        node = AudioNode(31, "viizeymix_b1", "B1", "Audio/Sink", "", "", "")
        self.assertTrue(node.is_output)
        self.assertTrue(node.is_viizeymix_bus)
        self.assertEqual(node.virtual_bus_code, "B1")

    def test_sink_monitor_is_identified_for_real_output_metering(self) -> None:
        node = AudioNode(
            32,
            "alsa_output.usb-headset.monitor",
            "Monitor of Headset",
            "Audio/Source",
            "",
            "",
            "",
        )
        self.assertTrue(node.is_monitor)
        self.assertFalse(node.is_output)

    @patch("audio_backend.subprocess.run")
    def test_volume_uses_explicit_four_times_gain_limit(self, run) -> None:
        self.backend.set_volume(42, 2.25)
        self.assertEqual(
            run.call_args.args[0],
            ["wpctl", "set-volume", "42", "2.2500", "--limit", "4.0"],
        )

    @patch("audio_backend.subprocess.run")
    def test_existing_boosted_volume_is_read_back(self, run) -> None:
        run.return_value = MagicMock(stdout="Volume: 1.500 [MUTED]\n")
        self.assertEqual(self.backend.get_volume(42), 1.5)

    @patch("audio_backend.os.read")
    def test_meter_converts_real_f32_peak_to_dbfs_height(self, read) -> None:
        process = MagicMock()
        process.poll.return_value = None
        process.stdout.fileno.return_value = 77
        read.side_effect = [
            struct.pack("=4f", 0.0, 0.5, -0.25, 0.1),
            BlockingIOError(),
        ]
        self.backend.meter_sessions[42] = MeterSession(process=process)
        level = self.backend.read_meter_level(42)
        self.assertIsNotNone(level)
        self.assertAlmostEqual(level, 0.8997, places=3)

    def test_hardware_bus_assignments_persist_by_stable_node_name(self) -> None:
        with TemporaryDirectory() as directory:
            self.backend.config_path = Path(directory) / "config.json"
            expected = {"A1": "alsa_output.usb-headset", "A2": "alsa_output.hdmi"}
            self.backend.save_bus_assignments(expected)
            self.assertEqual(self.backend.load_bus_assignments(), expected)

    def test_stale_intellipan_processors_are_stopped_after_source_disappears(self) -> None:
        process = MagicMock()
        self.backend.dsp_sessions[10] = DspSession(process, 30, "viizeymix_intellipan_10")
        self.backend.dsp_sessions[11] = DspSession(process, 31, "viizeymix_intellipan_11")
        with patch.object(self.backend, "stop_intellipan_dsp") as stop:
            self.backend.cleanup_dsp_sessions({11})
        stop.assert_called_once_with(10)

    def test_native_helper_can_be_resolved_from_packaging_override(self) -> None:
        with TemporaryDirectory() as directory:
            helper = Path(directory) / "viizeymix-backend"
            helper.write_text("#!/bin/sh\n", encoding="utf-8")
            helper.chmod(0o755)
            with patch.dict(os.environ, {"VIIZEYMIX_LIBEXEC_DIR": directory}):
                backend = PipeWireBackend()
            self.assertEqual(backend.backend_binary, helper)

    def test_missing_native_helper_records_demo_mode_reason(self) -> None:
        self.backend.backend_binary = Path("/definitely/missing/viizeymix-backend")
        nodes = self.backend.enumerate_nodes()
        self.assertTrue(nodes)
        self.assertTrue(all(node.is_demo for node in nodes))
        self.assertIn("was not found", self.backend.last_discovery_error or "")


if __name__ == "__main__":
    main()
