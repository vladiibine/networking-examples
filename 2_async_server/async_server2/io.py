import types
from .server import Session, Reactor, create_async_client_socket, IOIntention


# TODO - why does this have to be a @types.coroutine again?
@types.coroutine
def readline():
    """A non-blocking readline to use with two-way generators"""

    # TODO - preferably replace generators with async functions
    def inner(session: Session):
        # socket_.makefile().readline() works just as well!
        result = session.file.readline()

        Reactor.get_instance().make_progress(session, result, IOIntention.none)

    line = yield inner
    return line


@types.coroutine
def simple_http_get(url, port=80, headers=None):
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
        res = yield receive_response_inner
        return res

    async def make_http_request(s: Session):
        # TODO - make the request using the proper path, not just /
        raw_request = (
            b"GET / HTTP/1.1\r\n"
            b"User-Agent: guy-creating-http-server-sorry-for-spam\r\n"
            b"Reach-me-at: vlad.george.ardelean@gmail.com\r\n"
            b"\r\n"
        )
        none = await send_request(raw_request)
        response = await receive_response(none)

        # see the `response` here? We're basically throwing that to line marked `3mfn5gwf`,
        # as the result. The generator for the original session which wanted to make an HTTP
        # call paused on line marked `3mfn5gwf`. We then set a callback on another socket on
        # line marked `b4g9a`. The callback is this function. When this function completes
        # and we have our result, we basically restart the previous generator with that result
        Reactor.get_instance().make_progress(calling_session, response, IOIntention.none)

    Reactor.get_instance().add_client_socket_and_callback(client_socket, make_http_request)  # line:b4g9a

    # `yield` works very well, BUT, I think that's just by accident.
    #  Sure, the `make_http_request` function will trigger progress, and make line 3mfn5gwf get
    #  the result and continue, but what if the socket in the initial session triggers first?
    #  ...then, the reactor will call the `yield`ed value, and this would blow up, because
    #  that result is None. That is why we still return a noop, which doesn't do any progress
    #  but is required for respecting the expectations of the reactor.
    result = yield noop  # line: 3mfn5gwf
    return result


def noop(*args, **kwargs):
    pass
