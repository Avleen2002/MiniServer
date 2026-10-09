# MiniCartServer: Web Server + HTTP Proxy

A lightweight, multi-threaded HTTP web server and basic forwarding proxy written in pure Python using only the standard library. Built for **CMPT 371 – Mini Project (1)**.

The web server serves static HTML files and exposes a simple thread-safe shopping cart. The proxy server forwards plain HTTP requests to their destination and relays the response back to the client.

## Features

- **HTTP/1.0 and HTTP/1.1** request support
- **Status codes:** `200`, `304`, `403`, `404`, `505` (plus `400`, `500`, and `502` for malformed requests, server errors, and proxy failures)
- **Multi-threaded:** each client connection is handled in its own thread
- **Thread-safe shopping cart** shared across all clients, protected by a lock
- **Chunked transfer encoding** for file responses, so files are streamed rather than buffered in memory
- **Conditional GET** support via `If-Modified-Since`
- **Basic HTTP proxy** that forwards requests using the `Host` header
- **No dependencies:** standard library only

## Requirements

- Python 3.6 or newer (uses f-strings)

## Project Structure

```
.
├── server.py        # Web server + proxy (rename to match your file)
├── www/             # Document root for static files
│   └── index.html
└── README.md
```

> The server serves files from `./www`. Create this directory and add at least an `index.html` before starting.

## Getting Started

1. **Clone the repository**

   ```bash
   git clone https://github.com/<your-username>/<your-repo>.git
   cd <your-repo>
   ```

2. **Create the document root and a sample page**

   ```bash
   mkdir -p www
   echo "<html><body><h1>Welcome</h1><a href='/add?item=apple&qty=2'>Add 2 apples</a></body></html>" > www/index.html
   ```

3. **Run the servers**

   ```bash
   python3 server.py
   ```

   You should see:

   ```
   Proxy Server listening on port 8888
   Web Server running at http://localhost:8080
   ```

Both servers start together: the proxy runs in a background thread and the web server runs in the main thread. Press `Ctrl+C` to stop.

## Configuration

Settings are defined at the top of the script:

| Variable             | Default                | Description                          |
| -------------------- | ---------------------- | ------------------------------------ |
| `HOST`               | `0.0.0.0`              | Interface to listen on (all)         |
| `WEB_PORT`           | `8080`                 | Port for the web server              |
| `PROXY_PORT`         | `8888`                 | Port for the proxy server            |
| `WWW_ROOT`           | `./www`                | Directory static files are served from |
| `SUPPORTED_VERSIONS` | `HTTP/1.0`, `HTTP/1.1` | Accepted HTTP versions               |

## Usage

### Web Server

Open `http://localhost:8080` in a browser, or use `curl`:

```bash
# Fetch the home page
curl -i http://localhost:8080/

# HEAD request (headers only)
curl -I http://localhost:8080/index.html

# Conditional GET (returns 304 if the file hasn't changed)
curl -i -H "If-Modified-Since: Wed, 01 Jan 2030 00:00:00 GMT" http://localhost:8080/index.html
```

### Shopping Cart Routes

| Route                           | Description                                         |
| ------------------------------- | --------------------------------------------------- |
| `/add?item=<name>&qty=<number>` | Adds an item to the cart and displays the cart      |
| `/cart.html`                    | Displays the current cart contents                  |

```bash
curl "http://localhost:8080/add?item=apple&qty=3"
curl http://localhost:8080/cart.html
```

The cart is stored in memory and shared by all clients. It resets when the server restarts.

### Proxy Server

Point a client at the proxy on port `8888`. For example, with `curl`:

```bash
curl -x http://localhost:8888 http://example.com/
```

Or configure your browser's HTTP proxy to `localhost:8888`. The proxy reads the `Host` header, connects to the destination (port 80 by default), forwards the request, and streams the response back.

## Status Codes

| Code  | When it is returned                                                   |
| ----- | --------------------------------------------------------------------- |
| `200` | Resource found, or a successful cart operation                        |
| `304` | `If-Modified-Since` is at or after the file's last modification time  |
| `400` | Malformed request line (web server) or missing `Host` header (proxy)  |
| `403` | Method other than `GET`/`HEAD`, or access to a restricted path (`admin*`, `config*`) |
| `404` | Requested file does not exist in `WWW_ROOT`                           |
| `500` | Unexpected server error                                               |
| `502` | Proxy could not reach or relay from the destination server            |
| `505` | HTTP version other than 1.0 or 1.1                                    |

## Testing

Each status code and the proxy were verified with `curl -v` (full write-up with screenshots in the project report). The server must be running, and `www/` should contain `index.html` and `test.html`.

### Web server

| Test | Command | Expected result |
| ---- | ------- | --------------- |
| 200 – static file | `curl -v http://localhost:8080/index.html` | `200 OK`, `Transfer-Encoding: chunked` |
| 200 – dynamic route | `curl -v "http://localhost:8080/add?item=apple"` | `200 OK`, generated cart page |
| 304 – conditional GET | `curl -v -H "If-Modified-Since: <date later than file's mtime>" http://localhost:8080/test.html` | `304 Not Modified`, no body |
| 403 – restricted path | `curl -v http://localhost:8080/admin/secret.html` | `403 Forbidden` |
| 403 – unsupported method | `curl -v -X POST http://localhost:8080/index.html` | `403 Forbidden` |
| 404 – missing file | `curl -v http://localhost:8080/missing.html` | `404 Not Found` |
| 404 – unknown route | `curl -v http://localhost:8080/randompage` | `404 Not Found` |
| 505 – bad version | see below | `505 HTTP Version Not Supported` |

`curl` can't send an `HTTP/2.0` request line over a plain HTTP/1.x connection, so the 505 test uses a raw socket. On Windows PowerShell:

```powershell
$client = New-Object System.Net.Sockets.TcpClient("localhost",8080)
$stream = $client.GetStream()
$writer = New-Object System.IO.StreamWriter($stream)
$writer.Write("GET /test.html HTTP/2.0`r`nHost: localhost:8080`r`nConnection: close`r`n`r`n")
$writer.Flush()
(New-Object System.IO.StreamReader($stream)).ReadToEnd()
$client.Close()
```

On Linux/macOS, the equivalent is:

```bash
printf 'GET /test.html HTTP/2.0\r\nHost: localhost:8080\r\nConnection: close\r\n\r\n' | nc localhost 8080
```

### Proxy

| Test | Command | Expected result |
| ---- | ------- | --------------- |
| Successful forwarding | `curl -v -x localhost:8888 http://example.com/` | `200 OK` with the example.com page |
| Invalid host | `curl -v -x localhost:8888 http://invalid.com/` | `502 Bad Gateway` |
| Conditional GET passthrough | `curl -v -x localhost:8888 -H "If-Modified-Since: Fri, 24 Oct 2025 12:00:00 GMT" http://example.com/` | Header forwarded; `304` relayed from the origin |
| Web server unaffected | `curl -v http://localhost:8080/test.html` | `200 OK` (web server and proxy run concurrently) |

## How It Works

- **Concurrency:** `start_web_server()` and `start_proxy_server()` each accept connections in a loop and spawn a daemon `Thread` per client.
- **Request handling:** `handle_request()` parses the request line, validates the version and method, checks restricted paths, handles cart routes, and checks file existence and `If-Modified-Since`. For a normal file `GET`, it returns `None` and `handle_client()` streams the file.
- **Chunked transfer:** `send_file_in_chunks()` reads files in 1 KB chunks and sends each as a hex-length-prefixed chunk, ending with a zero-length chunk.
- **Thread safety:** all reads and writes to the shared `cart` dictionary are guarded by `cart_lock`.

## Limitations

- The proxy supports plain HTTP only (no `CONNECT` tunneling for HTTPS) and does no caching.
- Each connection serves a single request (`Connection: close`).
- Static files are always served with `Content-Type: text/html`.
- Only the first 4096 bytes (web) or 8192 bytes (proxy) of a request are read.
- Path traversal protection is minimal, so do not expose this server to untrusted networks.

## Authors

- Avleen Kaur Virdi
- Luu Dang Thanh Ha

CMPT 371, Simon Fraser University (Fall 2025)
