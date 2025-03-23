from dotenv import dotenv_values
CONFIG = dotenv_values(".env")
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
import asyncio

def start_web_server(callback):

    class handler(BaseHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            self.callback = callback
            super().__init__(*args, **kwargs)

        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-type','text/html')
            self.end_headers()

            message = '<h2>This is a boostagram IRC boostbot for the TSK relay.</h2> See <a href="https://github.com/cottongin/splitkit-relay">https://github.com/cottongin/splitkit-</a> and <a href="https://github.com/Podcastindex-org/helipad">https://github.com/Podcastindex-org/helipad</a> for more info'
            self.wfile.write(bytes(message, "utf8"))

        def do_POST(self):
            auth_token = self.headers.get('Authorization')
            if auth_token[7:] != CONFIG.get("AUTHTOKEN"):
                self.send_response(401)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(b'Unauthorized')
                return

            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))
            
            message = data['message']
            value_sat_total = int(data['value_msat_total']) // 1000
            sender = data['sender']
            app = data['app']
            podcast = data['podcast']
            episode = data['episode']
            remote_episode = data['remote_episode']
            output_message = f"\x02{ value_sat_total }\x02 sats from \x02{ sender }\x02 via { app } | { episode } | { remote_episode } | \x0304\"{message}\"\x0300"

            asyncio.run(callback(output_message))

            self.send_response(200)
            self.send_header('Content-type','text/html')
            self.end_headers()

    with HTTPServer(('', int(CONFIG.get("WEBPORT"))), handler) as server:
        server.serve_forever()