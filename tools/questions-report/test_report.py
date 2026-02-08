import os
import json
import shutil
import tempfile
import unittest
from datetime import date, timedelta
from report import scan_questions, parse_date, is_migrated

class TestReport(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        shutil.rmtree(self.test_dir)
        
    def create_file(self, name, content):
        with open(os.path.join(self.test_dir, name), "w", encoding="utf-8") as f:
            f.write(content)
            
    def test_counts_open_questions(self):
        content = """
# Test Category

## Open Questions
### Q: Question 1
**Status**: Open
**Created**: 2026-01-01

### Q: Question 2
**Status**: In Progress
**Created**: 2026-01-01

## Resolved
### R: Resolved 1
**Decision**: Done
"""
        self.create_file("test.md", content)
        data = scan_questions(self.test_dir)
        self.assertEqual(data["files"][0]["open"], 2)
        
    def test_counts_resolved_questions(self):
        content = """
# Test Category

## Open Questions
### Q: Question 1
**Status**: Open

## Resolved
### R: Resolved 1
**Decision**: Done
**ADR**: ADR-0001

### R: Resolved 2
**Decision**: Done
"""
        self.create_file("test.md", content)
        data = scan_questions(self.test_dir)
        # Resolved 1 (migrated) and Resolved 2 (not migrated) = 2
        self.assertEqual(data["files"][0]["resolved"], 2)
        
    def test_finds_migration_candidates(self):
        content = """
# Test Category

## Resolved
### R: Resolved 1
**Decision**: Done
**ADR**: ADR-0001

### R: Resolved 2
**Decision**: Done
No migration info here.
"""
        self.create_file("test.md", content)
        data = scan_questions(self.test_dir)
        self.assertEqual(len(data["migration_candidates"]), 1)
        self.assertEqual(data["migration_candidates"][0]["title"], "R: Resolved 2")
        
    def test_finds_stale_questions(self):
        old_date = (date.today() - timedelta(days=40)).isoformat()
        recent_date = (date.today() - timedelta(days=10)).isoformat()
        
        content = f"""
# Test Category

## Open Questions
### Q: Old Question
**Status**: Open
**Created**: {old_date}

### Q: New Question
**Status**: Open
**Created**: {recent_date}
"""
        self.create_file("test.md", content)
        data = scan_questions(self.test_dir)
        self.assertEqual(len(data["stale_questions"]), 1)
        self.assertEqual(data["stale_questions"][0]["title"], "Q: Old Question")
        
    def test_json_output(self):
        # This test verifies the scan_questions output structure which is used for JSON
        content = """
# Test
## Open Questions
### Q: Q1
**Status**: Open
"""
        self.create_file("test.md", content)
        data = scan_questions(self.test_dir)
        # Ensure it can be serialized
        json_str = json.dumps(data)
        parsed = json.loads(json_str)
        self.assertIn("files", parsed)
        self.assertIn("migration_candidates", parsed)
        self.assertIn("stale_questions", parsed)
        
    def test_skips_readme(self):
        self.create_file("README.md", "# Index")
        self.create_file("test.md", "# Test\n## Open Questions\n### Q: Q1\n**Status**: Open")
        data = scan_questions(self.test_dir)
        self.assertEqual(len(data["files"]), 1)
        self.assertEqual(data["files"][0]["name"], "test.md")

    def test_is_migrated(self):
        self.assertTrue(is_migrated("Refer to ADR-0001"))
        self.assertTrue(is_migrated("see {doc}"))
        self.assertTrue(is_migrated("Check [Decision](decision.md)"))
        self.assertFalse(is_migrated("No link here"))

    def test_parse_date(self):
        self.assertEqual(parse_date("2026-01-01"), date(2026, 1, 1))
        self.assertEqual(parse_date("2026-01-XX"), None)
        self.assertEqual(parse_date("Invalid"), None)

if __name__ == "__main__":
    unittest.main()
