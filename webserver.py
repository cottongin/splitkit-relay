from dotenv import dotenv_values
CONFIG = dotenv_values(".env")
import pprint
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
import queue
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
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))
            # pprint.pprint(data)
            message = data['message']
            value_sat_total = int(data['value_msat_total']) // 1000
            sender = data['sender']
            app = data['app']
            podcast = data['podcast']
            episode = data['episode']
            remote_episode = data['remote_episode']
            

            # output_message = "Boostagram received! \n message: " + message
            output_message = f"\x02{ value_sat_total }\x02 sats from \x02{ sender }\x02 via { app } | { episode } | { remote_episode } | \x0304\"{message}\"\x0300"
            print("!!!!!!!!!!!!")
            print(self.callback)
            if asyncio.iscoroutinefunction(callback):
                asyncio.run(callback(output_message))
            else:
                callback(output_message)

            self.send_response(200)
            self.send_header('Content-type','text/html')
            self.end_headers()
            

            # print(output_message)
            # self.wfile.write(bytes(output_message, "utf8"))

    with HTTPServer(('', 7777), handler) as server:
        server.serve_forever()