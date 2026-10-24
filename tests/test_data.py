import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from native_pilot.data import (
    SourceBlocked, audit_sources, changed_token_count, normalized_original_hash,
    prepare_sources, rank_candidates, select_tasks, verify_sources,
)


class DataTests(unittest.TestCase):
    def make_lock(self, directory, contents=b"public source bytes", path="file.txt"):
        lock = Path(directory) / "lock.json"
        lock.write_text(json.dumps({"artifacts": [{"path": path,
            "url": "https://example.org/pinned/file.txt", "bytes": len(contents),
            "sha256": hashlib.sha256(contents).hexdigest()}]}))
        return lock

    def test_corrupt_source_rejected_before_parse_or_download(self):
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary) / "cache"
            cache.mkdir()
            lock = self.make_lock(temporary)
            (cache / "file.txt").write_text("corrupted source")
            with patch("native_pilot.data.urllib.request.urlopen") as network:
                with self.assertRaisesRegex(SourceBlocked, "Checksum mismatch"):
                    prepare_sources(cache, lock)
                network.assert_not_called()
            with patch("native_pilot.data._read_rows") as reader:
                report = audit_sources(cache, lock)
                self.assertEqual(report["status"], "blocked")
                reader.assert_not_called()

    def test_verified_cache_is_reused_without_network(self):
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary) / "cache"
            cache.mkdir()
            lock = self.make_lock(temporary)
            (cache / "file.txt").write_bytes(b"public source bytes")
            with patch("native_pilot.data.urllib.request.urlopen") as network:
                self.assertTrue(prepare_sources(cache, lock)["verified"])
                network.assert_not_called()

    def test_cache_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            lock = self.make_lock(temporary, path="../outside.txt")
            with self.assertRaisesRegex(SourceBlocked, "escapes cache"):
                verify_sources(Path(temporary) / "cache", lock)

    def test_duplicates_ignore_whitespace_and_ids(self):
        left = {"id": 1, "original_problem": "A published  problem\ntext"}
        right = {"id": 900, "original_problem": "A published problem text"}
        self.assertEqual(normalized_original_hash(left), normalized_original_hash(right))

    def test_prospective_ranking_uses_difficulty_before_edit_size(self):
        items = [
            dict(task_id="medium", domain="coding", published_difficulty="medium", changed_tokens=1),
            dict(task_id="hard-big", domain="coding", published_difficulty="hard", changed_tokens=20),
            dict(task_id="hard-small", domain="coding", published_difficulty="hard", changed_tokens=2),
        ]
        self.assertEqual([x["task_id"] for x in rank_candidates(items)], ["hard-small", "hard-big", "medium"])
        self.assertEqual(rank_candidates(items), rank_candidates(list(reversed(items))))
        self.assertEqual(changed_token_count({"original_problem": "p = 5", "revised_problem": "p = 7"}), 1)

    def test_release_block_cannot_select_review_rows(self):
        audit = {"status": "blocked", "blockers": ["Missing initial graders"],
                 "candidates": [{"qualified": True}], "qualified_tasks": []}
        with self.assertRaisesRegex(SourceBlocked, "Missing initial graders"):
            select_tasks(audit)

    def pool(self):
        # Unit-test records only; never written into pilot source manifests.
        return [dict(task_id=f"unit-{domain}-{i}", domain=domain, published_difficulty="hard" if domain == "coding" else None,
                     changed_tokens=i, qualified=True, qualification_evidence_sha256="unit-test-only",
                     original_identity=f"unit-{domain}-{i}")
                for domain in ("math", "coding") for i in range(13)]

    def test_balanced_controls_distinct_originals_and_smoke(self):
        result = select_tasks({"status": "qualified", "blockers": [], "qualified_tasks": self.pool()})
        tasks = result["tasks"]
        self.assertEqual(len(tasks), 24)
        for domain in ("math", "coding"):
            self.assertEqual(sum(t["domain"] == domain for t in tasks), 12)
            self.assertEqual(sum(t["domain"] == domain and t["unchanged_control"] for t in tasks), 4)
        self.assertNotIn(result["smoke_task"]["original_identity"], {t["original_identity"] for t in tasks})
        self.assertEqual(result, select_tasks({"status": "qualified", "blockers": [], "qualified_tasks": list(reversed(self.pool()))}))

    def test_missing_smoke_and_duplicates_fail_closed(self):
        pool = self.pool()
        pool[1]["original_identity"] = pool[0]["original_identity"]
        with self.assertRaisesRegex(SourceBlocked, "Duplicate original"):
            select_tasks({"status": "qualified", "blockers": [], "qualified_tasks": pool})
        pool = [r for r in self.pool() if r["changed_tokens"] < 12]
        with self.assertRaisesRegex(SourceBlocked, "separate qualified smoke"):
            select_tasks({"status": "qualified", "blockers": [], "qualified_tasks": pool})


if __name__ == "__main__":
    unittest.main()
