"""Read-only localhost route viewer. No arbitrary paths, mutation API, or external assets."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import argparse
import hashlib
import html
import json
import sys

from library import Library, require
from routes import Routes
from knowledge_map import KnowledgeMap

WEB = Path(__file__).resolve().parents[1] / "web"
CSP = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-src 'self'; frame-ancestors 'self'; object-src 'none'; base-uri 'none'"


def make_server(workspace, port=8765):
    workspace = Path(workspace).resolve()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def send(self, body, content_type="application/json; charset=utf-8", status=200, attachment=False):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("Referrer-Policy", "no-referrer")
            if attachment:
                self.send_header("Content-Disposition", 'attachment; filename="archived-file.bin"')
            self.end_headers()
            self.wfile.write(body)

        def error(self, message, status=400):
            self.send(json.dumps({"error": message}, ensure_ascii=False).encode(), status=status)

        def do_GET(self):
            expected_host = "127.0.0.1:" + str(self.server.server_port)
            if self.headers.get("Host") != expected_host:
                self.error("Use the exact 127.0.0.1 URL printed by this service.", 403)
                return
            parsed = urlparse(self.path)
            args = parse_qs(parsed.query)
            param = lambda key, default="": args.get(key, [default])[0]
            try:
                namespace = param("namespace", "real")
                require(namespace in {"real", "demo"}, "invalid namespace")
                if parsed.path in {"/", "/app.js", "/style.css", "/knowledge", "/knowledge.js", "/knowledge.css"}:
                    name, mime = {"/knowledge": ("knowledge.html", "text/html; charset=utf-8"),
                                  "/knowledge.js": ("knowledge.js", "text/javascript; charset=utf-8"),
                                  "/knowledge.css": ("knowledge.css", "text/css; charset=utf-8"),
                                  "/": ("index.html", "text/html; charset=utf-8"),
                                  "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                                  "/style.css": ("style.css", "text/css; charset=utf-8")}[parsed.path]
                    self.send((WEB / name).read_bytes(), mime)
                    return
                routes = Routes(workspace, namespace)
                if parsed.path == "/api/knowledge-graph":
                    result = KnowledgeMap(workspace, namespace).graph()
                elif parsed.path == "/api/graph":
                    result = routes.graph(param("experiment"))
                elif parsed.path == "/api/compare":
                    result = routes.compare(param("first"), param("second"))
                elif parsed.path == "/api/trace":
                    result = routes.lib.trace(param("id"), int(param("version", "1")))
                elif parsed.path == "/api/file":
                    lib = routes.lib
                    record = lib.get(param("id"), int(param("version", "1")))
                    require(record["kind"] in {"source", "research_file"}, "file record required")
                    trace = lib.trace(record["id"], record["version"])
                    file = Path(trace["files"][0]["path"])
                    raw = file.read_bytes()
                    require(hashlib.sha256(raw).hexdigest() == record["data"]["sha256"], "file changed during read")
                    suffix = file.suffix.lower()
                    if suffix == ".pdf":
                        self.send(raw, "application/pdf")
                    elif suffix in {".png", ".jpg", ".jpeg"}:
                        self.send(raw, "image/png" if suffix == ".png" else "image/jpeg")
                    elif suffix in {".txt", ".md", ".json", ".csv", ".tsv", ".log", ".html", ".htm", ".svg"}:
                        # Source HTML/SVG is shown as escaped text, never executed in the app's origin.
                        text = raw[:2_000_000].decode("utf-8-sig", errors="replace")
                        if len(raw) > 2_000_000:
                            text += "\n[Preview truncated at 2 MB; original archived file is preserved.]"
                        self.send(text.encode(), "text/plain; charset=utf-8")
                    else:
                        self.send(raw, "application/octet-stream", attachment=True)
                    return
                else:
                    self.error("not found", 404)
                    return
                self.send(json.dumps(result, ensure_ascii=False).encode())
            except (ValueError, KeyError, OSError, TypeError) as exc:
                self.error(str(exc))

        def do_POST(self):
            self.error("Read-only viewer. Record changes through the authorized MCP workflow.", 405)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = make_server(args.workspace, args.port)
    print(f"Route viewer: http://127.0.0.1:{server.server_port}/ (read-only; Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
