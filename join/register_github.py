"""One-time operator setup on localhost. Store credentials in Appwrite function secrets."""
import html
import json
import secrets
import subprocess
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ORIGIN = "https://repo-neighbor-6b014c.appwrite.network"
STATE = secrets.token_urlsafe(32)


class Setup(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Callback URLs carry short-lived credentials.

    def page(self, body, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body.encode())

    def do_GET(self):
        host = f"127.0.0.1:{self.server.server_port}"
        if self.headers.get("Host") != host:
            return self.page("Invalid host", 400)
        url = urllib.parse.urlsplit(self.path)
        if url.path == "/":
            manifest = {"name": "Repo Neighbor Community Desk", "url": ORIGIN,
                        "hook_attributes": {"active": False},
                        "redirect_url": f"http://{host}/registered",
                        "callback_urls": [ORIGIN + "/auth/callback"], "public": True,
                        "default_events": [], "default_permissions": {}}
            return self.page('<h1>Repo Neighbor</h1><p>Войдите как TONstories. Приложение запрашивает только публичную личность.</p>'
                f'<form method="post" action="https://github.com/settings/apps/new?state={STATE}">'
                f'<input type="hidden" name="manifest" value="{html.escape(json.dumps(manifest), quote=True)}">'
                '<button>Зарегистрировать приложение в GitHub</button></form>')
        params = urllib.parse.parse_qs(url.query)
        if url.path != "/registered" or params.get("state") != [STATE] or not params.get("code"):
            return self.page("Invalid callback", 400)
        try:
            code = urllib.parse.quote(params["code"][0], safe="")
            req = urllib.request.Request("https://api.github.com/app-manifests/"+code+"/conversions", data=b"", method="POST",
                                         headers={"Accept":"application/vnd.github+json","User-Agent":"Repo-Neighbor"})
            with urllib.request.urlopen(req, timeout=25) as res:
                app = json.load(res)
            if app["owner"]["login"].lower() != "tonstories":
                return self.page("Registration owner must be TONstories.", 403)
            values = {"GITHUB_CLIENT_ID":app["client_id"], "GITHUB_CLIENT_SECRET":app["client_secret"]}
            for key, value in values.items():
                subprocess.run(
                    ["appwrite", "functions", "create-variable", "--function-id", "repo-neighbor",
                     "--variable-id", key.lower().replace("_", "-"), "--key", key, "--secret",
                     "--value", value], cwd=Path(__file__).parent, capture_output=True,
                    check=True, timeout=60,
                )
        except Exception:
            return self.page("Registration did not complete. Inspect the app settings before retrying.", 502)
        self.page("Секреты сохранены. Повторно разверните функцию. <a href='"+ORIGIN+"'>Открыть Repo Neighbor</a>")
        self.server.done = True


if __name__ == "__main__":
    with HTTPServer(("127.0.0.1",0),Setup) as srv:
        print(f"http://127.0.0.1:{srv.server_port}/",flush=True)
        srv.timeout=5
        until=time.monotonic()+1800
        while not getattr(srv,"done",False) and time.monotonic()<until:
            srv.handle_request()
