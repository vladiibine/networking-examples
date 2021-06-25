# learning about sockets
# using the book "retele de calculatoare structuri, programe, aplicatii" (Nicolae Tomai)
"""
Doing the same thing as in 1_simple_server, but asynchronously
Inspired by Raymond Hettinger's example:
 https://pybay.com/site_media/slides/raymond2017-keynote/async_examples.html

TODO - further reading: https://docs.python.org/3.8/howto/sockets.html#socket-howto

Usage:
$ python async_server.py

..then in another shell
$ telnet localhost 1984
"""
import select
import socket
import time
import types
from heapq import heappop
from typing import Callable, Any, TypeVar
from typing import NamedTuple, Optional, TextIO, Coroutine


T = TypeVar('T')


def server_stuff(whatever: T) -> T:
    """Decorator to simply mark things that are most likely needed only by the server

    Why? Because I wrote a bunch of functions, and the code "compiled". That means that
    can be a lower level layer, used by higher level ones
    (so it's easy to separate in different files).

    UPDATE: I was wrong about "everything was compiling". This entire server is polluted
    with business logic and needs to be refactored. I'll continue marking things as
    `server_stuff` or `business_logic`, but just so I can start from a concrete idea
    about where I'd move the thing.
    """
    return whatever


def business_logic(whatever: T) -> T:
    """Analogous to `server_stuff`, but mark pieces of code which definitely
    shouldn't be in the server library, with the purpose of removing them later
    """
    return whatever


sessions = server_stuff({})  # type: dict[socket.socket, Optional[Session]]

# todo - add typing for the callable
callbacks = server_stuff({})  # type: dict[socket.socket, Callable[[Any, str], Any]]

# TODO - add typing for coroutine
generators = server_stuff({})  # type: dict[socket.socket, Coroutine]
events = server_stuff([])  # type: list[ScheduledEvent]


@server_stuff
class Session(NamedTuple):
    address: str
    file: TextIO


@server_stuff
class ScheduledEvent(NamedTuple):
    event_time: float
    task: Any  # todo - add typing


@server_stuff
def async_read(client_socket: socket.socket, bufsize=4096):
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


@server_stuff
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


@server_stuff
def add_session(s: socket.socket, address):
    sessions[s] = Session(address, s.makefile())
    on_connect(s)


@server_stuff
@business_logic
def on_connect(s: socket.socket):
    """Yeah, this function should be provided as an API to the clients"""
    g = nonblocking_caser(s)  # HERE! business logic instantiation
    generators[s] = g  # ...and here, we're connecting the business logic to the server stuff
    callbacks[s] = g.send(None)


@types.coroutine
@server_stuff
def readline(s: socket.socket):
    """A non-blocking readline to use with two-way generators"""
    # TODO - preferably replace generators with async functions
    def inner(s_, line_):
        g = generators[s_]
        try:
            callbacks[s_] = g.send(line_)
        except StopIteration:
            disconnect(s_)

    line = yield inner
    return line


@business_logic
async def nonblocking_caser(s: socket.socket):
    cmd_quit = 'quit'
    cmd_upper = 'upper'
    cmd_title = 'title'
    cmd_lower = 'lower'
    cmd_help = 'help'

    mode = cmd_upper
    print(f"Received connection from {sessions[s].address}")

    try:
        s.sendall(b"<Welcome to the echo-server! Starting in upper case mode>\r\n")
        s.sendall(b"<To see the available commands, type \"help\" and press return>\r\n")
        while True:
            line = await readline(s)

            if line == cmd_quit:
                s.sendall(b"quit\r\n")
                return

            if line == cmd_help:
                s.sendall(b"Available commands: \r\n"
                          b"help - shows the available commands\r\n"
                          b"quit - quits the session\r\n"
                          b"upper - sets the echoing mode to UPPER case\r\n"
                          b"lower - sets the echoing mode to lower case\r\n"
                          b"title - sets the echoing mode to Title case\r\n"
                          )
                continue

            if mode is not cmd_title and line == cmd_title:
                s.sendall(b"<switching to Title case mode>\r\n")
                mode = cmd_title
                continue

            if mode is not cmd_upper and line == cmd_upper:
                s.sendall(b"<switching to UPPER case mode>\r\n")
                mode = cmd_upper
                continue

            if mode is not cmd_lower and line == cmd_lower:
                s.sendall(b"<Switching to lower case mode>\r\n")
                mode = cmd_lower

            if mode is cmd_upper:
                s.sendall(b"UPPER-cased: %a \r\n" % line.upper())
            elif mode is cmd_title:
                s.sendall(b"Title-cased: %a \r\n" % line.title())
            elif mode is cmd_lower:
                s.sendall(b"lower-cased: %a \r\n" % line.title())

            print(f"From {sessions[s].address} got {line}")
    finally:
        print(f"{sessions[s].address} quit")


# todo - inline this. has a single usage.
@server_stuff
def on_disconnect(s: socket.socket):
    g = generators.pop(s)
    g.close()


@server_stuff
def disconnect(s: socket.socket):
    on_disconnect(s)
    sessions[s].file.close()
    s.close()
    del sessions[s]
    del callbacks[s]


@server_stuff
def start_reactor(host, port):
    server_socket = None
    try:
        # socket.socket, bind, accept, listen, send, (recv to do), close, shutdown
        print(f"vlad: starting up...")
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        print(f"vlad: created the socket")
        # host = 'localhost'
        # port = 8084
        server_socket.bind((host, port))
        print(f"vlad: socket is bound")
        server_socket.listen()
        print(f"vlad: listening")
        server_socket.setblocking(False)
        # This should allow me to restart the server right after I shut it down
        # ...but it doesn't work
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sessions[server_socket] = None
        while True:
            ready_to_read, _, _ = select.select(sessions, [], [], 0.1)
            for ready_socket in ready_to_read:
                if ready_socket is server_socket:  # type: socket.socket
                    assert isinstance(ready_socket, socket.socket)
                    ready_socket, address = ready_socket.accept()
                    add_session(ready_socket, address)
                    continue

                # todo - readline? why not read until done? This might block and also
                #  reading a line has no defined semantics
                # Got it! it's readline because we must read until "something"
                # so either read until a certain character is reached, or read a
                # certain number of bytes. Reading a certain number of bytes is the
                # tricky part. How do we know how many bytes? :P RFC2616
                # (the http 1.1 protocol paper) specifies lots of rules, but implementing
                # them is out of scope
                line = sessions[ready_socket].file.readline()
                if line:
                    # todo - do we need rstrip?
                    callbacks[ready_socket](ready_socket, line.rstrip())
                else:
                    disconnect(ready_socket)

                # run scheduled events at the scheduled time
                while events and events[0].event_time <= time.monotonic():
                    event = heappop(events)
                    event.task()
    finally:
        # TODO - server shutdown first?
        server_socket.shutdown(socket.SHUT_RDWR)
        server_socket.close()


if __name__ == '__main__':
    start_reactor('localhost', 1948)
