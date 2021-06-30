import types
from .server import Session, Reactor


# TODO - why does this have to be a @types.coroutine again?
@types.coroutine
def readline():
    """A non-blocking readline to use with two-way generators"""

    # TODO - preferably replace generators with async functions
    def inner(session: Session):
        # socket_.makefile().readline() works just as well!
        line_ = session.file.readline()

        Reactor.get_instance().make_progress(session, line_)

    line = yield inner
    return line


@types.coroutine
def simple_http_get(url, headers=None) -> bytes:
    """Simple interface to make an HTTP GET request

     Return the entire request (line,headers,body) as raw bytes
     """
    def get_result():  # will be called with a session
        pass

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
    result = yield get_result
    return result
