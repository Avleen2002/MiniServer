#!/usr/bin/env python3
"""
CMPT 371 Mini Project (1)
-------------------------
Combined Web Server + Web Proxy Server

Features:
 - Supports HTTP/1.0 and HTTP/1.1
 - Handles 200, 304, 403, 404, 505 status codes
 - Multi-threaded for concurrent clients
 - Thread-safe shared shopping cart
 - Chunked transfer for large files
 - Basic HTTP proxy server forwarding
"""

import socket
import os
import datetime
from urllib.parse import urlparse, parse_qs
from threading import Thread, Lock

# -------------- CONFIGURATION ----------------
HOST = "0.0.0.0"        # Listen on all interfaces
WEB_PORT = 8080         # Local web server
PROXY_PORT = 8888       # Proxy server
WWW_ROOT = "./www"      # Directory for HTML files
SUPPORTED_VERSIONS = ["HTTP/1.0", "HTTP/1.1"]

# Global thread-safe shopping cart
cart = {}
cart_lock = Lock()


# -------------- HELPER: BUILD RESPONSE ----------------
def build_response(status_code, body="", content_type="text/html"):
    """Generate a standard HTTP response with headers."""
    reasons = {
        200: "OK",
        304: "Not Modified",
        403: "Forbidden",
        404: "Not Found",
        505: "HTTP Version Not Supported",
        502: "Bad Gateway"
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


# -------------- HELPER: RENDER CART HTML ----------------
def render_cart():
    """Generate a simple HTML page showing current shopping cart contents."""
    with cart_lock:
        if not cart:
            return "<html><body><h1>Your cart is empty</h1><a href='/index.html'>Back to shop</a></body></html>"
        items = "".join(f"<li>{item}: {qty}</li>" for item, qty in cart.items())
    return f"<html><body><h1>Shopping Cart</h1><ul>{items}</ul><a href='/index.html'>Continue shopping</a></body></html>"


# -------------- HELPER: CHUNKED FILE SENDER ----------------
def send_file_in_chunks(conn, file_path, chunk_size=1024):
    """Send large files using chunked transfer encoding (to avoid buffering entire content)."""
    with open(file_path, "rb") as f:
        while True:
            data = f.read(chunk_size)
            if not data:
                break
            conn.sendall(f"{len(data):X}\r\n".encode()) # Send chunk size in hex + CRLF
            conn.sendall(data)                          # Send chunk data
            conn.sendall(b"\r\n")                       # CRLF after chunk
    conn.sendall(b"0\r\n\r\n")  # Final zero-length chunk


# -------------- CORE: REQUEST HANDLER ----------------
def handle_request(request):
    """Main logic for interpreting HTTP requests and returning responses."""
    try:
        lines = request.split("\r\n")
        if not lines or len(lines[0].split()) < 3:
            return build_response(400, "<h1>400 Bad Request</h1>")

        method, path, version = lines[0].split()

        # ---- 505: Unsupported HTTP version ----
        if version not in SUPPORTED_VERSIONS:
            return build_response(505, "<h1>505 HTTP Version Not Supported</h1>")

        # ---- 403: Unsupported methods ----
        if method not in ["GET", "HEAD"]:
            return build_response(403, "<h1>403 Forbidden – Unsupported Method</h1>")

        # ---- Parse resource and query ----
        parsed = urlparse(path)
        resource = parsed.path.lstrip("/") or "index.html"
        query = parse_qs(parsed.query)

        # ---- 403: Restricted access ----
        restricted = ["admin", "config"]
        if any(resource.startswith(p) for p in restricted):
            return build_response(403, "<h1>403 Forbidden – Access denied</h1>")

        # ---- Dynamic routes ----
        if resource == "add":
            item = query.get("item", ["unknown"])[0]
            qty = int(query.get("qty", ["1"])[0])
            with cart_lock:
                cart[item] = cart.get(item, 0) + qty
            return build_response(200, render_cart())

        elif resource == "cart.html":
            return build_response(200, render_cart())

        # ---- 404: File not found ----
        full_path = os.path.join(WWW_ROOT, resource)
        if not os.path.exists(full_path):
            return build_response(404, "<h1>404 Not Found</h1>")

        # ---- 304: Not modified ----
        headers = {h.split(":")[0]: h.split(":", 1)[1].strip() for h in lines[1:] if ":" in h}
        if "If-Modified-Since" in headers:
            mod_time = datetime.datetime.utcfromtimestamp(os.path.getmtime(full_path))
            try:
                since_time = datetime.datetime.strptime(headers["If-Modified-Since"], "%a, %d %b %Y %H:%M:%S GMT")
                if mod_time <= since_time:
                    return build_response(304)
            except ValueError:
                pass

        # ---- HEAD: Only headers ----
        if method == "HEAD":
            return build_response(200, "")

        # GET request → defer to chunked sender
        return None
    except Exception as e:
        return build_response(500, f"<h1>500 Internal Server Error</h1><p>{e}</p>")


# -------------- CLIENT HANDLER (Web Server) ----------------
def handle_client(conn, addr):
    """Handle an individual web client connection."""
    try:
        request = conn.recv(4096).decode(errors="ignore")
        if not request:
            return
        print(f"[Web] {addr} → {request.splitlines()[0]}")
        response = handle_request(request)

        if response:
            conn.sendall(response.encode())
        else:
            # Send file via chunked transfer
            lines = request.split("\r\n")
            method, path, version = lines[0].split()
            resource = urlparse(path).path.lstrip("/") or "index.html"
            full_path = os.path.join(WWW_ROOT, resource)
            if os.path.exists(full_path):
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


# -------------- PROXY HANDLER ----------------
def handle_proxy(conn, addr):
    """Handle an HTTP proxy request: forward request to target host and relay response."""
    try:
        client_req = conn.recv(8192)
        if not client_req:
            return
        first_line = client_req.split(b"\r\n", 1)[0].decode(errors="ignore")
        print(f"[Proxy] {addr} → {first_line}")

        # Extract Host header
        headers = client_req.decode(errors="ignore").split("\r\n")
        host_line = next((h for h in headers if h.lower().startswith("host:")), None)
        if not host_line:
            conn.sendall(build_response(400, "<h1>400 Bad Request (Missing Host)</h1>").encode())
            return

        host = host_line.split(":", 1)[1].strip()
        hostname, _, port = host.partition(":")
        port = int(port) if port else 80

        # Connect to destination host
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_sock:
            server_sock.connect((hostname, port))
            server_sock.sendall(client_req)

            # Relay back to client
            while True:
                data = server_sock.recv(4096)
                if not data:
                    break
                conn.sendall(data)
    except Exception as e:
        conn.sendall(build_response(502, f"<h1>502 Bad Gateway</h1><p>{e}</p>").encode())
    finally:
        conn.close()


# -------------- SERVER STARTERS ----------------
def start_web_server():
    """Launch the local web server (port 8080)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, WEB_PORT))
        s.listen(5)     # Allow 5 people in queue
        print(f"Web Server running at http://localhost:{WEB_PORT}")
        while True:
            conn, addr = s.accept()
            Thread(target=handle_client, args=(conn, addr), daemon=True).start()


def start_proxy_server():
    """Launch the proxy server (port 8888)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PROXY_PORT))
        s.listen(5)
        print(f"Proxy Server listening on port {PROXY_PORT}")
        while True:
            conn, addr = s.accept()
            Thread(target=handle_proxy, args=(conn, addr), daemon=True).start()


# -------------- MAIN ENTRY POINT ----------------
if __name__ == "__main__":
    Thread(target=start_proxy_server, daemon=True).start()
    start_web_server()
