# learning about sockets
# using the book "retele de calculatoare structuri, programe, aplicatii" (Nicolae Tomai)
"""
This file implements a very simple and incomplete HTTP server.
There's just 1 thread, the requests are handled synchronously on it.
This is meant to illustrate how to use the socket library.

Errors are not handled properly, rather it's a mess!

Usage:
$ python simple_socket_server.py

..then in another shell
$ curl -i 'http://localhost:8084'
"""
import socket


def sync_read(client_socket: socket.socket, bufsize=4096):
    content_part = client_socket.recv(bufsize)
    content_buffer = content_part

    while content_part != b'':
        # This ignores the body of the request.
        # If I wanted to properly read the body, I'd have to
        # begin implementing RFC2616. This is out of scope
        if content_buffer.endswith(b'\r\n\r\n'):
            return content_buffer

        content_part = client_socket.recv(bufsize)
        content_buffer += content_part


def try_closing_the_server_socket(server_socket: socket.socket):
    # this part seems to fail sometimes, I have no idea what's going on here really
    # I'm basically trying to close the listening socket, so I can kill the server
    # and restart it again quickly after killing it.
    if server_socket:
        try:
            server_socket.shutdown(socket.SHUT_RD)
            print(f"vlad: succeeded shutting down the server (read)")
        except OSError:
            print(f"vlad: shutting down the server socket failed (read)")

        try:
            server_socket.shutdown(socket.SHUT_WR)
            print(f"vlad: succeeded shutting down the server (write)")
        except OSError:
            print(f"vlad: shutting down the server socket failed (write)")

        try:
            server_socket.shutdown(socket.SHUT_RDWR)
            print(f"vlad: succeeded shutting down the server (read/write)")
        except OSError:
            print(f"vlad: shutting down the server socket failed (read/write)")
        server_socket.close()


def main():
    server_socket = None
    try:
        # socket.socket, bind, accept, listen, send, (recv to do), close, shutdown
        print(f"vlad: starting up...")
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        print(f"vlad: created the socket")
        host = 'localhost'
        port = 8084
        server_socket.bind((host, port))
        print(f"vlad: socket is bound")
        server_socket.listen()
        print(f"vlad: listening")
        while True:
            client_socket, address = server_socket.accept()
            print(f"vlad: accepted a connection from {address}")
            request = sync_read(client_socket)
            print(f"vlad: received this request {request}")

            client_socket.send(b'HTTP/1.1 200 ok\r\n\r\nyoyoyoy!\r\n')
            print(f"vlad: sent back a response")
            client_socket.shutdown(socket.SHUT_RDWR)
            print(f"vlad: the client socket was shut down")
            client_socket.close()
            print(f"vlad: the client socket is now closed")

    except KeyboardInterrupt:
        try_closing_the_server_socket(server_socket)
    finally:
        try_closing_the_server_socket(server_socket)


if __name__ == '__main__':
    main()
