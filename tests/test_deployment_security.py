"""Local checks for deployment boundaries and restored source evidence."""
import hashlib
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from security import deployment, preview_data, private_evidence
from news.chart_data_manager import choose_pair
from news.weekly_facts import digest, fact_path, ROOT


class DeploymentBoundaryTests(unittest.TestCase):
    def test_cloud_requires_reviewed_synthetic_postgres_configuration(self):
        env = {
            "VERCEL": "1", "VERCEL_ENV": "preview", "KPOP_PREVIEW_SYNTHETIC": "1",
            "KPOP_PUBLIC_ORIGIN": "https://demo.vercel.app", "KPOP_DB_BACKEND": "postgresql",
            "KPOP_POSTGRES_SCHEMA": "kpop_class_preview", "KPOP_POSTGRES_DSN": "opaque",
            "KPOP_POSTGRES_SSLROOTCERT_PEM": "-----BEGIN CERTIFICATE-----\
TEST PUBLIC CA\
-----END CERTIFICATE-----",
        }
        with patch.dict(os.environ, env, clear=False), \
             patch("psycopg.conninfo.conninfo_to_dict", return_value={"sslmode": "verify-full", "user": "kpop_class_app.preview"}):
            deployment.validate()

    def test_cloud_without_synthetic_mode_fails_closed(self):
        env = {"VERCEL": "1", "VERCEL_ENV": "preview", "KPOP_PREVIEW_SYNTHETIC": "0"}
        with patch.dict(os.environ, env, clear=False), self.assertRaises(RuntimeError):
            deployment.validate()

    def test_synthetic_fixture_inventory_is_manifest_bound(self):
        with patch.dict(os.environ, {"KPOP_PREVIEW_SYNTHETIC": "1"}, clear=False):
            self.assertEqual(preview_data.data_root(), preview_data.FIXTURE_ROOT)
            inventory, notes = preview_data.inventory(preview_data.FIXTURE_ROOT)
            self.assertEqual(len(inventory), 2)
            self.assertTrue(all(set(files) == {"spotify", "youtube"} for files in inventory.values()))
            self.assertIn("SYNTHETIC", notes[0])

    def test_registered_article_evidence_matches_source_bytes(self):
        week = "2026-10-08"
        pair, _, _ = choose_pair(root=ROOT, week_end=week)
        hashes = {key: hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() for key, rel in pair.files.items()}
        facts = json.loads(fact_path(ROOT, week).read_text(encoding="utf-8"))
        evidence = {"facts": facts, "source_sha256": hashes}
        article = {"week_end": week, "fact_ref": fact_path(ROOT, week).relative_to(ROOT).as_posix(),
                   "evidence_hash": digest(evidence)}
        objects = private_evidence.expected_objects(None, article, evidence)
        self.assertEqual(set(objects), {*pair.files.values(), "evidence.json"})
        for rel, content in objects.items():
            self.assertTrue(content)
            if rel != "evidence.json": self.assertEqual(hashlib.sha256(content).hexdigest(), hashes[next(k for k,v in pair.files.items() if v == rel)])


if __name__ == "__main__":
    unittest.main()