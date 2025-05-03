import zmq

__all__ = ['Driver', 'DriverError', 'ConnectionTimedOut', 'ServerRequestError']

class DriverError(Exception):
    """Base error for driver."""


class ConnectionTimedOut(DriverError):
    """No DB response."""


class ServerRequestError(IOError):
    """Error while making any Server requests."""


class Driver(object):
    def __init__(self, method='tcp', url='127.0.0.1',
                 port=8000, timeout=2*1000):
        """Create NanoDB driver.

        :param method: Method use to connect to the db.
        :type method: st.
        :param url: Url of the the server.
        :type url: str.
        :param port: Port used to communicate with the server.
        :type port: int.
        :param timeout: Time in second before timeout the connection
        :type timeout: int.
        """
        self.settings = {
            'method': method,
            'db_url': url,
            'db_port': port,
            'timeout': timeout
        }
        self.socket = self._init_socket()

    def _init_socket(self):
        """ Initialize a socket based on driver settings

        :return: socket
        """
        connect_url = "{0[method]}://{0[db_url]}:{0[db_port]}".format(self.settings)
        context = zmq.Context()
        socket = context.socket(zmq.REQ)
        socket.setsockopt(zmq.LINGER, 0)
        socket.connect(connect_url)
        return socket

    def _send_command(self, cmd_name, data=None):
        """Send command to nanodb server and return response.

        :param cmd_name: Name of the command to send
        :type cmd_name: str.
        :param data: Optional data to send
        :type data: dict.
        :rtype : dict.
        :raises: ConnectionTimedOut, ServerRequestError
        """
        payload = {
            'cmd': cmd_name
        }

        if data is not None:
            payload['data'] = data

        self.socket.send_json(payload)
        poller = zmq.Poller()
        poller.register(self.socket, zmq.POLLIN)

        if poller.poll(self.settings.get('timeout')):
            ret = self.socket.recv_json()
        else:
            self.socket = self._init_socket()
            raise ConnectionTimedOut()

        if ret.get('status') == "error":
            raise ServerRequestError(ret.get('error'))
        else:
            return ret.get('data')

    @property
    def is_connected(self):
        """Return True is the driver can connect to the server

        :rtype : bool.
        """
        try:
            self._send_command("ping")
        except ConnectionTimedOut:
            return False
        else:
            return True

    def list_cubes(self):
        """Return list of nanocubes and details information

        :return: list.
        """
        return self._send_command("list")

    def get_information(self, cube_name):
        """Return cube details of a cube

        :param cube_name: name of the selected cube
        :type cube_name: str.
        :return: dict.
        """
        return self._send_command("info", {
            "cube": cube_name
        })

    def serialize(self, cube_name, path=None):
        """Serialize cube in a .nano file and return the name of the file

        :param cube_name: cube to serialize
        :type cube_name: str.
        :return: str.
        """
        msg = { "cube": cube_name }
        if path is not None:
            msg['path'] = path

        return self._send_command("serialize", msg)

    def create_cube(self, input_file, config_file):
        """Create a cube based input file and config file

        :param input_file: CSV containing cube data
        :type input_file: str.
        :param config_file: YAML containing cube configuration
        :type config_file: str.
        :return: None
        """
        return self._send_command("create", {
            "input": input_file,
            "config": config_file
        })

    def load_cube(self, nano_file):
        """Load cube in DB from a .nano file

        :param nano_file: .nano containing serialized DB
        :return: None
        """
        return self._send_command("load", {
            "file": nano_file
        })

    def drop(self, cube_name):
        """Drop cube in the DB

        :param cube_name: cube to drop
        :return: None
        """
        return self._send_command("drop", {
            "cube": cube_name
        })

    def close_connection(self):
        self.socket.close()
