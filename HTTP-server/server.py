import socket
import os


def juliet(host, port):

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, port))
        sock.listen()

        conn_sock, conn_addr = sock.accept()

        with conn_sock:
            print("Connected by", conn_addr)
            while True: 
                data = conn_sock.recv(1024)
                print("Received", repr(data))
                
                if not data:
                    break

                method, path, version = parse(data.decode("utf-8"))
                print(method, path, version)

                message = response(method, path, version)
                
                conn_sock.sendall(message)

def parse(header):
    lines = header.split("\r\n")
    method, path, version = lines[0].split(" ")
    
    return method, path, version

def response(method, path, version):
    if method == "GET":
        filename = path.lstrip("/")

        if os.path.isfile(filename):
            print("File found:", filename)
            with open(filename, "rb") as f:
                body = f.read()

            if filename.endswith('.txt'):
                content_type = "text/plain"
            elif filename.endswith('.html'):
                content_type = "text/html"
            else:
                content_type = "application/octet-stream"  # Fallback

            headers = (
                f"{version} 200 OK\r\n"
                f"Content-Type: {content_type}\r\n"
                f"Content-Length: {len(body)}\r\n"
                "\r\n"
            ).encode()

            return headers + body
        else:
            print("File not found:", filename)
            body = b"404 File not found"
            headers = (
                f"{version} 404 Not Found\r\n"
                "Content-Type: text/plain\r\n"
                f"Content-Length: {len(body)}\r\n"
                "\r\n"
            ).encode()
            return headers + body

import sys
import argparse 
def main():
    # parser = argparse.ArgumentParser()
    # parser.add_argument("--host", type=str, default="localhost")
    # parser.add_argument("--port", type=int, default=8080)
    # args = parser.parse_args()

    # juliet(args.host, args.port)

    port = 80
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print("Invalid port")
            sys.exit(1)
    juliet("localhost", port)

if __name__ == "__main__":
    main()