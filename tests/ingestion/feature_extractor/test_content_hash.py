import hashlib

from ingestion.feature_extractor.content_hash import hash_file


def test_hash_file_matches_direct_sha256(tmp_path):
    path = tmp_path / "track.bin"
    path.write_bytes(b"some audio bytes" * 100)

    assert hash_file(str(path)) == hashlib.sha256(path.read_bytes()).hexdigest()


def test_hash_file_is_deterministic(tmp_path):
    path = tmp_path / "track.bin"
    path.write_bytes(b"identical content")

    assert hash_file(str(path)) == hash_file(str(path))


def test_hash_file_differs_on_different_content(tmp_path):
    path_a = tmp_path / "a.bin"
    path_b = tmp_path / "b.bin"
    path_a.write_bytes(b"content A")
    path_b.write_bytes(b"content B")

    assert hash_file(str(path_a)) != hash_file(str(path_b))


def test_hash_file_streams_in_chunks_larger_than_one_chunk(tmp_path):
    path = tmp_path / "large.bin"
    # Larger than the module's internal chunk size to exercise the streaming loop.
    path.write_bytes(b"x" * (2 * 1024 * 1024 + 17))

    assert hash_file(str(path)) == hashlib.sha256(path.read_bytes()).hexdigest()


def test_hash_file_empty_file(tmp_path):
    path = tmp_path / "empty.bin"
    path.write_bytes(b"")

    assert hash_file(str(path)) == hashlib.sha256(b"").hexdigest()
