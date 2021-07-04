import enum
import select
import socket
import time
import traceback
from heapq import heappop
from typing import NamedTuple, TextIO, Callable, Any, TypeVar, Coroutine, Optional

T = TypeVar('T')


class SessionFinished(Exception):
    pass


class IOIntention(enum.Enum):
    read = 'read'
    write = 'write'
    none = 'none'


class Session:
    # optional because client sockets don't have this right away
    # but we're using the same ._connect method which requires an address
    address: Optional[str]
    file: TextIO
    socket: socket.socket

    # TODO - see if other mechanisms for getting/setting the generator work better
    #  for instance, lambdas with closure, or properties which can't be set to None
    # Doesn't change, it just generates functions which we call with `Session` instances
    # Only optional for bureaucratic reasons, that I need to create objects in a certain order
    # Otherwise, once it's set, it's never optional anymore
    _generator: Optional[Coroutine]

    # TODO - same comment as above: use smth like lambdas with closures OR properties
    #  instead of Optional[]
    # This keeps changing. It's always the next function returned by the generator
    # (until the generator finishes, and doesn't return anything anymore)
    # Optional, because in order to obtain this, the session already has to exist
    # (well not technically true, but it simplifies things)
    _next_callback: Optional[Callable[["Session"], Any]]

    initial_callback: Callable[["Session"], Any]

    io_intention: IOIntention

    def __init__(self, address, file, socket_, next_callback, initial_callback, io_intention):
        self.address = address
        self.file = file
        self.socket = socket_
        self._next_callback = next_callback
        self.initial_callback = initial_callback
        self.io_intention = io_intention

        self._generator = initial_callback(self)
        x = 0

    def _make_progress(self, result: Any):
        """DO NOT CALL THIS DIRECTLY! It's meant do be called from Reactor.make_progress"""
        try:
            # For example, continuing command_server with the awaited result (the line)
            self._next_callback = self._generator.send(result)

        except StopIteration as err:
            raise SessionFinished from err

        except Exception as err:
            print(f"An unexpected exception has occurred: {type(err)}: {err}")
            traceback.print_exc()
            raise SessionFinished from err

    def call_next_callback(self):
        # 1. ensure the session is started
        # 2. call self.next_callback(self)
        if self._next_callback is None:
            self._next_callback = self._generator.send(None)

        self._next_callback(self)

    # TODO - this looks like we're creating a socket server framework
    def write(self, raw_bytes):
        self.socket.sendall(raw_bytes)

    def close(self):
        self._generator.close()
        self.file.close()
        self.socket.close()

    def intends_read(self):
        return self.io_intention == IOIntention.read

    def intends_write(self):
        return self.io_intention == IOIntention.write


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


class Reactor:
    _instance: "Reactor" = None

    def __init__(self):
        self.sessions = {}  # type: dict[socket.socket, Optional[Session]]

        # TODO - remove self.server_callbacks. The Session now has an .initial_callback slot
        # here we keep the server sockets. They'll be used when ready to read
        self.server_callbacks = {}  # type: dict[socket.socket, Callable]

        self.events = []  # type: list[ScheduledEvent]

        self._current_session = None

    def start_reactor(self):
        try:
            if not self.server_callbacks:
                # todo - this is silly. Sure, we shouldn't be able to start the
                #  reactor without anything for it to run BUT, that doesn't mean it
                #  should require a server socket!
                raise Exception(
                    "Can't start the reactor without any server sockets! "
                    "Please uses reactor.add_server_socket_and_callback() before calling .start_reactor()"
                )

            # todo - this could/should happen in .add_server_socket_and_callback()
            for srv_socket in self.server_callbacks:
                self.sessions[srv_socket] = None

            while True:
                # ready_to_read, ready_to_write, _ = select.select(self.sessions, self.sessions, [], 0.1)
                read_candidates = [
                    socket_ for socket_, session in self.sessions.items() if
                    session is None or session.intends_read()
                ]
                write_candidates = [
                    socket_ for socket_, session in self.sessions.items() if
                    session and session.intends_write()
                ]
                ready_to_read, ready_to_write, _ = select.select(
                    read_candidates,
                    write_candidates,
                    [],
                    0.1
                )
                # if ready_to_read:
                #     print(f"start_reactor: {len(ready_to_read)} ready to read: \n{ready_to_read}\n\n")
                # if ready_to_write:
                #     print(f"start_reactor: {len(ready_to_write)} ready to write: \n{ready_to_write}\n\n")

                for r_ready_socket in ready_to_read:
                    if r_ready_socket in self.server_callbacks:
                        assert isinstance(r_ready_socket, socket.socket)
                        original_socket = r_ready_socket
                        r_ready_socket, address = r_ready_socket.accept()
                        self._connect(
                            r_ready_socket, address, self.server_callbacks[original_socket],
                            IOIntention.read,
                        )
                        continue

                    # TODO - this looks weird, right?
                    #  ...do we JUST call the next callback?
                    #  ...don't we add anything to any queue?
                    #  Well the next callback's job is to call reactor.make_progress
                    #  which sets the next_callback
                    session = self.sessions[r_ready_socket]
                    self._current_session = session
                    session.call_next_callback()

                # TODO - what if the same socket is ready for both read and write?
                #  Would be a weird situation! Server sockets, in my mental model
                #  should listen, and client sockets should send. Well, client sockets
                #  should receive stuff as well.
                #  ...and what about client-created sockets? Those do both things
                # wait a minute! so server sockets can indeed be read-only BUT
                # client sockets are read-write.
                # At this point I realised I don't know if this distinction
                # between read/write matters OR if it matters a lot and I'm a n00b.
                # Also... do we really need to wait until we can write? Is that a thing?
                for w_ready_socket in ready_to_write:
                    session = self.sessions[w_ready_socket]
                    self._current_session = session
                    session.call_next_callback()

                self._current_session = None

                # run scheduled events at the scheduled time
                while self.events and self.events[0].event_time <= time.monotonic():
                    event = heappop(self.events)
                    event.task()
        finally:
            for srv_socket in self.server_callbacks:
                try_closing_the_server_socket(srv_socket)

    def _connect(self, s: socket.socket, address, async_callback, io_intention):
        sess = Session(
            address, s.makefile(), s, None, initial_callback=async_callback,
            io_intention=io_intention
        )
        self.sessions[s] = sess

        # TODO - I don't think we need this anymore.
        #  update, I think we still need it. ._connect is called right when we're ready to read,
        #  meaning we need to react right now! (If we don't, for example, the welcome message in
        #  command_server is not displayed
        # This line looks really weird! Without it, nothing works, but it doesn't look natural!
        # so this actually runs the callbacks, but it's weird as hell!
        # why (None) ? I guess that's a detail of how stuff works.
        # because: "TypeError: can't send non-None value to a just-started coroutine"
        # sess.next_callback = sess.generator.send(None)
        self._current_session = sess
        sess._make_progress(None)  # noqa

    def _disconnect(self, s: socket.socket):
        # TODO - when do we close server sockets? :/
        #  ...after a certain amount of time of them not being used
        #  is a reasonable approach
        self.sessions[s].close()
        # self.sessions[s].generator.close()
        # self.sessions[s].file.close()
        # s.close()
        del self.sessions[s]

    @classmethod
    def get_instance(cls) -> "Reactor":
        if not cls._instance:
            cls._instance = cls()

        return cls._instance

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

    def make_progress(self, session: Session, result, next_intention: IOIntention):
        """This appears to need to be a public method"""
        try:
            # accessing protected member! Yes!
            # This protected member is made to be called exactly
            # from here!
            session._make_progress(result)  # noqa
        except SessionFinished:
            self._disconnect(session.socket)

    def add_client_socket_and_callback(self, client_sock: socket.socket, async_callback):
        self.sessions[client_sock] = Session(
            address=None,
            file=client_sock.makefile(),
            socket_=client_sock,
            next_callback=None,
            initial_callback=async_callback,
            io_intention=IOIntention.write,
        )

    def get_current_session(self):
        return self._current_session


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


def create_async_client_socket(address):
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect(address)
    client_socket.setblocking(False)
    return client_socket
