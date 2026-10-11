"""Local HTTP OSS simulator: tests exercise the real official SDK, never a cloud account."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import md5
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from urllib.parse import parse_qs, quote, unquote, urlsplit
import uuid
import xml.etree.ElementTree as ET

import alibabacloud_oss_v2 as oss
import pytest

from oss_toolkit import OSSManager, Settings

NOW = "2026-01-17T11:55:14.000Z"


def crc(data: bytes) -> str:
    value = oss.crc.Crc64(0)
    value.update(data)
    return str(value.sum64())


@dataclass
class Store:
    objects: dict[str, bytes] = field(default_factory=dict)
    metadata: dict[str, dict] = field(default_factory=dict)
    uploads: dict[str, dict] = field(default_factory=dict)
    part_calls: dict[int, int] = field(default_factory=dict)
    range_calls: dict[int, int] = field(default_factory=dict)
    fail_part: int | None = None
    fail_range: int | None = None
    fail_gets: int = 0
    corrupt_crc: bool = False
    pages: int = 0
    lock: Lock = field(default_factory=Lock)


@pytest.fixture
def local_oss(tmp_path):
    store = Store()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def target(self):
            parsed = urlsplit(self.path)
            parts = unquote(parsed.path).split("/", 2)
            return (parts[2] if len(parts) > 2 else ""), parse_qs(parsed.query, keep_blank_values=True)

        def respond(self, status=200, data=b"", headers=None, *, head=False):
            self.send_response(status)
            self.send_header("x-oss-request-id", "local-test-request")
            if not headers or "Content-Length" not in headers:
                self.send_header("Content-Length", str(len(data)))
            for name, value in (headers or {}).items():
                self.send_header(name, str(value))
            self.end_headers()
            if not head:
                self.wfile.write(data)

        def error(self, code, status=500, *, head=False):
            body = f"<Error><Code>{code}</Code><Message>local test error</Message><RequestId>local-test-request</RequestId></Error>".encode()
            self.respond(status, body, {"Content-Type": "application/xml"}, head=head)

        def object_headers(self, key, data):
            return {
                "ETag": '"' + md5(data).hexdigest() + '"',
                "Last-Modified": "Sat, 17 Jan 2026 11:55:14 GMT",
                "Content-Type": store.metadata.get(key, {}).get("content_type", "application/octet-stream"),
                "Content-Length": str(len(data)),
                "x-oss-storage-class": "Standard",
                "x-oss-hash-crc64ecma": "1" if store.corrupt_crc else crc(data),
            }

        def do_HEAD(self):
            key, _ = self.target()
            if key not in store.objects:
                return self.error("NoSuchKey", 404, head=True)
            self.respond(200, headers=self.object_headers(key, store.objects[key]), head=True)

        def do_GET(self):
            key, query = self.target()
            if "list-type" in query:
                with store.lock:
                    store.pages += 1
                prefix = query.get("prefix", [""])[0]
                keys = sorted(key for key in store.objects if key.startswith(prefix))
                start = int(query.get("continuation-token", ["0"])[0])
                count = min(int(query.get("max-keys", ["1000"])[0]), 2)
                selected = keys[start:start + count]
                root = ET.Element("ListBucketResult")
                for name, text in (("Name", "test-bucket"), ("Prefix", prefix), ("KeyCount", str(len(selected))),
                                   ("MaxKeys", str(count)), ("IsTruncated", str(start + count < len(keys)).lower()), ("EncodingType", "url")):
                    ET.SubElement(root, name).text = text
                if start + count < len(keys):
                    ET.SubElement(root, "NextContinuationToken").text = str(start + count)
                for name in selected:
                    content = ET.SubElement(root, "Contents")
                    for tag, text in (("Key", quote(name, safe="")), ("Size", str(len(store.objects[name]))),
                                      ("LastModified", NOW), ("ETag", '"' + md5(store.objects[name]).hexdigest() + '"'), ("StorageClass", "Standard")):
                        ET.SubElement(content, tag).text = text
                return self.respond(data=ET.tostring(root), headers={"Content-Type": "application/xml"})
            if "uploadId" in query:
                upload_id = query["uploadId"][0]
                upload = store.uploads[upload_id]
                root = ET.Element("ListPartsResult")
                for name, text in (("Bucket", "test-bucket"), ("Key", key), ("UploadId", upload_id), ("IsTruncated", "false")):
                    ET.SubElement(root, name).text = text
                for number, data in sorted(upload["parts"].items()):
                    part = ET.SubElement(root, "Part")
                    for name, text in (("PartNumber", str(number)), ("Size", str(len(data))), ("ETag", '"' + md5(data).hexdigest() + '"'),
                                       ("LastModified", NOW), ("HashCrc64ecma", crc(data))):
                        ET.SubElement(part, name).text = text
                return self.respond(data=ET.tostring(root), headers={"Content-Type": "application/xml"})
            if key not in store.objects:
                return self.error("NoSuchKey", 404)
            if store.fail_gets:
                store.fail_gets -= 1
                return self.error("InternalError")
            data = store.objects[key]
            headers = self.object_headers(key, data)
            range_header = self.headers.get("Range")
            if range_header:
                start_text, end_text = range_header.removeprefix("bytes=").split("-")
                start, end = int(start_text), int(end_text) if end_text else len(data) - 1
                with store.lock:
                    store.range_calls[start] = store.range_calls.get(start, 0) + 1
                if store.fail_range == start:
                    return self.error("InternalError")
                block = data[start:end + 1]
                headers.update({"Content-Length": str(len(block)), "Content-Range": f"bytes {start}-{end}/{len(data)}"})
                return self.respond(206, block, headers)
            self.respond(200, data, headers)

        def do_PUT(self):
            key, query = self.target()
            data = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            if "uploadId" in query:
                number = int(query["partNumber"][0])
                with store.lock:
                    store.part_calls[number] = store.part_calls.get(number, 0) + 1
                if store.fail_part == number:
                    return self.error("InternalError")
                store.uploads[query["uploadId"][0]]["parts"][number] = data
                return self.respond(headers={"ETag": '"' + md5(data).hexdigest() + '"', "x-oss-hash-crc64ecma": crc(data)})
            if key in store.objects and self.headers.get("x-oss-forbid-overwrite") == "true":
                return self.error("FileAlreadyExists", 409)
            copy_source = self.headers.get("x-oss-copy-source")
            if copy_source:
                source = unquote(copy_source).lstrip("/").split("/", 1)[1]
                store.objects[key] = store.objects[source]
                body = f'<CopyObjectResult><ETag>"{md5(store.objects[key]).hexdigest()}"</ETag><LastModified>{NOW}</LastModified></CopyObjectResult>'.encode()
                return self.respond(data=body, headers={"Content-Type": "application/xml", "x-oss-hash-crc64ecma": crc(store.objects[key])})
            store.objects[key] = data
            store.metadata[key] = dict(content_type=self.headers.get("Content-Type"))
            self.respond(headers={"ETag": '"' + md5(data).hexdigest() + '"', "x-oss-hash-crc64ecma": crc(data)})

        def do_POST(self):
            key, query = self.target()
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            if "uploads" in query:
                upload_id = uuid.uuid4().hex
                store.uploads[upload_id] = {"key": key, "parts": {}, "content_type": self.headers.get("Content-Type")}
                xml = f"<InitiateMultipartUploadResult><Bucket>test-bucket</Bucket><Key>{key}</Key><UploadId>{upload_id}</UploadId></InitiateMultipartUploadResult>".encode()
                return self.respond(data=xml, headers={"Content-Type": "application/xml"})
            if "uploadId" in query:
                if key in store.objects and self.headers.get("x-oss-forbid-overwrite") == "true":
                    return self.error("FileAlreadyExists", 409)
                upload = store.uploads[query["uploadId"][0]]
                root = ET.fromstring(body)
                parts = [int(element.text) for element in root.iter() if element.tag.endswith("PartNumber")]
                data = b"".join(upload["parts"][number] for number in parts)
                store.objects[key] = data
                store.metadata[key] = dict(content_type=upload["content_type"])
                del store.uploads[query["uploadId"][0]]
                root = ET.Element("CompleteMultipartUploadResult")
                ET.SubElement(root, "Bucket").text = "test-bucket"
                ET.SubElement(root, "Key").text = key
                ET.SubElement(root, "ETag").text = '"' + md5(data).hexdigest() + '"'
                return self.respond(data=ET.tostring(root), headers={"Content-Type": "application/xml", "x-oss-hash-crc64ecma": crc(data)})
            self.error("InvalidRequest", 400)

        def do_DELETE(self):
            key, query = self.target()
            if "uploadId" in query:
                store.uploads.pop(query["uploadId"][0], None)
            else:
                store.objects.pop(key, None)
            self.respond(204)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = f"http://127.0.0.1:{server.server_port}"

    def manager(*, attempts=1, workers=1):
        cfg = oss.config.load_default()
        cfg.region = "cn-hangzhou"
        cfg.endpoint = endpoint
        cfg.use_path_style = True
        cfg.retry_max_attempts = attempts
        cfg.credentials_provider = oss.credentials.StaticCredentialsProvider("test-access-key", "test-secret")
        client = oss.Client(cfg)
        settings = Settings(bucket="test-bucket", endpoint=endpoint, workers=workers,
                            part_size=1024 * 1024, max_attempts=attempts, checkpoint_dir=tmp_path / "checkpoints")
        return OSSManager(settings, client=client)

    yield store, manager
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
