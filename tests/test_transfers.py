from datetime import datetime, timezone
from pathlib import Path

import pytest

from oss_toolkit.service import safe_download_path, service_error, upload_plan


@pytest.mark.parametrize("payload", [b"", "图片内容".encode(), b"a" * (3 * 1024 * 1024 + 11)], ids=["empty", "unicode", "multipart"])
def test_upload_download_roundtrip_with_real_sdk(local_oss, tmp_path, payload):
    store, factory = local_oss
    manager = factory(workers=2)
    source = tmp_path / "图片.png"
    source.write_bytes(payload)
    result = manager.upload(source, "图片/文生图.png")
    assert result["size"] == len(payload)
    assert store.objects["图片/文生图.png"] == payload
    assert manager.info("图片/文生图.png")["content_type"] == "image/png"
    destination = tmp_path / "out" / "图片.png"
    assert manager.download("图片/文生图.png", destination) == destination
    assert destination.read_bytes() == payload
    assert not list(destination.parent.glob("*.oss-part"))


@pytest.mark.parametrize("size", [5, 2 * 1024 * 1024 + 1])
def test_remote_overwrite_is_forbidden_by_server_even_for_multipart(local_oss, tmp_path, monkeypatch, size):
    store, factory = local_oss
    manager = factory()
    store.objects["same.bin"] = b"original"
    source = tmp_path / "source.bin"
    source.write_bytes(b"x" * size)
    # Simulate a file created by another uploader after our preflight query.
    monkeypatch.setattr(manager.client, "is_object_exist", lambda *args, **kwargs: False)
    with pytest.raises(Exception) as caught:
        manager.upload(source, "same.bin")
    assert service_error(caught.value).code == "FileAlreadyExists"
    assert store.objects["same.bin"] == b"original"
    manager.upload(source, "same.bin", overwrite=True)
    assert store.objects["same.bin"] == source.read_bytes()


def test_preflight_skips_existing_large_file_without_sending_parts(local_oss, tmp_path):
    store, factory = local_oss
    store.objects["same.bin"] = b"original"
    source = tmp_path / "source.bin"
    source.write_bytes(b"x" * (2 * 1024 * 1024))
    with pytest.raises(FileExistsError):
        factory().upload(source, "same.bin")
    assert not store.part_calls
    assert not store.uploads
    assert store.objects["same.bin"] == b"original"


def test_interrupted_upload_resumes_without_reuploading_completed_parts(local_oss, tmp_path):
    store, factory = local_oss
    manager = factory()
    source = tmp_path / "large.bin"
    source.write_bytes(b"r" * (3 * 1024 * 1024 + 11))
    store.fail_part = 2
    with pytest.raises(Exception):
        manager.upload(source, "large.bin")
    assert store.part_calls[1] == 1
    assert store.uploads
    store.fail_part = None
    manager.upload(source, "large.bin")
    assert store.part_calls[1] == 1
    assert store.objects["large.bin"] == source.read_bytes()
    assert not store.uploads


def test_interrupted_download_resumes_and_does_not_publish_partial_file(local_oss, tmp_path):
    store, factory = local_oss
    manager = factory()
    payload = b"d" * (3 * 1024 * 1024 + 11)
    store.objects["large.bin"] = payload
    store.fail_range = 1024 * 1024
    destination = tmp_path / "large.bin"
    with pytest.raises(Exception):
        manager.download("large.bin", destination)
    assert not destination.exists()
    assert store.range_calls[0] == 1
    store.fail_range = None
    manager.download("large.bin", destination)
    assert store.range_calls[0] == 1
    assert destination.read_bytes() == payload


def test_download_failure_preserves_existing_file_and_explicit_overwrite_works(local_oss, tmp_path):
    store, factory = local_oss
    manager = factory()
    store.objects["file.bin"] = b"remote data"
    destination = tmp_path / "file.bin"
    destination.write_bytes(b"local data")
    with pytest.raises(FileExistsError):
        manager.download("file.bin", destination)
    store.fail_gets = 1
    with pytest.raises(Exception):
        manager.download("file.bin", destination, overwrite=True)
    assert destination.read_bytes() == b"local data"
    manager.download("file.bin", destination, overwrite=True)
    assert destination.read_bytes() == b"remote data"


def test_sdk_retries_transient_errors(local_oss, tmp_path):
    store, factory = local_oss
    store.objects["retry.bin"] = b"success"
    store.fail_gets = 1
    destination = tmp_path / "retry.bin"
    factory(attempts=2).download("retry.bin", destination)
    assert destination.read_bytes() == b"success"
    assert store.fail_gets == 0


def test_crc_failure_does_not_replace_original(local_oss, tmp_path):
    store, factory = local_oss
    store.objects["file.bin"] = b"new content"
    store.corrupt_crc = True
    destination = tmp_path / "file.bin"
    destination.write_bytes(b"original")
    with pytest.raises(Exception):
        factory().download("file.bin", destination, overwrite=True)
    assert destination.read_bytes() == b"original"


def test_pagination_limit_and_search_filters(local_oss):
    store, factory = local_oss
    store.objects.update({"a.txt": b"a", "b.txt": b"b", "c.txt": b"c", "图片/文生图.PNG": b"12345", "图片/其它.png": b"123"})
    manager = factory()
    assert len(list(manager.list_objects())) == 5
    assert store.pages == 3
    assert len(list(manager.list_objects(limit=3))) == 3
    found = list(manager.search("文生图", pattern="*.png", min_size=4, max_size=6,
                                after=datetime(2026, 1, 1), before=datetime(2026, 2, 1, tzinfo=timezone.utc), limit=1))
    assert [item.key for item in found] == ["图片/文生图.PNG"]
    assert list(manager.search("文生图", pattern="*.png", case_sensitive=True)) == []
    pages = store.pages
    assert list(manager.list_objects(limit=0)) == []
    assert store.pages == pages


def test_batch_upload_skips_existing_and_excludes_credentials(local_oss, tmp_path):
    store, factory = local_oss
    root = tmp_path / "input"
    (root / "sub").mkdir(parents=True)
    (root / "a.txt").write_text("a")
    (root / "sub" / "b.txt").write_text("b")
    (root / ".env").write_text("fake secret")
    (root / ".ossenv").write_text("fake user secret")
    store.objects["docs/a.txt"] = b"original"
    report = factory().upload_directory(root, "docs")
    assert report.to_dict()["succeeded"] == 1
    assert report.to_dict()["skipped"] == 1
    assert store.objects["docs/a.txt"] == b"original"
    assert store.objects["docs/sub/b.txt"] == b"b"
    assert "docs/.env" not in store.objects
    assert "docs/.ossenv" not in store.objects


def test_batch_download_preserves_paths_rejects_traversal_and_reports_errors(local_oss, tmp_path):
    store, factory = local_oss
    store.objects.update({"docs/sub/a.txt": b"a", "docs/sub/b.txt": b"b", "docs/../../escape.txt": b"bad", "docs/": b""})
    output = tmp_path / "output"
    (output / "sub").mkdir(parents=True)
    (output / "sub" / "b.txt").write_bytes(b"existing")
    report = factory().download_directory("docs", output)
    assert report.to_dict()["succeeded"] == 1
    assert report.to_dict()["skipped"] == 1
    assert report.to_dict()["failed"] == 1
    assert (output / "sub" / "a.txt").read_bytes() == b"a"
    assert (output / "sub" / "b.txt").read_bytes() == b"existing"
    assert not (tmp_path / "escape.txt").exists()


def test_presigned_url_is_local_and_correctly_encoded(local_oss):
    store, factory = local_oss
    value = factory().signed_url("图片/a b.png", expires=300)
    assert value["method"] == "GET"
    assert "%E5%9B%BE%E7%89%87" in value["url"]
    assert "a%20b.png" in value["url"]
    assert "x-oss-signature=" in value["url"]
    assert store.pages == 0
    with pytest.raises(ValueError):
        factory().signed_url("file", expires=0)


def test_copy_and_explicit_single_file_delete(local_oss):
    store, factory = local_oss
    store.objects["source.txt"] = b"content"
    manager = factory()
    manager.copy("source.txt", "copied.txt")
    assert store.objects["copied.txt"] == b"content"
    with pytest.raises(ValueError):
        manager.delete("copied.txt")
    assert "copied.txt" in store.objects
    manager.delete("copied.txt", confirm=True)
    assert "copied.txt" not in store.objects


@pytest.mark.parametrize("key", ["../x", "/x", "a/../../x", "a\\x", "a//x", "a/./x", "a/C:evil", "CON.txt", "a/NUL", "x.", "x ", "x\x00"])
def test_unsafe_object_keys_rejected_for_local_paths(tmp_path, key):
    with pytest.raises(ValueError):
        safe_download_path(tmp_path, key)


def test_literal_percent_encoded_names_are_not_decoded(tmp_path):
    assert safe_download_path(tmp_path, "%2E%2E/file.txt") == tmp_path / "%2E%2E" / "file.txt"
