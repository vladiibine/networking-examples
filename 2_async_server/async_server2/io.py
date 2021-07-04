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
def simple_http_get(url, port=80, headers=None) -> bytes:
    """Simple interface to make an HTTP GET request

     Return the entire request (line,headers,body) as raw bytes
     """
    # can't be this simple!
    # Need to
    # 1. create a client socket
    # 2. wait for it until it's ready to send
    # 3. send the data
    # 4. wait for it until it's ready to receive
    # 5. receive stuff, parsing as per RFC2616 (content-length header OR dunno... \r\n\r\n ? repeated 'b' ?)
    # 6. return result

    # This can be done in the current model.
    # We must create and add to the reactor somehow the (socket, callback) pair
    # 1. simple_http_get (shg) creates the socket
    # 2. shg adds the (socket, get_result) pair to the reactor?
    # 3. when socket is ready to read, we read
    # 4. OPTIONAL: in case the response is too big,
    #       wait until it's again ready to read, so we don't block
    # 5. ...so now we have the result. How do we make_progress
    #    on the initial callback?
    # 5.1. do we create a mapping between something and something else (sockets,sessions)?
    #       doesn't seem like good logic can result from here.
    # 5.2. do we do some callback things?
    # 5.3. do we return some Futures, which we resolve at this point?

    # I think the futures thing makes the most sense
    # result = yield get_result
    # return result
    client_socket = create_async_client_socket((url, port))

    done = False
    result = None
    calling_session = Reactor.get_instance().get_current_session()

    @types.coroutine
    def send_request(request_bytes):
        def send_request_inner(session: Session):
            try:
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
            result = session.file.readline()
            result_buffer = result
            while not result:
                result = session.file.readline()
                result_buffer += result



            Reactor.get_instance().make_progress(session, result_buffer, IOIntention.none)
        result = yield receive_response_inner
        return result


    # TODO - quite interesting!
    #  this function has to return a "generator", so basically act just like
    #  command_server. Therefore it must itself `await` for 2 results:
    #  1. await send_request()
    #  2. await receive_response()
    #  ...where send_request and receive_response should again be
    #  @types.coroutine functions using the yield keyword, defining an inner function
    #  AND calling reactor.make_progress
    #  Idea! Don't I already have a `receive_response` function?
    #  ...well, kind of. `readline()` is kind of like that
    async def make_http_request(s: Session):
        # TODO - keep yielding some kind of "WAIT!!!" until the future is done
        nonlocal done
        # we're ready to write baby!
        raw_request = (
            b"GET / HTTP/1.1\r\n"
            b"User-Agent: guy-creating-http-server-sorry-for-spam\r\n"
            b"Reach-me-at: vlad.george.ardelean@gmail.com\r\n"
            b"\r\n"
        )
        none = await send_request(raw_request)
        response = await receive_response(none)

        print("setting done do true")
        done = True
        nonlocal result
        result = response

        Reactor.get_instance().make_progress(calling_session, response, IOIntention.none)

        # TODO - get the former session, and make progress!

        # this hopefully just raises StopIteration and disconnects this socket
        # ...update...or it fails?
        # Reactor.get_instance().make_progress(s, None, IOIntention.none)

    Reactor.get_instance().add_client_socket_and_callback(client_socket, make_http_request)

    @types.coroutine
    def noop(*a, **kw):
        print("in noop")
        pass

    # need to yield a function which will be called with a session
    # when will it be called?
    # when the original socket is ready to do something
    # what must it do?
    #  ...well, we've got no business with the original socket
    #  ...so we must return the same kind of "signal" to "continue waiting"
    #  ... as long as we haven't finished returning the response
    # how do we know when we finished returning the response?
    # >>> we can set some state somewhere, that our other socket is ready to read
    # what's this magic "signal" we're talking about?
    # >>> can it be a Future?
    # >>> or can it just be a function which continuously yields functions which yield?
    while not done:
        print("Nooping")
        yield noop

    return result

