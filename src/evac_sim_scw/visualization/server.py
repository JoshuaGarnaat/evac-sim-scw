from __future__ import annotations

from functools import partial
import http.server
import json
import logging
from pathlib import Path
import socket
import threading
import urllib.parse
import webbrowser


class ReplayHandler(http.server.SimpleHTTPRequestHandler):
    replay_path: Path | None = None
    metadata_path: Path | None = None
    replay_data: bytes | None = None
    metadata_data: bytes | None = None

    def end_headers(self):
        """Disable caching so the viewer always receives current data."""
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        """Serve replay data endpoints and static viewer assets."""
        path = urllib.parse.urlparse(self.path).path
        if path == "/data/replay.jsonl":
            if self.replay_data is not None:
                return self._send_bytes(self.replay_data, "application/x-ndjson")
            return self._send_file(self.replay_path, "application/x-ndjson")
        if path == "/data/replay_metadata.json":
            if self.metadata_data is not None:
                return self._send_bytes(self.metadata_data, "application/json")
            return self._send_file(self.metadata_path, "application/json")
        return super().do_GET()

    def _send_file(self, path: Path | None, content_type: str):
        """Stream a replay asset from disk with its content type."""
        if path is None or not path.exists():
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(path.stat().st_size))
        self.end_headers()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                self.wfile.write(chunk)

    def _send_bytes(self, data: bytes, content_type: str):
        """Serve an in-memory replay asset with its content type."""
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        """Route HTTP request logs through the application logger."""
        logging.debug(format, *args)


class ViewerHTTPServer(http.server.ThreadingHTTPServer):
    """Prevent Windows from allowing multiple viewers to share one port."""

    allow_reuse_address = False

    def server_bind(self):
        """Bind exclusively on Windows to avoid shared viewer ports."""
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def _serve(host: str, port: int, open_browser: bool, label: str) -> None:
    """Start the viewer on the first available port in a small range."""
    static = Path(__file__).parent / "static"
    handler = partial(ReplayHandler, directory=str(static))
    server = None
    for candidate in range(port, port + 21):
        try:
            server = ViewerHTTPServer((host, candidate), handler)
            break
        except OSError:
            continue
    if server is None:
        raise OSError(f"No free viewer port found in range {port}-{port + 20}")
    actual_port = server.server_address[1]
    if actual_port != port:
        logging.warning("Port %d is already in use; using %d instead", port, actual_port)
    url = f"http://{host}:{actual_port}/"
    logging.info("%s: %s", label, url)
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("Viewer stopped")
    finally:
        server.server_close()


def serve_replay(replay_path: str | Path, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    """Serve an on-disk replay in the browser viewer."""
    replay = Path(replay_path).resolve()
    ReplayHandler.replay_path = replay
    ReplayHandler.metadata_path = replay.parent / "replay_metadata.json"
    ReplayHandler.replay_data = None
    ReplayHandler.metadata_data = None
    _serve(host, port, open_browser, "Replay viewer")


def floorplan_preview_data(layout_path: str | Path) -> tuple[bytes, bytes]:
    """Build the viewer payload in memory without creating a simulation or result files."""
    from ..geometry.building import Building

    building = Building(layout_path)
    metadata = {
        "format": "evac_sim_scw-floorplan-preview-1",
        "mode": "floorplan",
        "building_layout_reference": str(building.path),
        "building": building.serializable(),
        "population": 0,
    }
    frame = {"t": 0.0, "e": 0, "r": 0, "a": []}
    return (
        json.dumps(metadata, separators=(",", ":")).encode("utf-8"),
        (json.dumps(frame, separators=(",", ":")) + "\n").encode("utf-8"),
    )


def serve_floorplan(layout_path: str | Path, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    """Serve a static floorplan preview in the browser viewer."""
    metadata, replay = floorplan_preview_data(layout_path)
    ReplayHandler.replay_path = None
    ReplayHandler.metadata_path = None
    ReplayHandler.metadata_data = metadata
    ReplayHandler.replay_data = replay
    _serve(host, port, open_browser, "Floorplan viewer")
