import dataclasses
import select
import socket
import time
import traceback
import types
from heapq import heappop
from typing import NamedTuple, TextIO, Callable, Any, TypeVar, Coroutine, Optional


T = TypeVar('T')


class SessionFinished(Exception):
    pass


@dataclasses.dataclass
class Session:
    address: str
    file: TextIO
    socket: socket.socket

    # Doesn't change, it just generates functions which we call with `Session` instances
    generator: Coroutine

    # This keeps changing. It's always the next function returned by the generator
    # (until the generator finishes, and doesn't return anything anymore)
    # Optional, because in order to obtain this, the session already has to exist
    # (well not technically true, but it simplifies things)
    next_callback: Optional[Callable[["Session"], Any]]

    def make_progress(self, result: Any):
        """DO NOT CALL THIS DIRECTLY! It's meant do be called from Reactor.make_progress"""
        try:
            # For example, continuing nonblocking_caser with the awaited result (the line)
            self.next_callback = self.generator.send(result)

        except StopIteration as err:
            raise SessionFinished from err

        except Exception as err:
            print(f"An unexpected exception has occurred: {type(err)}: {err}")
            traceback.print_exc()
            raise SessionFinished from err


class ScheduledEvent(NamedTuple):
    event_time: float
    task: Any  # todo - add typing


def try_closing_the_server_socket(server_socket: socket.socket):
    if server_socket:
        for mode in (socket.SHUT_RD, socket.SHUT_WR, socket.SHUT_RDWR):
            try:
                server_socket.shutdown(socket.SHUT_RD)
            except OSError:
                print(f"vlad: failed to shut down the server in mode {mode}")
        server_socket.close()




# I don't know how to create an `async def readline()` at this point.
# async def readline():
#     def inner(session: Session, socket_: socket.socket):
#         line = session.file.readline()
#         Reactor.get_instance().make_progress(socket_, line)
#
#     line = inner
#     return line


class Reactor:
    _instance: "Reactor" = None

    def __init__(self):
        self.sessions = {}  # type: dict[socket.socket, Optional[Session]]
        self.server_callbacks = {}  # type: dict[socket.socket, Callable]

        self.events = []  # type: list[ScheduledEvent]

    def start_reactor(self):
        try:
            if not self.server_callbacks:
                raise Exception(
                    "Can't start the reactor without any server sockets! "
                    "Please uses reactor.add_server_socket_and_callback() before calling .start_reactor()"
                )

            for srv_socket in self.server_callbacks:
                self.sessions[srv_socket] = None

            while True:
                ready_to_read, _, _ = select.select(self.sessions, [], [], 0.1)
                for ready_socket in ready_to_read:
                    if ready_socket in self.server_callbacks:
                        assert isinstance(ready_socket, socket.socket)
                        original_socket = ready_socket
                        ready_socket, address = ready_socket.accept()
                        self._connect(ready_socket, address, self.server_callbacks[original_socket])
                        continue

                    session = self.sessions[ready_socket]
                    session.next_callback(session)

                    # run scheduled events at the scheduled time
                    while self.events and self.events[0].event_time <= time.monotonic():
                        event = heappop(self.events)
                        event.task()
        finally:
            for srv_socket in self.server_callbacks:
                try_closing_the_server_socket(srv_socket)

    def _connect(self, s: socket.socket, address, async_callback):
        generator = async_callback(s)
        self.sessions[s] = Session(address, s.makefile(), s, generator, None)

        # This line looks really weird! Without it, nothing works, but it doesn't look natural!
        # so this actually runs the callbacks, but it's weird as hell!
        # why (None) ? I guess that's a detail of how stuff works.
        # because: "TypeError: can't send non-None value to a just-started coroutine"
        self.sessions[s].next_callback = generator.send(None)

    def _disconnect(self, s: socket.socket):
        # TODO - when do we close server sockets? :/
        #  ...after a certain amount of time of them not being used
        #  is a reasonable approach
        self.sessions[s].generator.close()
        self.sessions[s].file.close()
        s.close()
        del self.sessions[s]

    @classmethod
    def get_instance(cls):
        if not cls._instance:
            cls._instance = cls()

        return cls._instance

    def get_address_of(self, s: socket.socket) -> str:
        """Not sure about this method. Should the reactor keep a reference to all the addresses
        from which connections were made?
        """
        return self.sessions[s].address

    def add_server_socket_and_callback(self, s: socket.socket, callback):
        """
        :param s: This is a server socket, meaning we'll not use this to send/recv, but
            we'll only use it to accept(). accept() creates a client socket, that we can use
            for actually sending/receiving data. It's important to distinguish server from
            client sockets (though both of these are on the server...not sure how to call them)
        :param callback: whatever function the client of the Reactor wants to execute.
            Notice that this entire thing assumes a synchronous programming style, I think!
        """
        self.server_callbacks[s] = callback

    def make_progress(self, session: Session, result):
        """This appears to need to be a public method"""
        try:
            session.make_progress(result)
        except SessionFinished:
            self._disconnect(session.socket)


def create_async_server_socket(host, port, reuse: bool = False):
    """
    :param host:
    :param port:
    :param reuse: If true, allows shutting down the server and starting it up
        right away. Otherwise, we have to wait 1min before starting it up again
        https://stackoverflow.com/questions/4465959/python-errno-98-address-already-in-use
        In production, you'd want this set to `false`.
    :return:
    """
    # socket.socket, bind, accept, listen, send, (recv to do), close, shutdown
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if reuse:
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((host, port))
    server_socket.listen()
    server_socket.setblocking(False)
    return server_socket
