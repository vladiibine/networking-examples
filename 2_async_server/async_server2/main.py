"""
Check __init__.py for documentation/usage
"""
import dataclasses
from typing import Callable, Coroutine, Any

from .server import Reactor, create_async_server_socket, Session
from .io import readline, simple_http_get


@dataclasses.dataclass
class Command:
    name: str
    func: Callable[[bytes], bytes]
    is_async: bool = False  # whether the command is to be executed asynchronously

    def case_self(self):
        return self.func(self.name.encode())

    def switching_to_msg(self):
        return b"<Switching to %s cased mode>\r\n\r\n" % self.case_self()

    def echo_msg(self, msg: bytes):
        return b"%s-cased: %s\r\n\r\n" % (self.case_self(), self.func(msg))

    def handle_command(self, *args) -> bytes:
        return self.func(*args)

    @staticmethod
    async def handle_command_async(*args) -> Coroutine[Any, Any, bytes]:
        result = await simple_http_get(*args)  # todo - fix typing

        return b"after making the response, got:\r\n" + result.encode() + b"\r\n\r\n"


def handle_http(url_bytes) -> bytes:
    print(f"dummy: handling HTTP GET for url {url_bytes}")

    return b"dummy handler of HTTP -> to be implemented\r\n\r\n"


async def command_server(s: Session):
    cmd_quit = 'quit'
    cmd_upper = 'upper'
    cmd_title = 'title'
    cmd_lower = 'lower'
    cmd_http = 'http'
    cmd_help = 'help'

    possible_modes = {
        cmd_upper: Command(cmd_upper, bytes.upper, ),
        cmd_title: Command(cmd_title, bytes.title, ),
        cmd_lower: Command(cmd_lower, bytes.lower, ),
    }
    commands = {
        cmd_http: Command(cmd_help, handle_http, is_async=True),
    }

    mode = cmd_upper
    # calling this function looks too low-level.
    # Let's make the handler receive a Session instead
    print(f"Received connection from {s.address}")

    try:
        s.write(b"<Welcome to the echo-server! Starting in upper case mode>\r\n")
        s.write(b"<To see the available commands, type \"help\" and press return>\r\n\r\n")

        while True:
            line = (await readline()).strip()

            if line == cmd_quit:
                s.write(b"bye!\r\n")
                return

            if line == cmd_help:
                s.write(
                    b"Available commands: \r\n"
                    b"help - shows the available commands\r\n"
                    b"quit - quits the session\r\n"
                    b"upper - sets the echoing mode to UPPER case\r\n"
                    b"lower - sets the echoing mode to lower case\r\n"
                    b"title - sets the echoing mode to Title case\r\n"
                    b"http <url> - make a HTTP GET request to <url> and print the response line & headers\n\r"
                    b"\r\n"
                )
            elif line in possible_modes:
                for mode_candidate in possible_modes:
                    if mode is not mode_candidate and line == mode_candidate:
                        s.write(possible_modes[line].switching_to_msg())
                        mode = mode_candidate
            elif line:
                line_parts = line.split()
                if len(line_parts) > 1:
                    # commands
                    if line_parts[0] in commands:
                        cmd = commands[line_parts[0]]
                        if cmd.is_async:
                            result = await cmd.handle_command_async(*line_parts[1:])
                        else:
                            result = cmd.handle_command(*line_parts[1:])

                        s.write(result)
                    else:
                        s.write(possible_modes[mode].echo_msg(line.encode('utf-8')))
                else:
                    s.write(possible_modes[mode].echo_msg(line.encode('utf-8')))

            print(f"From {s.address} got {line}")
    finally:
        print(f"{s.address} quit")


if __name__ == '__main__':
    reactor = Reactor.get_instance()

    server_socket = create_async_server_socket('localhost', 1848, reuse=True)
    reactor.add_server_socket_and_callback(server_socket, command_server)

    reactor.start_reactor()
