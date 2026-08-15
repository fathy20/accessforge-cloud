import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from urllib.parse import quote
import uuid

from backend.tests.test_rbac_permissions import AppHarness


PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


class TestSecureUploads(unittest.TestCase):
    def setUp(self):
        self.app = AppHarness()
        self.email = "secure-upload@example.test"
        self.app.create_user(self.email)
        self.headers = self.app.headers(self.email)
        self.storage_tmp = Path(tempfile.mkdtemp(prefix="secure_upload_storage_"))
        self.upload_dir = self.storage_tmp / "uploads"
        self.output_dir = self.storage_tmp / "outputs"
        self.upload_dir.mkdir()
        self.output_dir.mkdir()
        self.app.main.UPLOAD_DIR = self.upload_dir
        self.app.main.OUTPUT_DIR = self.output_dir

    def tearDown(self):
        self.app.close()
        shutil.rmtree(self.storage_tmp, ignore_errors=True)

    def upload(self, filename="report.pdf", contents=PDF_BYTES, mime="application/pdf"):
        return self.app.client.post(
            "/api/uploads",
            headers=self.headers,
            files=[("files", (filename, contents, mime))],
        )

    def upload_record(self, response):
        self.assertEqual(response.status_code, 200, response.text)
        from backend.models import Upload

        with self.app.database.SessionLocal() as session:
            return session.query(Upload).filter(Upload.id == response.json()[0]["id"]).one()

    def test_traversal_filenames_do_not_change_storage_tree(self):
        before = sorted(path.relative_to(self.storage_tmp).as_posix() for path in self.storage_tmp.rglob("*"))

        for filename in ("../../evil.txt", r"..\..\evil.txt"):
            with self.subTest(filename=filename):
                response = self.upload(filename, b"not an accepted artifact", "text/plain")
                self.assertEqual(response.status_code, 415)

        after = sorted(path.relative_to(self.storage_tmp).as_posix() for path in self.storage_tmp.rglob("*"))
        self.assertEqual(after, before)

    def test_size_limit_stops_stream_and_removes_partial_file(self):
        self.app.main.MAX_UPLOAD_SIZE = 10
        before = sorted(path.relative_to(self.storage_tmp).as_posix() for path in self.storage_tmp.rglob("*"))

        response = self.upload(contents=PDF_BYTES, mime="application/pdf")

        self.assertEqual(response.status_code, 413)
        after = sorted(path.relative_to(self.storage_tmp).as_posix() for path in self.storage_tmp.rglob("*"))
        self.assertEqual(after, before)

    def test_pdf_extension_with_non_pdf_bytes_is_rejected(self):
        response = self.upload(contents=b"plain text", mime="application/pdf")

        self.assertEqual(response.status_code, 415)
        self.assertEqual(list(self.upload_dir.iterdir()), [])

    def test_genuine_pdf_uses_a_server_generated_storage_name(self):
        response = self.upload("client-report.pdf")
        upload = self.upload_record(response)

        stored_path = Path(upload.storage_path)
        self.assertTrue(stored_path.is_file())
        self.assertNotIn("client-report.pdf", stored_path.name)
        self.assertEqual(upload.original_name, "client-report.pdf")
        self.assertEqual(upload.mime, "application/pdf")
        self.assertEqual(upload.scan_state, "not_scanned")

    def test_reuploading_a_name_creates_two_immutable_paths(self):
        first = self.upload_record(self.upload("same-name.pdf", PDF_BYTES))
        second = self.upload_record(self.upload("same-name.pdf", PDF_BYTES + b"second"))

        self.assertNotEqual(first.storage_path, second.storage_path)
        self.assertTrue(Path(first.storage_path).is_file())
        self.assertTrue(Path(second.storage_path).is_file())
        self.assertEqual(Path(first.storage_path).read_bytes(), PDF_BYTES)
        self.assertEqual(Path(second.storage_path).read_bytes(), PDF_BYTES + b"second")

    def test_sha256_is_persisted_for_the_stored_bytes(self):
        upload = self.upload_record(self.upload(contents=PDF_BYTES))

        stored_bytes = Path(upload.storage_path).read_bytes()
        self.assertEqual(upload.sha256, hashlib.sha256(stored_bytes).hexdigest())

    def test_output_download_rejects_backslash_traversal_with_404(self):
        from backend.models import Job, JobStatus

        output_name = "owned-output.pdf"
        (self.output_dir / output_name).write_bytes(PDF_BYTES)
        user_id = self.app.user_id(self.email)
        with self.app.database.SessionLocal() as session:
            session.add(
                Job(
                    user_id=user_id,
                    module_key="check_control",
                    status=JobStatus.done,
                    input_refs={},
                    output_refs={
                        "files": [
                            {
                                "id": "output-1",
                                "storage_name": output_name,
                                "original_name": output_name,
                                "size_bytes": len(PDF_BYTES),
                                "sha256": hashlib.sha256(PDF_BYTES).hexdigest(),
                                "mime": "application/pdf",
                            }
                        ]
                    },
                )
            )
            session.commit()

        traversal = quote(r"..\..\owned-output.pdf", safe="")
        response = self.app.client.get(
            f"/api/downloads/{traversal}",
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 404)
        self.assertNotIn(PDF_BYTES, response.content)

    def test_user_cannot_download_another_users_upload(self):
        upload = self.upload_record(self.upload())
        other_email = "other-secure-upload@example.test"
        self.app.create_user(other_email)
        other_headers = self.app.headers(other_email)

        forbidden = self.app.client.get(
            f"/api/uploads/{upload.id}/download",
            headers=other_headers,
        )
        missing = self.app.client.get(
            f"/api/uploads/{uuid.uuid4()}/download",
            headers=other_headers,
        )

        self.assertEqual(forbidden.status_code, 404)
        self.assertEqual(forbidden.status_code, missing.status_code)
        self.assertEqual(forbidden.json(), missing.json())

    def test_upload_download_and_delete_emit_sanitized_audit_events(self):
        from backend.models import AuditLog

        upload = self.upload_record(self.upload(contents=PDF_BYTES))
        downloaded = self.app.client.get(
            f"/api/uploads/{upload.id}/download",
            headers=self.headers,
        )
        self.assertEqual(downloaded.status_code, 200)
        deleted = self.app.client.delete(
            f"/api/uploads/{upload.id}",
            headers=self.headers,
        )
        self.assertEqual(deleted.status_code, 200)

        with self.app.database.SessionLocal() as session:
            events = (
                session.query(AuditLog)
                .filter(AuditLog.entity_id == upload.id)
                .order_by(AuditLog.action)
                .all()
            )

        self.assertEqual({event.action for event in events}, {"delete", "download", "upload"})
        serialized = json.dumps([event.metadata_json for event in events])
        self.assertNotIn(PDF_BYTES.decode("latin1"), serialized)
        for event in events:
            self.assertEqual(event.metadata_json["original_name"], upload.original_name)
            self.assertEqual(event.metadata_json["sha256"], upload.sha256)
            self.assertEqual(event.metadata_json["mime"], upload.mime)

    def test_delete_missing_file_removes_row_and_audits_failure(self):
        from backend.models import AuditLog, Upload

        upload = self.upload_record(self.upload())
        Path(upload.storage_path).unlink()

        response = self.app.client.delete(
            f"/api/uploads/{upload.id}",
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 500)
        with self.app.database.SessionLocal() as session:
            self.assertIsNone(session.query(Upload).filter(Upload.id == upload.id).first())
            event = (
                session.query(AuditLog)
                .filter(AuditLog.action == "delete", AuditLog.entity_id == upload.id)
                .one()
            )
            self.assertEqual(event.metadata_json["filesystem_status"], "failed")
            self.assertTrue(event.metadata_json["filesystem_error"])


if __name__ == "__main__":
    unittest.main()
