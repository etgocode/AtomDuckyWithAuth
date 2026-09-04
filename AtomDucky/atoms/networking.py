import wifi
import socketpool
import gc
import time
import ipaddress
import sys
import os
import json
import errno
import select
import ssl

from atoms.hid import AtomDucky, load_payload_from_file
from atoms.config_man import ConfigMan
from atoms.atomble import sour_apple, samsung_ble_spam
from atoms.buttons import button, pixel
from atoms.colors import color

EAGAIN_BLOCK_TIME = 0.01
"seconds to wait when socket would block"

CERT_FILE = "/atoms/cert.pem"
KEY_FILE = "/atoms/key.pem"
TLS_PORT = 443


def file_exists(path):
    """CircuitPython has no os.path, so check existence via listdir() like code.py does."""
    folder, _, name = path.rpartition("/")
    return name in os.listdir(folder)


def button_pressed():
    return button.value

class WebHost:
    def __init__(self, ip, port, web_passwd):
        self.port = port
        self.ip = ip
        self.config = ConfigMan()
        """variables for session authentication"""
        self.tokens = set()
        self.web_passwd = web_passwd or None
        self.tls_enabled = file_exists(CERT_FILE) and file_exists(KEY_FILE)
        self.tls_context = None
        self.tls_socket = None
        self.start_web_server()
        if self.tls_enabled:
            self.start_tls_server()
        pixel.fill(color("cyan"))
        # don't leak secrets from requests in log if auth is enabled
        self.log_requests = self.web_passwd is None
        self.run_web_loop()

    def start_web_server(self):
        try:
            self.pool = socketpool.SocketPool(wifi.radio)
            self.server_socket = self.pool.socket(self.pool.AF_INET, self.pool.SOCK_STREAM)
            """
                PROTIP: without this line the program will scream EADDRINUSE with every soft reboot.
            """
            self.server_socket.setsockopt(self.pool.SOL_SOCKET, self.pool.SO_REUSEADDR, 1)
            # ^^
            self.server_socket.bind((str(self.ip), self.port))
            self.server_socket.listen(5)
            self.server_socket.settimeout(None)  # Use blocking mode
            print(f"Listening on http://{self.ip}:{self.port}")
        except OSError as e:
            """
                we used pool.SO_REUSEADDR, but just in case
            """
            pixel.fill(color("red"))
            if e.errno == errno.EADDRINUSE:
                print("Address already in use. Retrying...")
                self.server_socket.close()
                time.sleep(5)
                self.start_web_server()

    def start_tls_server(self):
        """Start an HTTPS listener on port {TLS_PORT} using {CERT_FILE} and {KEY_FILE}.
        If anything goes wrong (missing/invalid cert, no memory, ...) we log the error
        and keep serving plain HTTP on port 80."""
        try:
            self.tls_context = ssl.create_default_context()
            # clear CA bundle to save memory
            self.tls_context.load_verify_locations(cadata="")
            self.tls_context.load_cert_chain(CERT_FILE, KEY_FILE)
            tls_socket = self.pool.socket(self.pool.AF_INET, self.pool.SOCK_STREAM)
            tls_socket.setsockopt(self.pool.SOL_SOCKET, self.pool.SO_REUSEADDR, 1)
            tls_socket.bind((str(self.ip), TLS_PORT))
            tls_socket.listen(5)
            tls_socket.settimeout(None)
            # wrap the LISTENING socket: accept() now returns handshaken SSLSockets
            self.tls_socket = self.tls_context.wrap_socket(tls_socket, server_side=True)
            print(f"Listening on https://{self.ip}:{TLS_PORT}")
        except Exception as e:
            print("TLS setup failed, continuing with HTTP only:", repr(e))
            self.tls_enabled = False
            self.tls_context = None
            if self.tls_socket is not None:
                try:
                    self.tls_socket.close()
                except Exception:
                    pass
                self.tls_socket = None

    def _check_auth_required(self, path):
        if self.web_passwd is None:
            return False
        if path.startswith("/auth"):
            return False
        if path.startswith("/login.html"):
            return False
        return True
        
    def _validate_token(self, token):
        return token in self.tokens
        
    def _extract_token(self, request):
        for line in request.splitlines():
            if line.lower().startswith("cookie:"):
                for part in line.split(":"):
                    if part.strip().startswith("token="):
                        return part.split("=")[1].strip()
        return None
                
    
    def _generate_token(self):
        token = os.urandom(32).hex()
        self.tokens.add(token)
        return token
        
    def _is_authenticated(self, request, path):
        if not self._check_auth_required(path):
            return True
        token = self._extract_token(request)
        if token and self._validate_token(token):
            return True
        return False
    
    def _check_path(self, path):
        """check if path is allowed"""
        path = path.lstrip("/")
        if not path:
            return True
        allowed = ["index.html", "login.html", "atoms/_config"]
        if path in allowed:
            return True
        if path.startswith("static/"):
            return True
        if path.startswith("atoms/website_atoms/"):
            return True
        return False
        
    
    def read_file_in_chunks(self, path, chunk_size=1024):
        try:
            with open(path, 'rb') as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk
        except Exception as e:
            print(str(e))
            yield None

    def get_content_type(self, path):
        if path.endswith(".html"):
            return "text/html"
        elif path.endswith(".css"):
            return "text/css"
        elif path.endswith(".svg"):
            return "image/svg+xml"
        elif path.endswith(".ico"):
            return "image/x-icon"
        else:
            return "application/octet-stream"

    def send_with_retry(self, client_socket, data):
        while data:
            try:
                sent = client_socket.send(data)
                data = data[sent:]
            except OSError as e:
                if e.errno == errno.EAGAIN:
                    # socket blocks, wait a bit and retry
                    time.sleep(EAGAIN_BLOCK_TIME)
                    continue
                raise
    
    def read_full_request(self, client_socket):
        buf = bytearray(1024)
        request_bytes = bytearray()
        headers_done = False
        content_length = 0
        body_bytes_read = 0

        while True:
            try:
                received = client_socket.recv_into(buf)
            except OSError as e:
                if e.errno == errno.EAGAIN:
                    # socket blocks, wait a bit and retry
                    time.sleep(EAGAIN_BLOCK_TIME)
                    continue
                raise
            if received == 0:
                break
            request_bytes.extend(buf[:received])

            if not headers_done:
                try:
                    header_end = request_bytes.index(b"\r\n\r\n")
                    headers_done = True
                    headers = request_bytes[:header_end].decode()
                    for line in headers.splitlines():
                        if line.lower().startswith("content-length:"):
                            content_length = int(line.split(":")[1].strip())
                    body_bytes_read = len(request_bytes) - (header_end + 4)
                except ValueError:
                    continue
            else:
                body_bytes_read += received

            if headers_done and body_bytes_read >= content_length:
                break

        return request_bytes.decode()
    
    def handle_request(self, client_socket):
        try:

            request = self.read_full_request(client_socket)
            if not request:
                return  # client closed without sending a request
            self.__debug_print("Request:", request)

            request_line = request.splitlines()[0]
            method, file_path, _ = request_line.split(" ")
            if file_path == "/":
                file_path = "/index.html"

            if not self._is_authenticated(request, file_path):
                if file_path == "/index.html":
                    file_path = "/login.html"
                else:
                    self.send_with_retry(client_socket, b"HTTP/1.1 401 Unauthorized\r\n\r\n")
                    return
            
            endpoint_handlers = {
                "/modify_payload": self.handle_modify_payload,
                "/handle_ble": self.handle_ble_callbacks,
                "/file_manager": self.handle_file_manager,
                "/single_payload": self.handle_single_payload,
                "/ret_templates": self.handle_ret_templates,
                "/edit_config": self.handle_edit_config,
                "/restart": self.handle_restart,
                "/inject": self.handle_inject,
                "/auth": self._handle_auth,
            }

            handler = None
            for ep, h in endpoint_handlers.items():
                if file_path.startswith(ep):
                    handler = h
                    break

            if handler:
                handler(client_socket, request)
            else:
                if self._check_path(file_path):
                    content_type = self.get_content_type(file_path)
                    headers = f"HTTP/1.1 200 OK\r\nContent-Type: {content_type}\r\n\r\n".encode()
                    self.send_with_retry(client_socket, headers)

                    for chunk in self.read_file_in_chunks(file_path[1:]):
                        if chunk is None:
                            response = b"HTTP/1.1 404 Not Found\r\n\r\n"
                            self.send_with_retry(client_socket, response)
                            break
                        self.send_with_retry(client_socket, chunk)
                else:
                    self.send_with_retry(client_socket, b"HTTP/1.1 403 Forbidden\r\n\r\n")
            gc.collect()
        except OSError as e:
            print("OSError in handle_request", str(e))
        finally:
            client_socket.close()

    def unpack_body_and_headers(self, req_lines):
        headers = {}
        body = ""
        is_body = False

        for line in req_lines[1:]:
            if line == "":
                is_body = True
                continue
            if is_body:
                body += line + "\n"
            else:
                key, value = line.split(": ", 1)
                headers[key] = value

        return headers, body.strip()

    def _handle_auth(self, client_socket, request):
        lines = request.splitlines()
        method, url, _ = lines[0].split(" ")
        
        if method != "POST":
            self.send_with_retry(client_socket, b"HTTP/1.1 405 Method Not Allowed\r\n\r\n")
            return
        
        headers, body = self.unpack_body_and_headers(lines)
        password = body.strip()
        
        if password == self.web_passwd:
            token = self._generate_token()
            response = json.dumps({"success": True})
            status = "200 OK"
            cookie = "Set-Cookie: token=%s; Path=/" % token
        else:
            response = json.dumps({"success": False, "error": "Invalid password"})
            status = "401 Unauthorized"
            cookie = "Set-Cookie: token=; Path=/; Max-Age=0"
            
        """send response"""
        self.send_with_retry(client_socket, (f"HTTP/1.1 {status}\r\n").encode())
        self.send_with_retry(client_socket, (f"{cookie}\r\n").encode())
        self.send_with_retry(client_socket, b"Content-Type: text/plain\r\n")
        self.send_with_retry(client_socket, (f"Content-Length: {len(response)}\r\n").encode())
        self.send_with_retry(client_socket, b"\r\n")
        self.send_with_retry(client_socket, response.encode())
        
    
    def handle_restart(self, client_socket, req=None):
        print("Restarting...")
        import supervisor
        response = b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nRestarting..."
        self.send_with_retry(client_socket, response)
        supervisor.reload()

    def handle_inject(self, client_socket, req=None):
        print("Injecting...")
        ducky = AtomDucky()
        payload = load_payload_from_file()
        gc.collect()
        response = b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nPayload Injected"
        self.send_with_retry(client_socket, response)
        if payload is not None:
            ducky.payloads_write(payload)
        gc.collect()

    def handle_file_manager(self, client_socket, request):
        request_lines = request.splitlines()
        method, url, _ = request_lines[0].split(" ")
        headers, body = self.unpack_body_and_headers(request_lines)
        
        self.__debug_print("Headers:", headers)
        self.__debug_print("Body:", body)
        if method == 'POST':
            response = "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nOk, but why POST Method?"
        elif method == 'GET':
            files = os.listdir()
            response_body = json.dumps(files)
            response = f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {len(response_body)}\r\n\r\n{response_body}"
        self.send_with_retry(client_socket, response.encode())

    def handle_ble_callbacks(self, client_socket, request):
        request_lines = request.splitlines()
        method, url, _ = request_lines[0].split(" ")
        headers, body = self.unpack_body_and_headers(request_lines)
    
        self.__debug_print("Headers:", headers)
        self.__debug_print("Body:", body)
        if method == 'POST':
            if body == "start_ble_spam_ios":
                pixel.fill(color("green"))
                response = b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nStopped the Sour Apple attack"
                sour_apple(stop_cb=button_pressed)
                pixel.fill(color("yellow"))
            elif body == "start_ble_spam_samsung":
                pixel.fill(color("green"))
                response = b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nStopped the Samsung BLE Spam"
                samsung_ble_spam(stop_cb=button_pressed)
                pixel.fill(color("yellow"))
        else:
            response = b"HTTP/1.1 400 Bad Request\r\nContent-Type: text/plain\r\n\r\nInvalid request method."
            pixel.fill(color("red"))
        self.send_with_retry(client_socket, response)

    def handle_single_payload(self, client_socket, request):
        request_lines = request.splitlines()
        method, url, _ = request_lines[0].split(" ")
        headers, body = self.unpack_body_and_headers(request_lines)
    
        self.__debug_print("Headers:", headers)
        self.__debug_print("Body:", body)
        if method == 'POST':
            print("Injecting...")
            ducky = AtomDucky()
            payload = body
            gc.collect()
            response = b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nSuccess!"
            self.send_with_retry(client_socket, response)   
            if payload is not None:
                ducky.payloads_write(payload, skip_release=True)
            gc.collect()  
    
    def handle_ret_templates(self, client_socket, request):
        request_lines = request.splitlines()
        method, url, _ = request_lines[0].split(" ")
        path, _, query = url.partition('?')
        params = dict(param.split('=') for param in query.split('&'))
        headers, body = self.unpack_body_and_headers(request_lines)

        self.__debug_print("Headers:", headers)
        self.__debug_print("Body:", body)
        if method == 'GET' and params.get('action') == 'read_list':
            file_list = os.listdir('/atoms/templates')
            if ".gitkeep" in file_list:
                file_list.remove(".gitkeep")
            content = json.dumps(file_list)
            print(content)
            response = f"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\n{content}"
            self.send_with_retry(client_socket, response.encode())
        if method == 'GET' and params.get('action') == 'read':
            template_name = params.get('name')
            self.read_payload(client_socket, folder='atoms/templates', name=template_name)
        elif method == 'POST' and params.get('action') == 'write':
            data = body
            template_name = params.get('name')
            # Name of the file can be maximum 16 chars
            if template_name != '' and len(template_name) < 16:
                self.write_payload(client_socket, data, folder='atoms/templates', name=template_name)
     
    def handle_modify_payload(self, client_socket, request):
        request_lines = request.splitlines()
        method, url, _ = request_lines[0].split(" ")
        path, _, query = url.partition('?')
        params = dict(param.split('=') for param in query.split('&'))

        headers, body = self.unpack_body_and_headers(request_lines)

        self.__debug_print("Headers:", headers)
        self.__debug_print("Body:", body)
        if method == 'GET' and params.get('action') == 'read':
            self.read_payload(client_socket)
        elif method == 'POST' and params.get('action') == 'write':
            data = body
            self.write_payload(client_socket, data)

    def handle_edit_config(self, client_socket, request):
        try:
            request_lines = request.splitlines()
            method, url, _ = request_lines[0].split(" ")
            path, _, query = url.partition('?')
            headers, body = self.unpack_body_and_headers(request_lines)

            self.__debug_print("Headers:", headers)
            self.__debug_print("Body:", body)
            
            if method == 'POST':
                try:
                    config_updates = json.loads(body)
                    valid_fields = {"IP", "SSID", "PASSW", "AP", "MODE", "WEB_PASSWD"}
                    if not all(field in valid_fields for field in config_updates.keys()):
                        response = "HTTP/1.1 400 Bad Request\r\n\r\nInvalid field in request body."
                    else:
                        self.config.edit_config(**config_updates)
                        response = "HTTP/1.1 200 OK\r\n\r\nConfig updated successfully."
                except ValueError:
                    response = "HTTP/1.1 400 Bad Request\r\n\r\nInvalid JSON in request body."
                except Exception as e:
                    print(str(e))
                    response = f"HTTP/1.1 500 Internal Server Error\r\n\r\nError updating config: {str(e)}"
            else:
                response = "HTTP/1.1 400 Bad Request\r\n\r\nInvalid request method."
            
            self.send_with_retry(client_socket, response)
        except Exception as e:
            print(f"Exception in handle_edit_config: {e}")
            response = f"HTTP/1.1 500 Internal Server Error\r\n\r\n{str(e)}"
            self.send_with_retry(client_socket, response)
 
    def read_payload(self, client_socket, folder="atoms", name="payload"):
        try:
            with open(f'/{folder}/{name}.txt', 'r') as f:
                content = f.read()
            response = f"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\n{content}"
        except Exception as e:
            print(str(e))
            response = f"HTTP/1.1 500 Internal Server Error\r\nContent-Type: text/plain\r\n\r\nError reading payload: {str(e)}"
        self.send_with_retry(client_socket, response.encode())
        
    def write_payload(self, client_socket, data, folder="atoms", name="payload"):
        try:
            with open(f'/{folder}/{name}.txt', 'w') as f:
                f.write(data)
            response = "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nPayload written successfully"
        except Exception as e:
            print(str(e))
            response = f"HTTP/1.1 500 Internal Server Error\r\nContent-Type: text/plain\r\n\r\nError writing payload: {str(e)}"
        self.send_with_retry(client_socket, response.encode())

    def _accept_and_handle(self, listener):
        """Accept a connection and serve it."""
        gc.collect()  # reclaim garbage before the (possibly TLS) handshake allocates much memory
        # if TLS, handshake happens here, which can fail
        try:
            client_socket, addr = listener.accept()
        except Exception as e:
            print("Accept failed:", repr(e))
            return
        print("Client connected from", addr)
        self.handle_request(client_socket)

    def run_web_loop(self):
        # CircuitPython's poll() returns the registered objects, not fds
        self._listeners = [self.server_socket]
        if self.tls_socket is not None:
            self._listeners.append(self.tls_socket)

        poller = select.poll()
        for listener in self._listeners:
            poller.register(listener, select.POLLIN)

        while True:
            for listener, _ in poller.poll():
                self._accept_and_handle(listener)

    def __debug_print(self, *args, **kwargs):
        if self.log_requests:
            print(*args, **kwargs)
