import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
import logging
from socketserver import ThreadingMixIn
from threading import Thread


class ThreadedWebServer(ThreadingMixIn, HTTPServer):
    logger = None
    get_clustre_state_func = None


class WebServer(Thread):
    def __init__(self, get_clustre_state_func, address, port):
        Thread.__init__(self)
        self.logger = logging.getLogger("logger")
        self.server = None
        self.get_clustre_state_func = get_clustre_state_func
        self.address = address
        self.port = port

    def run(self):
        self.server = ThreadedWebServer((self.address, self.port), RequestHandler)
        self.server.logger = self.logger
        self.server.get_clustre_state_func = self.get_clustre_state_func
        url = "http://" + self.address + ":" + str(self.port)
        self.logger.info(f"Starting webserver at {url}. Check {url}/status and {url}/heartbeat")
        self.server.serve_forever()
        pass

    def stop(self):
        if self.server is None:
            return

        self.logger.debug("Stopping webserver.")
        self.server.shutdown()
        self.logger.debug("Webserver has been stopped.")

class RequestHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/status':
            self.server.logger.debug("Got request: %r", self.path)
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            response = str(self.server.get_clustre_state_func())
            self.send_header('Content-length', len(response))
            self.end_headers()
            self.wfile.write(response.encode(encoding='utf_8'))

        if self.path == '/heartbeat':
            self.server.logger.debug("Got request: %r", self.path)
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            response = "{'state': 'ok', 'time':'" + str(datetime.datetime.now()) + "'}"
            self.send_header('Content-length', len(response))
            self.end_headers()
            self.wfile.write(response.encode(encoding='utf_8'))

        self.send_response(404)

    def log_message(self, format, *args):
        """Function is overridden in order to fix the running of webserver as a Windows service."""
        pass
