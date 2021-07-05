import types
from .server import Session, Reactor, create_async_client_socket, IOIntention


# TODO - why does this have to be a @types.coroutine again?
@types.coroutine
def readline():
    """A non-blocking readline to use with two-way generators"""

    # TODO - preferably replace generators with async functions
    def inner(session: Session):
        # socket_.makefile().readline() works just as well!
        line_ = session.file.readline()

        Reactor.get_instance().make_progress(session, line_, IOIntention.none)

    line = yield inner
    return line


@types.coroutine
def simple_http_get(url, port=80, headers=None) -> None:
    """Simple interface to make an HTTP GET request

     Return the entire request (line,headers,body) as raw bytes
     """
    client_socket = create_async_client_socket((url, port))

    calling_session = Reactor.get_instance().get_current_session()

    @types.coroutine
    def send_request(request_bytes):
        def send_request_inner(session: Session):
            try:
                # TODO - maybe we can't send the entire request at once.
                #  there might be a reason why both .send and .sendall exist
                result = session.socket.sendall(request_bytes)
            except BrokenPipeError as err:
                session.close()
                return

            # The result is None...whatever!
            Reactor.get_instance().make_progress(session, result, IOIntention.read)
        none = yield send_request_inner
        return none

    @types.coroutine
    def receive_response(none):
        def receive_response_inner(session: Session):
            # TODO - so... can we just "read a line"?
            #  isn't the line MAYBE chunked, and we have to yield control,
            #  and wait for the socket to be readable again?

            # Weird stuff happening here!
            # Some sites send me a '\n' first
            # Well I guess I should skip that
            result_part = session.file.readline()
            result_buffer = result_part

            while not result_part:
                result_part = session.file.readline()
                result_buffer += result_part

            Reactor.get_instance().make_progress(session, result_buffer, IOIntention.none)
        result = yield receive_response_inner
        return result

    async def make_http_request(s: Session):
        # we're ready to write baby!
        # TODO - send to the actual url provided by the client, not just to /
        raw_request = (
            b"GET / HTTP/1.1\r\n"
            b"User-Agent: guy-creating-http-server-sorry-for-spam\r\n"
            b"Reach-me-at: vlad.george.ardelean@gmail.com\r\n"
            b"\r\n"
        )
        none = await send_request(raw_request)
        response = await receive_response(none)

        Reactor.get_instance().make_progress(calling_session, response, IOIntention.none)

    Reactor.get_instance().add_client_socket_and_callback(client_socket, make_http_request)
