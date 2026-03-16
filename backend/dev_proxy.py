"""Helpers for the local frontend development proxy."""

from __future__ import annotations


def iter_response_chunks(response, chunk_size: int = 8192):
    """Yield upstream response bytes without waiting for the full body when possible."""
    buffered_reader = getattr(getattr(response, "fp", None), "read1", None)
    read_chunk = buffered_reader if callable(buffered_reader) else response.read

    while True:
        chunk = read_chunk(chunk_size)
        if not chunk:
            break
        yield chunk


def iter_ndjson_lines(response):
    """Yield NDJSON lines from an upstream HTTP response."""
    while True:
        line = response.readline()
        if not line:
            break
        yield line


def write_chunked_body(target, chunks) -> None:
    """Write a chunked HTTP/1.1 body to a writable binary stream."""
    for chunk in chunks:
        if not chunk:
            continue
        target.write(f"{len(chunk):X}\r\n".encode("ascii"))
        target.write(chunk)
        target.write(b"\r\n")
    target.write(b"0\r\n\r\n")
