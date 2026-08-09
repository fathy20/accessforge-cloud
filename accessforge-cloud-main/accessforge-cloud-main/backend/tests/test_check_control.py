import os
import sys
import csv
import tempfile
import shutil
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

class TestCheckControlPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 1. Create tmpdir
        cls.tmpdir = tempfile.mkdtemp(prefix="cc_tests_")
        cls.workdir = Path(cls.tmpdir) / "work"
        (cls.workdir / "in").mkdir(parents=True)
        (cls.workdir / "out").mkdir(parents=True)
        cls.output_dir = Path(cls.tmpdir) / "outputs"
        cls.output_dir.mkdir(parents=True)

        cls.csv_path = Path(cls.tmpdir) / "checks.csv"
        with open(cls.csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["CHECK", "TASK", "TITLE"])
            writer.writeheader()
            writer.writerow({"CHECK": "A1", "TASK": "27-001-00", "TITLE": "Base inspection"})
            writer.writerow({"CHECK": "A2", "TASK": "27-002-00", "TITLE": "Expanded inspection"})
            writer.writerow({"CHECK": "C1", "TASK": "28-001-00", "TITLE": "Unrelated inspection"})

        # 2. Set DATABASE_URL to temporary SQLite
        cls.original_db_url = os.environ.get("DATABASE_URL")
        cls.db_path = Path(cls.tmpdir) / "test.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{cls.db_path}"

        # 3. Change cwd to tmpdir BEFORE importing backend modules
        cls.original_cwd = os.getcwd()
        os.chdir(cls.tmpdir)

        # 4. Remove cached backend modules if needed
        for m in list(sys.modules.keys()):
            if m == "backend" or m.startswith("backend."):
                del sys.modules[m]

        # 5. Import backend modules (now safe to import, they will use test env/cwd)
        import sqlalchemy as sa
        from sqlalchemy.orm import sessionmaker
        import backend.database as bd
        from backend.models import Base, User, UserRole, AppRole, Module
        from backend.auth import get_password_hash
        from backend.tools.sync_registry import sync_registry
        
        cls.test_engine = bd.engine
        Base.metadata.create_all(bind=cls.test_engine)
        cls.TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls.test_engine)

        with cls.TestSessionLocal() as db:
            user = User(email="test@test.com", hashed_password=get_password_hash("test"), full_name="Test")
            db.add(user)
            db.flush()
            cls.user_id = user.id
            db.add(UserRole(user_id=user.id, role=AppRole.super_admin))
            db.add(Module(key="check_control", name="Check Control", enabled=True))
            db.commit()
            sync_registry(db)

    @classmethod
    def tearDownClass(cls):
        try:
            # 1. Dispose test engine
            if hasattr(cls, "test_engine"):
                cls.test_engine.dispose()
                
            # 2. Clean backend modules from sys.modules
            for name in list(sys.modules):
                if name == "backend" or name.startswith("backend."):
                    sys.modules.pop(name, None)
                    
        finally:
            # 3. Restore DATABASE_URL
            if hasattr(cls, "original_db_url"):
                if cls.original_db_url is None:
                    os.environ.pop("DATABASE_URL", None)
                else:
                    os.environ["DATABASE_URL"] = cls.original_db_url
                    
            # 4. Restore original cwd
            if hasattr(cls, "original_cwd"):
                os.chdir(cls.original_cwd)
                
            # 5. Remove temporary directory
            if hasattr(cls, "tmpdir"):
                shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def _create_upload_and_job(self, file_path: Path):
        from backend.models import Upload, UploadKind, Job, JobStatus
        with self.TestSessionLocal() as db:
            upload = Upload(
                user_id=self.user_id,
                original_name=file_path.name,
                storage_path=str(file_path),
                kind=UploadKind.csv,
                mime="text/csv",
                size_bytes=file_path.stat().st_size if file_path.exists() else 100,
            )
            db.add(upload)
            db.flush()
            
            job = Job(
                user_id=self.user_id,
                module_key="check_control",
                status=JobStatus.queued,
                input_refs={"files": [upload.id], "check": "A2", "data_source": "file"},
            )
            db.add(job)
            db.commit()
            return str(job.id)

    def test_handler_a2(self):
        import pandas as pd
        from worker.handlers import check_control
        job = {"id": "test-1", "input_refs": {"check": "A2", "data_source": "file"}}
        outputs = check_control(job, [str(self.csv_path)], self.workdir, lambda p, m: None)

        self.assertEqual(len(outputs), 1)
        out_path = Path(outputs[0])
        self.assertEqual(out_path.name, "CHECKS_A2.xlsx")

        df = pd.read_excel(out_path)
        checks = df["CHECK"].astype(str).str.upper().tolist()
        self.assertIn("A1", checks)
        self.assertIn("A2", checks)
        self.assertNotIn("C1", checks)
        self.assertIn("_matched", df.columns)
        self.assertTrue((df["_matched"].astype(str).str.upper() == "A2").all())

    def test_runner_success(self):
        import backend.main as bm
        from backend.models import Job
        job_id = self._create_upload_and_job(self.csv_path)

        with mock.patch.object(bm, "SessionLocal", self.TestSessionLocal), \
             mock.patch.object(bm, "OUTPUT_DIR", self.output_dir):
            bm.run_job_background(job_id)

        with self.TestSessionLocal() as db:
            job = db.query(Job).filter(Job.id == job_id).first()
            self.assertEqual(job.status, "done")
            self.assertIn("files", job.output_refs)
            self.assertTrue(len(job.output_refs["files"]) > 0)
            
            filename = job.output_refs["files"][0]["url"].split("/")[-1]
            physical = self.output_dir / filename
            self.assertTrue(physical.exists())

    def test_runner_failure(self):
        import backend.main as bm
        from backend.models import Job
        job_id = self._create_upload_and_job(Path(self.tmpdir) / "missing.csv")

        with mock.patch.object(bm, "SessionLocal", self.TestSessionLocal), \
             mock.patch.object(bm, "OUTPUT_DIR", self.output_dir):
            bm.run_job_background(job_id)

        with self.TestSessionLocal() as db:
            job = db.query(Job).filter(Job.id == job_id).first()
            self.assertEqual(job.status, "failed")
            self.assertTrue(bool(job.error_message))
            self.assertEqual(len((job.output_refs or {}).get("files", [])), 0)

if __name__ == "__main__":
    unittest.main()
