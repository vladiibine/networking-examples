import select
import socket
import time
import types
from heapq import heappop
from typing import NamedTuple, TextIO, Callable, Any, TypeVar, Coroutine, Optional


T = TypeVar('T')


class Session(NamedTuple):
    address: str
    file: TextIO
    callback: Callable


class ScheduledEvent(NamedTuple):
    event_time: float
    task: Any  # todo - add typing


def try_closing_the_server_socket(server_socket: socket.socket):
    # TODO - this entire function is BS. To be able to shut down a socket,
    #  as far as I know now, one needs to set certain options on it
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


@types.coroutine
def readline():
    """A non-blocking readline to use with two-way generators"""

    # TODO - preferably replace generators with async functions
    def inner(session: Session, socket_: socket.socket):
        # socket_.makefile().readline() works just as well!
        line_ = session.file.readline()

        Reactor.get_instance().make_progress(socket_, line_)

    line = yield inner
    return line


# I don't know how to create an `async def readline()` at this point.
# async def readline():
#     def inner(session: Session, socket_: socket.socket):
#         line = session.file.readline()
#         Reactor.get_instance().make_progress(socket_, line)
#
#     line = inner
#     return line



# todo - maybe the yield-based coroutine is necessary?
#  I think that `await` already does some wrapping/unwrapping
#  for us maybe?
# async def readline2():
#     def readline_inner(session: Session, socket_: socket.socket):
#         line_ = session.file.readline()
#         if line_:
#             g = Reactor.get_instance().get_generator(socket_)
#             try:
#                 Reactor.get_instance().add_callback(socket_, await g(line_))
#             except StopIteration:
#                 Reactor.get_instance().disconnect(socket_)
#
#     line = yield readline_inner


class Reactor:
    _instance: "Reactor" = None

    def __init__(self):
        self.sessions = {}  # type: dict[socket.socket, Optional[Session]]
        # todo - add typing for the callable
        self.callbacks = {}  # type: dict[socket.socket, Callable[[Any, str], Any]]
        self.server_callbacks = {}  # type: dict[socket.socket, Callable]

        # TODO - add typing for coroutine
        self.generators = {}  # type: dict[socket.socket, Coroutine]

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

                    self.callbacks[ready_socket](self.sessions[ready_socket], ready_socket)

                    # run scheduled events at the scheduled time
                    while self.events and self.events[0].event_time <= time.monotonic():
                        event = heappop(self.events)
                        event.task()
        finally:
            # TODO - server shutdown first?
            for srv_socket in self.server_callbacks:
                try_closing_the_server_socket(srv_socket)

    def _connect(self, s: socket.socket, address, async_callback):
        self.sessions[s] = Session(address, s.makefile(), async_callback)

        g = async_callback(s)
        self.generators[s] = g
        # This line looks really weird! Without it, nothing works, but it doesn't look natural!
        # so this actually runs the callbacks, but it's weird as hell!
        # why (None) ? I guess that's a detail of how stuff works.
        # because: "TypeError: can't send non-None value to a just-started coroutine"
        self.callbacks[s] = g.send(None)

    def _disconnect(self, s: socket.socket):
        # TODO - when do we close server sockets? :/
        #  ...after a certain ammount of time of them not being used
        #  is a reasonable approach
        g = self.generators.pop(s)
        g.close()
        self.sessions[s].file.close()
        s.close()
        del self.sessions[s]
        del self.callbacks[s]

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

    def make_progress(self, socket_, result):
        """This appears to need to be a public method"""
        g = self.generators[socket_]
        try:
            next_generator = g.send(result)
            self.callbacks[socket_] = next_generator
        except StopIteration:
            self._disconnect(socket_)


def create_async_server_socket(host, port):
    # socket.socket, bind, accept, listen, send, (recv to do), close, shutdown
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # TODO - in a real world scenario, you wouldn't want this line in production
    #  however, since this entire project is just a learning exercies, it's fine
    #  Explanation - this has the effect of allowing a restart of the server
    #  right after it was closed. Otherwise, we'd have to wait for 1 minute
    #  before being allowed to open a new connection on the same port
    #  https://stackoverflow.com/questions/4465959/python-errno-98-address-already-in-use
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((host, port))
    server_socket.listen()
    server_socket.setblocking(False)
    # This should allow me to restart the server right after I shut it down
    # ...but it doesn't work
    return server_socket
