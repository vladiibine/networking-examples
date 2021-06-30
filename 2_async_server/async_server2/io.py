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
