#!/usr/bin/env python3
import http.server
import socketserver

PORT = 8080  # You can change this if you want another port


class MiniHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """A simple HTTP request handler that can respond with various HTTP codes."""

    def do_GET(self):
        """
        Handle GET requests and respond with custom HTTP status codes
        depending on the URL path.
        """
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>200 OK</h1><p>Welcome to the Mini Server!</p>")

        elif self.path == "/badrequest":
            self.send_error(400, "Bad Request: Your request cannot be processed.")

        elif self.path == "/forbidden":
            self.send_error(403, "Forbidden: You don’t have permission to access this resource.")

        elif self.path == "/notfound":
            self.send_error(404, "Not Found: The requested resource doesn’t exist.")

        elif self.path == "/error":
            self.send_error(500, "Internal Server Error: Something went wrong on the server.")

        else:
            # Default to 404 for any other path
            self.send_error(404, f"Path '{self.path}' not recognized.")

    def do_POST(self):
        """
        Example POST handler.
        """
        self.send_response(201)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"<h1>201 Created</h1><p>Your POST request was received!</p>")


# Create the server
with socketserver.TCPServer(("", PORT), MiniHTTPRequestHandler) as httpd:
    print(f"🚀 Mini Server running on port {PORT}")
    print("Try visiting these URLs in your browser:")
    print("  • http://localhost:8080/")
    print("  • http://localhost:8080/badrequest")
    print("  • http://localhost:8080/forbidden")
    print("  • http://localhost:8080/notfound")
    print("  • http://localhost:8080/error")
    print("Press Ctrl+C to stop the server.\n")
    httpd.serve_forever()
