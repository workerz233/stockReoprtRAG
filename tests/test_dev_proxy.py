import importlib
import io
import sys
import types
import unittest


class ReadOnlyResponse:
    def __init__(self) -> None:
        self.read_sizes = []
        self.read_calls = 0

    def read(self, size: int) -> bytes:
        self.read_sizes.append(size)
        self.read_calls += 1
        if self.read_calls == 1:
            return b"payload"
        return b""


class BufferedResponse:
    def __init__(self) -> None:
        self.lines = [b'{"idx": 0}\n', b'{"idx": 1}\n', b""]

    def readline(self) -> bytes:
        return self.lines.pop(0)


class DevProxyTests(unittest.TestCase):
    def setUp(self) -> None:
        sys.modules.pop("backend.dev_proxy", None)
        self.module = importlib.import_module("backend.dev_proxy")

    def test_iter_ndjson_lines_reads_one_line_at_a_time(self) -> None:
        response = BufferedResponse()

        chunks = list(self.module.iter_ndjson_lines(response))

        self.assertEqual(chunks, [b'{"idx": 0}\n', b'{"idx": 1}\n'])

    def test_iter_response_chunks_falls_back_to_read(self) -> None:
        response = ReadOnlyResponse()

        chunks = list(self.module.iter_response_chunks(response, chunk_size=32))

        self.assertEqual(chunks, [b"payload"])
        self.assertEqual(response.read_sizes, [32, 32])

    def test_write_chunked_body_encodes_each_chunk(self) -> None:
        target = io.BytesIO()

        self.module.write_chunked_body(target, [b'{"idx": 0}\n', b'{"idx": 1}\n'])

        self.assertEqual(
            target.getvalue(),
            b'B\r\n{"idx": 0}\n\r\nB\r\n{"idx": 1}\n\r\n0\r\n\r\n',
        )


if __name__ == "__main__":
    unittest.main()
