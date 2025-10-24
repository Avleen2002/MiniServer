#!/usr/bin/env python3
import socket
import os
import datetime
from urllib.parse import urlparse, parse_qs
from threading import Thread

# --------------- Configuration ---------------
HOST = "0.0.0.0"        # Listen on all interfaces
PORT = 8080
WWW_ROOT = "./www"      # Directory for files
SUPPORTED_VERSIONS = ["HTTP/1.0", "HTTP/1.1"]

# Simple global cart (shared by all clients)
cart = {}

# --------------- Utility Functions ---------------
def build_response(status_code, body="", content_type="text/html"):
    """Build full HTTP response string."""
    reasons = {
        200: "OK",
        304: "Not Modified",
        403: "Forbidden",
        404: "Not Found",
        505: "HTTP Version Not Supported"
    }
    reason = reasons.get(status_code, "Unknown")
    headers = [
        f"HTTP/1.1 {status_code} {reason}",
        f"Date: {datetime.datetime.utcnow():%a, %d %b %Y %H:%M:%S GMT}",
        "Server: MiniCartServer/1.0",
        f"Content-Type: {content_type}",
        f"Content-Length: {len(body.encode())}",
        "Connection: close",
        "\r\n"
    ]
    return "\r\n".join(headers) + body

# --------------- Request Handler ---------------
def handle_request(request):
    try:
        # Parse request line
        lines = request.split("\r\n")
        if not lines or len(lines[0].split()) < 3:
            return build_response(400, "<h1>400 Bad Request</h1>")

        method, path, version = lines[0].split()

        # ---- 505 HTTP Version Not Supported ----
        if version not in SUPPORTED_VERSIONS:
            return build_response(505, "<h1>505 HTTP Version Not Supported</h1>")

        # ---- Only GET, HEAD supported ----
        if method not in ["GET", "HEAD"]:
            return build_response(403, "<h1>403 Forbidden – Unsupported Method</h1>")

        # Parse URL and query
        parsed = urlparse(path)
        resource = parsed.path.lstrip("/") or "index.html"
        query = parse_qs(parsed.query)
        print(f"[DEBUG] resource={resource}, query={query}")

        # ---- 403 Forbidden for restricted directories ----
        restricted = ["admin", "config"]
        if any(resource.startswith(p) for p in restricted):
            return build_response(403, "<h1>403 Forbidden – Access denied to protected area</h1>")

        # ---- Shopping Cart Actions ----
        if resource == "add":
            item = query.get("item", ["unknown"])[0]
            qty = int(query.get("qty", ["1"])[0])
            cart[item] = cart.get(item, 0) + qty
            body = render_cart()
            return build_response(200, body)

        elif resource == "cart.html":
            body = render_cart()
            return build_response(200, body)

        # ---- 404 Not Found ----
        full_path = os.path.join(WWW_ROOT, resource)
        if not os.path.exists(full_path):
            return build_response(404, "<h1>404 Not Found</h1>")

        # ---- 304 Not Modified ----
        headers = {h.split(":")[0]: h.split(":", 1)[1].strip()
                   for h in lines[1:] if ":" in h}
        if "If-Modified-Since" in headers:
            mod_time = datetime.datetime.utcfromtimestamp(os.path.getmtime(full_path))
            try:
                since_time = datetime.datetime.strptime(
                    headers["If-Modified-Since"], "%a, %d %b %Y %H:%M:%S GMT")
                if mod_time <= since_time:
                    return build_response(304)
            except ValueError:
                pass  # Ignore malformed header

        # ---- Serve Static File ----
        with open(full_path, "r", encoding="utf-8") as f:
            body = f.read()

        # For HEAD, do not send body (headers only)
        if method == "HEAD":
            return build_response(200, "")

        return build_response(200, body)

    except Exception as e:
        return build_response(500, f"<h1>500 Internal Server Error</h1><p>{e}</p>")

# --------------- HTML Rendering ---------------
def render_cart():
    """Render HTML page for current cart state."""
    if not cart:
        return "<html><body><h1>Your cart is empty</h1><a href='/index.html'>Back to shop</a></body></html>"
    items = "".join(f"<li>{item}: {qty}</li>" for item, qty in cart.items())
    return f"<html><body><h1>Shopping Cart</h1><ul>{items}</ul><a href='/index.html'>Continue shopping</a></body></html>"

# --------------- Threaded Connection Handling ---------------
def handle_client(conn, addr):
    try:
        request = conn.recv(4096).decode(errors="ignore")
        if not request:
            return
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Request from {addr}")
        print(request.split('\r\n')[0])
        response = handle_request(request)
        conn.sendall(response.encode())
    finally:
        conn.close()

# --------------- Main Server Loop ---------------
def start_server():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen(5)
        print(f"🚀 MiniCart Server running on http://localhost:{PORT}")
        print("Press Ctrl+C to stop.")
        while True:
            conn, addr = s.accept()
            Thread(target=handle_client, args=(conn, addr), daemon=True).start()

if __name__ == "__main__":
    start_server()
