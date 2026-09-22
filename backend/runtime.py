import socket


def bind_server_socket(port=0):
    """Keep the socket reserved until Uvicorn takes ownership; no port-picking race."""
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        server_socket.bind(('127.0.0.1', port))
        return server_socket
    except OSError:
        server_socket.close()
        raise
