import importlib.util
import unittest


class RuntimeTests(unittest.TestCase):
    def test_automatic_ports_remain_reserved_and_do_not_collide(self):
        self.assertIsNotNone(importlib.util.find_spec('backend.runtime'), 'Automatic port binding is missing')
        from backend.runtime import bind_server_socket
        with bind_server_socket(0) as first, bind_server_socket(0) as second:
            self.assertEqual(first.getsockname()[0], '127.0.0.1')
            self.assertNotEqual(first.getsockname()[1], second.getsockname()[1])
            self.assertGreater(first.getsockname()[1], 0)
