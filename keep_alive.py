# keep_alive.py
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Moses Bot is alive and running 24/7!")

    def log_message(self, format, *args):
        # جلوگیری از شلوغ شدن لاگ‌ها با پینگ‌های آپتایم
        return

def run_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    server.serve_forever()

def keep_alive():
    t = threading.Thread(target=run_server, daemon=True)
    t.start()
