from __future__ import annotations

from functools import partial
import http.server
import logging
from pathlib import Path
import threading
import urllib.parse
import webbrowser


class ReplayHandler(http.server.SimpleHTTPRequestHandler):
    replay_path: Path
    metadata_path: Path

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/data/replay.jsonl":
            return self._send_file(self.replay_path, "application/x-ndjson")
        if path == "/data/replay_metadata.json":
            return self._send_file(self.metadata_path, "application/json")
        return super().do_GET()

    def _send_file(self, path: Path, content_type: str):
        if not path.exists():
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(path.stat().st_size))
        self.end_headers()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                self.wfile.write(chunk)

    def log_message(self, format, *args):
        logging.debug(format, *args)


def serve_replay(replay_path: str | Path, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    replay = Path(replay_path).resolve()
    static = Path(__file__).parent / "static"
    ReplayHandler.replay_path = replay
    ReplayHandler.metadata_path = replay.parent / "replay_metadata.json"
    handler = partial(ReplayHandler, directory=str(static))
    server = http.server.ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{port}/"
    logging.info("Replay viewer: %s", url)
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("Viewer stopped")
    finally:
        server.server_close()
