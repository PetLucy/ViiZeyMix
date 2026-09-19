from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from array import array
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time


VIRTUAL_BUSES = {
    "B1": ("viizeymix_b1", "ViiZeyMix-B1-Stream-Mix"),
    "B2": ("viizeymix_b2", "ViiZeyMix-B2-Chat-Mix"),
    "B3": ("viizeymix_b3", "ViiZeyMix-B3-Record-Mix"),
}


@dataclass(frozen=True)
class AudioNode:
    id: int
    name: str
    description: str
    media_class: str
    application_name: str
    application_binary: str
    media_name: str

    @property
    def display_name(self) -> str:
        for candidate in (
            self.application_name,
            self.media_name,
            self.description,
            self.name,
        ):
            if candidate:
                return candidate
        return f"Node {self.id}"

    @property
    def subtitle(self) -> str:
        if self.application_binary and self.application_binary != self.display_name:
            return self.application_binary
        return self.media_class or "PipeWire node"

    @property
    def is_output(self) -> bool:
        return "Sink" in self.media_class

    @property
    def is_input_or_source(self) -> bool:
        return not self.is_output

    @property
    def is_demo(self) -> bool:
        return self.id >= 1_000_000

    @property
    def virtual_bus_code(self) -> str | None:
        for code, (node_name, _description) in VIRTUAL_BUSES.items():
            if self.name == node_name or node_name in self.name:
                return code
        return None

    @property
    def is_viizeymix_bus(self) -> bool:
        return self.virtual_bus_code is not None

    @property
    def is_viizeymix_dsp(self) -> bool:
        return self.name.startswith(("viizeymix_intellipan_", "viizeymix_color_"))

    @property
    def is_viizeymix_meter(self) -> bool:
        return self.name.startswith("viizeymix_meter_")

    @property
    def is_monitor(self) -> bool:
        return self.name.endswith(".monitor") or ".monitor." in self.name


@dataclass(frozen=True)
class PortInfo:
    id: int
    node_id: int
    direction: str
    channel: str
    name: str


@dataclass(frozen=True)
class RoutingResult:
    success: bool
    message: str
    changed_links: int = 0


@dataclass
class DspSession:
    process: subprocess.Popen[str]
    node_id: int
    node_name: str


@dataclass
class MeterSession:
    process: subprocess.Popen[bytes]
    remainder: bytes = b""
    level: float = 0.0


class PipeWireBackend:
    def __init__(self) -> None:
        self.root = Path(__file__).resolve().parent.parent
        self.backend_binary = self.resolve_helper("viizeymix-backend")
        self.dsp_binary = self.resolve_helper("viizeymix-dsp")
        self.last_discovery_error: str | None = None
        self.intellipan_state: dict[int, dict] = {}
        self.dsp_sessions: dict[int, DspSession] = {}
        self.meter_sessions: dict[int, MeterSession] = {}
        config_root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        self.config_path = config_root / "viizeymix" / "config.json"

    def resolve_helper(self, filename: str) -> Path:
        """Locate a native helper in development, system, or bundled layouts."""
        candidates: list[Path] = []
        override = os.environ.get("VIIZEYMIX_LIBEXEC_DIR")
        if override:
            candidates.append(Path(override) / filename)

        frozen_root = getattr(sys, "_MEIPASS", None)
        if frozen_root:
            candidates.append(Path(frozen_root) / filename)

        appdir = os.environ.get("APPDIR")
        if appdir:
            candidates.extend(
                (
                    Path(appdir) / "usr" / "lib" / "viizeymix" / filename,
                    Path(appdir) / "usr" / "lib" / "viizeymix" / "_internal" / filename,
                )
            )

        candidates.extend(
            (
                self.root / "build" / filename,
                self.root / filename,
                Path("/usr/lib/viizeymix") / filename,
                Path("/usr/local/lib/viizeymix") / filename,
                Path("/usr/libexec/viizeymix") / filename,
            )
        )
        for candidate in candidates:
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return candidate
        return self.root / "build" / filename

    @property
    def is_live(self) -> bool:
        return (
            self.backend_binary.exists()
            and shutil.which("pw-dump") is not None
            and shutil.which("pw-link") is not None
        )

    def enumerate_nodes(self) -> list[AudioNode]:
        if not self.backend_binary.exists():
            self.last_discovery_error = (
                f"Native PipeWire helper was not found at {self.backend_binary}."
            )
            return self.demo_nodes()

        try:
            proc = subprocess.run(
                [str(self.backend_binary)],
                capture_output=True,
                text=True,
                timeout=3,
                check=True,
            )
        except subprocess.CalledProcessError as error:
            detail = (error.stderr or "").strip() or f"exit status {error.returncode}"
            self.last_discovery_error = (
                f"{self.backend_binary} could not enumerate PipeWire devices: {detail}"
            )
            return self.demo_nodes()
        except subprocess.TimeoutExpired:
            self.last_discovery_error = (
                f"{self.backend_binary} timed out while connecting to PipeWire."
            )
            return self.demo_nodes()
        except OSError as error:
            self.last_discovery_error = (
                f"{self.backend_binary} could not be started: {error}"
            )
            return self.demo_nodes()

        nodes: list[AudioNode] = []
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                nodes.append(
                    AudioNode(
                        id=int(item.get("id", -1)),
                        name=item.get("name") or "",
                        description=item.get("description") or "",
                        media_class=item.get("media_class") or "",
                        application_name=item.get("application_name") or "",
                        application_binary=item.get("application_binary") or "",
                        media_name=item.get("media_name") or "",
                    )
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                continue

        if not nodes:
            self.last_discovery_error = (
                "The native PipeWire helper ran but reported no audio devices."
            )
            return self.demo_nodes()
        self.last_discovery_error = None
        return nodes

    def ensure_virtual_buses(self) -> list[str]:
        """Create B1-B3 as PipeWire-Pulse null sinks when they are absent."""
        if not self.backend_binary.exists():
            return []
        if shutil.which("pactl") is None:
            return ["pactl was not found; B1-B3 could not be created"]

        try:
            listing = subprocess.run(
                ["pactl", "list", "short", "sinks"],
                capture_output=True,
                text=True,
                timeout=3,
                check=True,
            ).stdout
        except (OSError, subprocess.SubprocessError) as error:
            return [f"Could not inspect virtual buses: {error}"]

        existing = {
            fields[1]
            for line in listing.splitlines()
            if len(fields := line.split()) >= 2
        }
        errors: list[str] = []
        for code, (sink_name, description) in VIRTUAL_BUSES.items():
            if sink_name in existing:
                continue
            try:
                subprocess.run(
                    [
                        "pactl",
                        "load-module",
                        "module-null-sink",
                        f"sink_name={sink_name}",
                        f"sink_properties=device.description={description}",
                        "channels=2",
                        "channel_map=front-left,front-right",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=4,
                    check=True,
                )
            except (OSError, subprocess.SubprocessError) as error:
                errors.append(f"{code} creation failed: {error}")
        return errors

    def load_bus_assignments(self) -> dict[str, str]:
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return {}
        assignments = data.get("hardware_bus_assignments", {})
        if not isinstance(assignments, dict):
            return {}
        return {
            code: str(node_name)
            for code, node_name in assignments.items()
            if code in {"A1", "A2", "A3"} and isinstance(node_name, str)
        }

    def save_bus_assignments(self, assignments: dict[str, str]) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"hardware_bus_assignments": assignments}
        self.config_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def parse_graph_state(raw_json: str) -> list[dict]:
        state = json.loads(raw_json)
        if not isinstance(state, list):
            raise ValueError("pw-dump did not return a JSON array")
        return state

    def graph_state(self) -> list[dict]:
        try:
            proc = subprocess.run(
                ["pw-dump", "-N"],
                capture_output=True,
                text=True,
                timeout=4,
                check=True,
            )
            return self.parse_graph_state(proc.stdout)
        except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError) as error:
            raise RuntimeError(f"Could not read the PipeWire graph: {error}") from error

    @staticmethod
    def node_id_by_name(state: list[dict], node_name: str) -> int | None:
        for item in state:
            if not str(item.get("type", "")).endswith(":Node"):
                continue
            props = item.get("info", {}).get("props", {}) or {}
            if props.get("node.name") == node_name:
                try:
                    return int(item["id"])
                except (KeyError, TypeError, ValueError):
                    return None
        return None

    @staticmethod
    def ports_for_node(state: list[dict], node_id: int, direction: str) -> list[PortInfo]:
        ports: list[PortInfo] = []
        for item in state:
            if not str(item.get("type", "")).endswith(":Port"):
                continue
            props = item.get("info", {}).get("props", {}) or {}
            try:
                port_node_id = int(props.get("node.id", -1))
            except (TypeError, ValueError):
                continue
            if port_node_id != node_id or props.get("port.direction") != direction:
                continue
            ports.append(
                PortInfo(
                    id=int(item["id"]),
                    node_id=port_node_id,
                    direction=direction,
                    channel=str(props.get("audio.channel", "")).upper(),
                    name=str(props.get("port.name", "")),
                )
            )
        return sorted(ports, key=lambda port: (port.channel, port.name, port.id))

    @staticmethod
    def graph_links(state: list[dict]) -> set[tuple[int, int]]:
        links: set[tuple[int, int]] = set()
        for item in state:
            if not str(item.get("type", "")).endswith(":Link"):
                continue
            info = item.get("info", {}) or {}
            try:
                links.add((int(info["output-port-id"]), int(info["input-port-id"])))
            except (KeyError, TypeError, ValueError):
                props = info.get("props", {}) or {}
                try:
                    links.add((int(props["link.output.port"]), int(props["link.input.port"])))
                except (KeyError, TypeError, ValueError):
                    continue
        return links

    @staticmethod
    def pair_ports(outputs: list[PortInfo], inputs: list[PortInfo]) -> list[tuple[PortInfo, PortInfo]]:
        if not outputs or not inputs:
            return []
        if len(outputs) == 1:
            return [(outputs[0], target) for target in inputs]

        by_channel = {port.channel: port for port in outputs if port.channel}
        pairs: list[tuple[PortInfo, PortInfo]] = []
        for index, target in enumerate(inputs):
            source = by_channel.get(target.channel)
            if source is None:
                source = by_channel.get("MONO") or outputs[min(index, len(outputs) - 1)]
            pairs.append((source, target))
        return pairs

    @classmethod
    def route_is_active(
        cls,
        state: list[dict],
        source_node_id: int,
        target_node_id: int,
    ) -> bool:
        pairs = cls.pair_ports(
            cls.ports_for_node(state, source_node_id, "out"),
            cls.ports_for_node(state, target_node_id, "in"),
        )
        if not pairs:
            return False
        links = cls.graph_links(state)
        return all((source.id, target.id) in links for source, target in pairs)

    def _set_route_direct(self, source_node_id: int, target_node_id: int, enabled: bool) -> RoutingResult:
        if source_node_id >= 1_000_000 or target_node_id >= 1_000_000:
            return RoutingResult(True, "Demo route updated", 0)
        if shutil.which("pw-link") is None or shutil.which("pw-dump") is None:
            return RoutingResult(False, "pw-link and pw-dump are required")

        try:
            state = self.graph_state()
        except RuntimeError as error:
            return RoutingResult(False, str(error))

        source_ports = self.ports_for_node(state, source_node_id, "out")
        target_ports = self.ports_for_node(state, target_node_id, "in")
        pairs = self.pair_ports(source_ports, target_ports)
        if not pairs:
            return RoutingResult(False, "No compatible PipeWire ports were found")

        links = self.graph_links(state)
        changed = 0
        for source, target in pairs:
            pair = (source.id, target.id)
            if enabled and pair in links:
                continue
            if not enabled and pair not in links:
                continue
            command = ["pw-link"]
            if not enabled:
                command.append("-d")
            command.extend((str(source.id), str(target.id)))
            try:
                subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=True,
                )
                changed += 1
            except subprocess.CalledProcessError as error:
                detail = (error.stderr or error.stdout or str(error)).strip()
                return RoutingResult(False, f"PipeWire link failed: {detail}", changed)
            except (OSError, subprocess.SubprocessError) as error:
                return RoutingResult(False, f"PipeWire link failed: {error}", changed)

        action = "connected" if enabled else "disconnected"
        return RoutingResult(True, f"{changed} channel link(s) {action}", changed)

    def set_route(self, source_node_id: int, target_node_id: int, enabled: bool) -> RoutingResult:
        session = self.dsp_sessions.get(source_node_id)
        routed_source_id = session.node_id if session is not None else source_node_id
        return self._set_route_direct(routed_source_id, target_node_id, enabled)

    def route_is_active_for_source(
        self,
        state: list[dict],
        source_node_id: int,
        target_node_id: int,
    ) -> bool:
        session = self.dsp_sessions.get(source_node_id)
        routed_source_id = session.node_id if session is not None else source_node_id
        return self.route_is_active(state, routed_source_id, target_node_id)

    def ensure_intellipan_dsp(self, source_node_id: int) -> tuple[DspSession | None, RoutingResult]:
        session = self.dsp_sessions.get(source_node_id)
        if session is not None and session.process.poll() is None:
            return session, RoutingResult(True, "IntelliPan DSP is ready")
        self.dsp_sessions.pop(source_node_id, None)

        if source_node_id >= 1_000_000:
            return None, RoutingResult(True, "Demo IntelliPan DSP updated")
        if not self.dsp_binary.exists():
            return None, RoutingResult(False, "Build viizeymix-dsp before using IntelliPan")

        node_name = f"viizeymix_intellipan_{source_node_id}"
        try:
            process = subprocess.Popen(
                [str(self.dsp_binary), node_name],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except OSError as error:
            return None, RoutingResult(False, f"Could not start IntelliPan DSP: {error}")

        dsp_node_id: int | None = None
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            try:
                state = self.graph_state()
                candidate = self.node_id_by_name(state, node_name)
                if (
                    candidate is not None
                    and self.ports_for_node(state, candidate, "in")
                    and self.ports_for_node(state, candidate, "out")
                ):
                    dsp_node_id = candidate
            except RuntimeError:
                dsp_node_id = None
            if dsp_node_id is not None:
                break
            time.sleep(0.04)

        if dsp_node_id is None:
            process.terminate()
            try:
                _stdout, stderr = process.communicate(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                _stdout, stderr = process.communicate()
            detail = stderr.strip() or "the DSP node did not appear in PipeWire"
            return None, RoutingResult(False, f"Could not start IntelliPan DSP: {detail}")

        session = DspSession(process=process, node_id=dsp_node_id, node_name=node_name)
        self.dsp_sessions[source_node_id] = session
        source_link = self._set_route_direct(source_node_id, dsp_node_id, True)
        if not source_link.success:
            self.stop_intellipan_dsp(source_node_id)
            return None, source_link
        return session, RoutingResult(True, "IntelliPan DSP is ready", source_link.changed_links)

    def write_intellipan_control(
        self,
        session: DspSession,
        mode: str,
        x: float,
        y: float,
    ) -> RoutingResult:
        if session.process.stdin is None or session.process.poll() is not None:
            return RoutingResult(False, "IntelliPan DSP process stopped unexpectedly")
        command = {
            "Color": "color",
            "Modulation": "modulation",
            "Position": "position",
        }.get(mode)
        if command is None:
            return RoutingResult(False, f"Unknown IntelliPan mode: {mode}")
        try:
            session.process.stdin.write(f"{command} {x:.6f} {y:.6f}\n")
            session.process.stdin.flush()
        except (BrokenPipeError, OSError) as error:
            return RoutingResult(False, f"Could not update IntelliPan DSP: {error}")
        return RoutingResult(True, f"{mode} DSP updated")

    def intellipan_is_active(self, source_node_id: int) -> bool:
        return any(
            abs(float(state.get("x", 0.0))) > 0.001 or
            abs(float(state.get("y", 0.0))) > 0.001
            for state in self.intellipan_state.get(source_node_id, {}).values()
        )

    def set_intellipan_dsp(
        self,
        source_node_id: int,
        mode: str,
        x: float,
        y: float,
        routed_target_ids: list[int],
    ) -> RoutingResult:
        existing = self.dsp_sessions.get(source_node_id)
        if existing is not None and existing.process.poll() is not None:
            self.dsp_sessions.pop(source_node_id, None)
            existing = None

        if not self.intellipan_is_active(source_node_id):
            if existing is None:
                return RoutingResult(True, "IntelliPan is neutral")
            return self.deactivate_intellipan_dsp(source_node_id, routed_target_ids)

        session, result = self.ensure_intellipan_dsp(source_node_id)
        if not result.success or session is None:
            return result

        if existing is None:
            for target_id in routed_target_ids:
                filtered = self._set_route_direct(session.node_id, target_id, True)
                if not filtered.success:
                    return filtered
                direct = self._set_route_direct(source_node_id, target_id, False)
                if not direct.success:
                    return direct

            for saved_mode, state in self.intellipan_state.get(source_node_id, {}).items():
                control_result = self.write_intellipan_control(
                    session,
                    saved_mode,
                    float(state.get("x", 0.0)),
                    float(state.get("y", 0.0)),
                )
                if not control_result.success:
                    return control_result
            return RoutingResult(True, "IntelliPan DSP activated")

        return self.write_intellipan_control(session, mode, x, y)

    def deactivate_intellipan_dsp(
        self,
        source_node_id: int,
        routed_target_ids: list[int],
    ) -> RoutingResult:
        session = self.dsp_sessions.get(source_node_id)
        if session is None:
            return RoutingResult(True, "IntelliPan is neutral")

        for target_id in routed_target_ids:
            direct = self._set_route_direct(source_node_id, target_id, True)
            if not direct.success:
                return direct
            filtered = self._set_route_direct(session.node_id, target_id, False)
            if not filtered.success:
                return filtered

        self._set_route_direct(source_node_id, session.node_id, False)
        self.stop_intellipan_dsp(source_node_id)
        return RoutingResult(True, "IntelliPan DSP bypassed")

    def stop_intellipan_dsp(self, source_node_id: int) -> None:
        session = self.dsp_sessions.pop(source_node_id, None)
        if session is None:
            return
        if session.process.stdin is not None:
            try:
                session.process.stdin.write("quit\n")
                session.process.stdin.flush()
            except (BrokenPipeError, OSError):
                pass
        try:
            session.process.wait(timeout=0.6)
        except subprocess.TimeoutExpired:
            session.process.terminate()

    def shutdown_dsp(self) -> None:
        for source_node_id in list(self.dsp_sessions):
            self.stop_intellipan_dsp(source_node_id)

    def cleanup_dsp_sessions(self, active_source_ids: set[int]) -> None:
        for source_node_id in list(self.dsp_sessions):
            if source_node_id not in active_source_ids:
                self.stop_intellipan_dsp(source_node_id)

    def start_meter(self, node: AudioNode) -> bool:
        if node.is_demo:
            return False
        existing = self.meter_sessions.get(node.id)
        if existing is not None and existing.process.poll() is None:
            return True
        self.stop_meter(node.id)

        pw_cat = shutil.which("pw-cat") or shutil.which("pw-record")
        if pw_cat is None or not node.name:
            return False
        command = [pw_cat]
        if Path(pw_cat).name != "pw-record":
            command.append("--record")
        command.extend(
            [
                "--target",
                node.name,
                "--raw",
                "--format",
                "f32",
                "--rate",
                "48000",
                "--channels",
                "2",
                "--channel-map",
                "stereo",
                "--latency",
                "100ms",
                "--properties",
                json.dumps(
                    {
                        "node.name": f"viizeymix_meter_{node.id}",
                        "application.name": "ViiZeyMix Meter",
                        "node.passive": True,
                    },
                    separators=(",", ":"),
                ),
                "-",
            ]
        )
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=0,
            )
            if process.stdout is None:
                process.terminate()
                return False
            os.set_blocking(process.stdout.fileno(), False)
        except OSError:
            return False
        self.meter_sessions[node.id] = MeterSession(process=process)
        return True

    def read_meter_level(self, node_id: int) -> float | None:
        session = self.meter_sessions.get(node_id)
        if session is None:
            return None
        if session.process.poll() is not None or session.process.stdout is None:
            self.stop_meter(node_id)
            return None

        chunks: list[bytes] = []
        for _ in range(4):
            try:
                chunk = os.read(session.process.stdout.fileno(), 65536)
            except BlockingIOError:
                break
            except OSError:
                self.stop_meter(node_id)
                return None
            if not chunk:
                break
            chunks.append(chunk)

        raw = session.remainder + b"".join(chunks)
        usable = len(raw) - (len(raw) % 4)
        session.remainder = raw[usable:]
        if usable:
            samples = array("f")
            samples.frombytes(raw[:usable])
            peak = max((abs(sample) for sample in samples if math.isfinite(sample)), default=0.0)
            decibels = 20.0 * math.log10(max(peak, 0.000001))
            target = max(0.0, min(1.0, (decibels + 60.0) / 60.0))
            session.level = target if target > session.level else session.level * 0.72
        else:
            session.level *= 0.72
        if session.level < 0.003:
            session.level = 0.0
        return session.level

    def stop_meter(self, node_id: int) -> None:
        session = self.meter_sessions.pop(node_id, None)
        if session is None or session.process.poll() is not None:
            return
        session.process.terminate()
        try:
            session.process.wait(timeout=0.4)
        except subprocess.TimeoutExpired:
            session.process.kill()

    def shutdown_meters(self) -> None:
        for node_id in list(self.meter_sessions):
            self.stop_meter(node_id)

    def get_volume(self, node_id: int) -> float:
        if node_id >= 1_000_000:
            return 1.0
        try:
            result = subprocess.run(
                ["wpctl", "get-volume", str(node_id)],
                capture_output=True,
                text=True,
                timeout=2,
                check=True,
            )
        except (OSError, subprocess.SubprocessError):
            return 1.0
        match = re.search(r"Volume:\s*([0-9]+(?:\.[0-9]+)?)", result.stdout)
        return max(0.0, min(float(match.group(1)), 4.0)) if match else 1.0

    def set_volume(self, node_id: int, value: float) -> None:
        value = max(0.0, min(value, 4.0))
        subprocess.run(
            [
                "wpctl",
                "set-volume",
                str(node_id),
                f"{value:.4f}",
                "--limit",
                "4.0",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )

    def set_mute(self, node_id: int, muted: bool) -> None:
        subprocess.run(
            ["wpctl", "set-mute", str(node_id), "1" if muted else "0"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )

    def set_intellipan_state(
        self,
        node_id: int,
        mode: str,
        x: float,
        y: float,
        parameters: dict,
    ) -> None:
        node_state = self.intellipan_state.setdefault(node_id, {})
        node_state[mode] = {
            "mode": mode,
            "x": float(x),
            "y": float(y),
            "parameters": dict(parameters),
        }

    @staticmethod
    def demo_nodes() -> list[AudioNode]:
        demo = [
            (1_000_001, "Firefox", "Stream/Output/Audio", "firefox"),
            (1_000_002, "Discord", "Stream/Output/Audio", "vesktop"),
            (1_000_003, "Game", "Stream/Output/Audio", "vrchat"),
            (1_000_004, "Microphone", "Audio/Source", "alsa"),
            (1_000_005, "alsa_output.headphones", "Audio/Sink", "alsa"),
            (1_000_006, "alsa_output.hdmi", "Audio/Sink", "alsa"),
            (1_000_011, "viizeymix_b1", "Audio/Sink", "pipewire-pulse"),
            (1_000_012, "viizeymix_b2", "Audio/Sink", "pipewire-pulse"),
            (1_000_013, "viizeymix_b3", "Audio/Sink", "pipewire-pulse"),
        ]
        names = {
            "alsa_output.headphones": "Headphones",
            "alsa_output.hdmi": "HDMI Speakers",
            "viizeymix_b1": "ViiZeyMix B1 Stream Mix",
            "viizeymix_b2": "ViiZeyMix B2 Chat Mix",
            "viizeymix_b3": "ViiZeyMix B3 Record Mix",
        }
        return [
            AudioNode(
                id=node_id,
                name=name.lower(),
                description=names.get(name, name),
                media_class=media_class,
                application_name="" if "Sink" in media_class else name,
                application_binary=binary,
                media_name="",
            )
            for node_id, name, media_class, binary in demo
        ]
