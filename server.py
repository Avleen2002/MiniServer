#!/usr/bin/env python3
import socket
import os
import datetime
from urllib.parse import urlparse, parse_qs
from threading import Thread, Lock

# --------------- Configuration ---------------
HOST = "0.0.0.0"        # Listen on all interfaces
PORT = 8080
WWW_ROOT = "./www"      # Directory for files
SUPPORTED_VERSIONS = ["HTTP/1.0", "HTTP/1.1"]

# Simple global cart (shared by all clients)
cart = {}
cart_lock = Lock()  # Thread-safe access

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

# --------------- HTML Rendering ---------------
def render_cart():
    """Render HTML page for current cart state."""
    with cart_lock:
        if not cart:
            return "<html><body><h1>Your cart is empty</h1><a href='/index.html'>Back to shop</a></body></html>"
        items = "".join(f"<li>{item}: {qty}</li>" for item, qty in cart.items())
    return f"<html><body><h1>Shopping Cart</h1><ul>{items}</ul><a href='/index.html'>Continue shopping</a></body></html>"

# --------------- Chunked File Sending Helper ---------------
def send_file_in_chunks(conn, file_path, chunk_size=1024):
    """Send a file using proper HTTP/1.1 chunked transfer."""
    with open(file_path, "rb") as f:
        while True:
            data = f.read(chunk_size)
            if not data:
                break
            # Send chunk size in hex + CRLF
            conn.sendall(f"{len(data):X}\r\n".encode())
            # Send chunk data
            conn.sendall(data)
            # CRLF after chunk
            conn.sendall(b"\r\n")
    # Final zero-length chunk
    conn.sendall(b"0\r\n\r\n")

# --------------- Request Handler ---------------
def handle_request(request):
    try:
        lines = request.split("\r\n")
        if not lines or len(lines[0].split()) < 3:
            return build_response(400, "<h1>400 Bad Request</h1>")

        method, path, version = lines[0].split()

        # 505 HTTP Version Not Supported
        if version not in SUPPORTED_VERSIONS:
            return build_response(505, "<h1>505 HTTP Version Not Supported</h1>")

        # Only GET, HEAD supported
        if method not in ["GET", "HEAD"]:
            return build_response(403, "<h1>403 Forbidden – Unsupported Method</h1>")

        # Parse URL
        parsed = urlparse(path)
        resource = parsed.path.lstrip("/") or "index.html"
        query = parse_qs(parsed.query)

        # 403 Forbidden for restricted directories
        restricted = ["admin", "config"]
        if any(resource.startswith(p) for p in restricted):
            return build_response(403, "<h1>403 Forbidden – Access denied</h1>")

        # Shopping cart actions
        if resource == "add":
            item = query.get("item", ["unknown"])[0]
            qty = int(query.get("qty", ["1"])[0])
            with cart_lock:
                cart[item] = cart.get(item, 0) + qty
            body = render_cart()
            return build_response(200, body)

        elif resource == "cart.html":
            body = render_cart()
            return build_response(200, body)

        # Serve static file
        full_path = os.path.join(WWW_ROOT, resource)
        if not os.path.exists(full_path):
            return build_response(404, "<h1>404 Not Found</h1>")

        # Check If-Modified-Since header
        headers = {h.split(":")[0]: h.split(":", 1)[1].strip() for h in lines[1:] if ":" in h}
        if "If-Modified-Since" in headers:
            mod_time = datetime.datetime.utcfromtimestamp(os.path.getmtime(full_path))
            try:
                since_time = datetime.datetime.strptime(headers["If-Modified-Since"], "%a, %d %b %Y %H:%M:%S GMT")
                if mod_time <= since_time:
                    return build_response(304)
            except ValueError:
                pass

        # For HEAD requests, only send headers
        if method == "HEAD":
            return build_response(200, "")

        # For GET requests, send file body via chunked transfer in handle_client()
        return None  # We'll handle chunked sending separately

    except Exception as e:
        return build_response(500, f"<h1>500 Internal Server Error</h1><p>{e}</p>")

# --------------- Threaded Client Handling ---------------
def handle_client(conn, addr):
    try:
        request = conn.recv(4096).decode(errors="ignore")
        if not request:
            return
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Request from {addr}")
        print(request.split('\r\n')[0])

        response = handle_request(request)
        if response:  # If response is already fully built
            conn.sendall(response.encode())
        else:
            # Serve file in chunked transfer
            lines = request.split("\r\n")
            method, path, version = lines[0].split()
            parsed = urlparse(path)
            resource = parsed.path.lstrip("/") or "index.html"
            full_path = os.path.join(WWW_ROOT, resource)
            if os.path.exists(full_path) and os.path.isfile(full_path):
                # Send headers first
                headers = [
                    "HTTP/1.1 200 OK",
                    f"Date: {datetime.datetime.utcnow():%a, %d %b %Y %H:%M:%S GMT}",
                    "Server: MiniCartServer/1.0",
                    "Content-Type: text/html",
                    "Transfer-Encoding: chunked",
                    "Connection: close",
                    "\r\n"
                ]
                conn.sendall("\r\n".join(headers).encode())
                send_file_in_chunks(conn, full_path)

    except Exception as e:
        conn.sendall(build_response(500, f"<h1>500 Internal Server Error</h1><p>{e}</p>").encode())
    finally:
        conn.close()

# --------------- Main Server Loop ---------------
def start_server():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen(5)
        s.settimeout(2.0)  # To allow KeyboardInterrupt
        print(f"CMPT 371 Mini Server running on http://localhost:{PORT}")
        print("Press Ctrl+C to stop.\n")
        try:
            while True:
                try:
                    conn, addr = s.accept()
                    Thread(target=handle_client, args=(conn, addr), daemon=True).start()
                except socket.timeout:
                    continue
        except KeyboardInterrupt:
            print("\nServer stopped by user.")
        finally:
            s.close()

if __name__ == "__main__":
    start_server()