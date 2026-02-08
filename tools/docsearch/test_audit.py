import unittest
import os
import shutil
import tempfile
import sys
from pathlib import Path

# Add current dir to path to import audit.py
sys.path.append(str(Path(__file__).parent))

from audit import DocAudit

class TestDocAudit(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.root = Path(self.test_dir)
        self.docs_dir = self.root / "docs"
        self.docs_dir.mkdir()
        self.index_path = self.docs_dir / "INDEX.md"
        
        # Create some folders
        (self.docs_dir / "design").mkdir()
        (self.docs_dir / "adr").mkdir()
        (self.docs_dir / "archive").mkdir()
        
        # Create INDEX.md
        self.index_path.write_text("""# Index
## Section 1
- [Doc 1](adr/doc1.md)
- [External](http://google.com)
""", encoding="utf-8")
        
        # Create Doc 1
        (self.docs_dir / "adr" / "doc1.md").write_text("Doc 1 content")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_audit_finds_orphan_docs(self):
        """--audit reports orphan docs (files not in INDEX.md)"""
        orphan = self.docs_dir / "adr" / "orphan.md"
        orphan.write_text("Orphan content")
        
        auditor = DocAudit(self.root)
        all_files = auditor.get_all_md_files()
        links = auditor.parse_index_links()
        
        self.assertIn(orphan.resolve(), all_files)
        self.assertNotIn(orphan.resolve(), links)
        
        # Verify run_audit identifies it (we'll mock stdout if needed, but for now just check logic)
        orphan_docs = {p for p in all_files if p not in links and p != self.index_path}
        self.assertIn(orphan.resolve(), orphan_docs)

    def test_audit_finds_dead_links(self):
        """--audit reports dead links (INDEX.md refs to nonexistent files)"""
        # Add dead link to INDEX.md
        self.index_path.write_text(self.index_path.read_text() + "\n- [Dead](nonexistent.md)", encoding="utf-8")
        
        auditor = DocAudit(self.root)
        links = auditor.parse_index_links()
        dead_links = {p for p in links if not p.exists()}
        
        self.assertIn((self.docs_dir / "nonexistent.md").resolve(), dead_links)

    def test_audit_finds_coverage_gaps(self):
        """--audit reports coverage gaps (design docs without INDEX.md entry)"""
        design_doc = self.docs_dir / "design" / "gap.md"
        design_doc.write_text("Gap content")
        
        auditor = DocAudit(self.root)
        all_files = auditor.get_all_md_files()
        links = auditor.parse_index_links()
        
        orphan_docs = {p for p in all_files if p not in links and p != self.index_path}
        design_dir = auditor.docs_dir / "design"
        design_archive = design_dir / "archive"
        coverage_gaps = {
            p for p in orphan_docs 
            if p.is_relative_to(design_dir) and not p.is_relative_to(design_archive)
        }
        
        self.assertIn(design_doc.resolve(), coverage_gaps)

    def test_audit_excludes_archive_prompts(self):
        """Excluded directories are not flagged as orphans"""
        archive_doc = self.docs_dir / "archive" / "old.md"
        archive_doc.write_text("Old content")
        
        # Also test design/archive
        (self.docs_dir / "design" / "archive").mkdir()
        design_archive_doc = self.docs_dir / "design" / "archive" / "superseded.md"
        design_archive_doc.write_text("Superseded")
        
        auditor = DocAudit(self.root)
        all_files = auditor.get_all_md_files()
        
        self.assertNotIn(archive_doc.resolve(), all_files)
        self.assertNotIn(design_archive_doc.resolve(), all_files)

    def test_audit_exit_codes(self):
        """Exit code is 0 when clean, 1 when issues found"""
        auditor = DocAudit(self.root)
        
        # Clean state
        self.assertEqual(auditor.run_audit(), 0)
        
        # Add an orphan
        (self.docs_dir / "orphan.md").write_text("Orphan")
        self.assertEqual(auditor.run_audit(), 1)

    def test_get_sections(self):
        """Test parsing sections from INDEX.md"""
        auditor = DocAudit(self.root)
        sections = auditor.get_sections()
        self.assertEqual(sections, ["Section 1"])

    def test_fix_adds_to_section(self):
        """Test adding orphan to a section"""
        auditor = DocAudit(self.root)
        rel_path = Path("adr/new_doc.md")
        auditor._add_to_section(rel_path, "Section 1")
        
        content = self.index_path.read_text()
        self.assertIn("[new_doc.md](adr/new_doc.md)", content)
        # It should be added after Section 1
        self.assertTrue(content.find("## Section 1") < content.find("adr/new_doc.md"))

    # --- Anchor link validation tests ---

    def test_heading_to_anchor_basic(self):
        """heading_to_anchor converts headings to GitHub-style anchors."""
        self.assertEqual(DocAudit.heading_to_anchor("My Section"), "my-section")
        self.assertEqual(
            DocAudit.heading_to_anchor("ADR-0001: Architecture"),
            "adr-0001-architecture",
        )
        self.assertEqual(DocAudit.heading_to_anchor("Step 1. Setup"), "step-1-setup")

    def test_heading_to_anchor_inline_markdown(self):
        """heading_to_anchor strips bold, italic, code, and links."""
        self.assertEqual(
            DocAudit.heading_to_anchor("Section with **bold**"),
            "section-with-bold",
        )
        self.assertEqual(
            DocAudit.heading_to_anchor("Has `code` in it"),
            "has-code-in-it",
        )
        self.assertEqual(
            DocAudit.heading_to_anchor("See [link](http://x.com) here"),
            "see-link-here",
        )

    def test_heading_to_anchor_special_chars(self):
        """heading_to_anchor strips special chars; each space becomes one hyphen."""
        # & removed leaves two spaces → two hyphens (GitHub behavior)
        self.assertEqual(
            DocAudit.heading_to_anchor("Intelligence & Learning"),
            "intelligence--learning",
        )
        self.assertEqual(
            DocAudit.heading_to_anchor("Question: What?"),
            "question-what",
        )

    def test_extract_anchors(self):
        """extract_anchors finds all heading anchors in a file."""
        doc = self.docs_dir / "anchored.md"
        doc.write_text("# Top\n## Sub Section\n### Deep\n", encoding="utf-8")

        auditor = DocAudit(self.root)
        anchors = auditor.extract_anchors(doc)

        self.assertIn("top", anchors)
        self.assertIn("sub-section", anchors)
        self.assertIn("deep", anchors)

    def test_extract_anchors_dedup(self):
        """Duplicate headings get -1, -2 suffixes (GitHub style)."""
        doc = self.docs_dir / "dupes.md"
        doc.write_text("## API\n## API\n## API\n", encoding="utf-8")

        auditor = DocAudit(self.root)
        anchors = auditor.extract_anchors(doc)

        self.assertIn("api", anchors)
        self.assertIn("api-1", anchors)
        self.assertIn("api-2", anchors)

    def test_anchor_check_valid(self):
        """Valid anchor links are not reported as broken."""
        target = self.docs_dir / "adr" / "doc1.md"
        target.write_text("# Doc 1\n## My Section\nContent here.", encoding="utf-8")

        self.index_path.write_text(
            "# Index\n## Section 1\n- [Doc 1 Section](adr/doc1.md#my-section)\n",
            encoding="utf-8",
        )

        auditor = DocAudit(self.root)
        broken = auditor.check_broken_anchors()
        self.assertEqual(broken, [])

    def test_anchor_check_broken(self):
        """Broken anchor links are detected."""
        target = self.docs_dir / "adr" / "doc1.md"
        target.write_text("# Doc 1\n## Real Section\nContent.", encoding="utf-8")

        self.index_path.write_text(
            "# Index\n## Section 1\n"
            "- [Doc 1](adr/doc1.md#nonexistent-section)\n",
            encoding="utf-8",
        )

        auditor = DocAudit(self.root)
        broken = auditor.check_broken_anchors()
        self.assertEqual(len(broken), 1)
        self.assertEqual(broken[0][2], "nonexistent-section")

    def test_anchor_check_same_file_valid(self):
        """Pure anchor links (#section) are validated within the same file."""
        doc = self.docs_dir / "selfref.md"
        doc.write_text(
            "# Top\nSee [below](#bottom)\n## Bottom\nDone.", encoding="utf-8"
        )

        auditor = DocAudit(self.root)
        broken = auditor.check_broken_anchors()
        selfref_broken = [b for b in broken if "selfref" in str(b[0])]
        self.assertEqual(selfref_broken, [])

    def test_anchor_check_same_file_broken(self):
        """Broken pure anchor links within the same file are detected."""
        doc = self.docs_dir / "selfref.md"
        doc.write_text(
            "# Top\nSee [missing](#does-not-exist)\n", encoding="utf-8"
        )

        auditor = DocAudit(self.root)
        broken = auditor.check_broken_anchors()
        selfref_broken = [b for b in broken if "selfref" in str(b[0])]
        self.assertEqual(len(selfref_broken), 1)
        self.assertEqual(selfref_broken[0][2], "does-not-exist")

    def test_anchor_check_skips_dead_links(self):
        """Links to missing files don't trigger anchor check (dead-link check covers them)."""
        self.index_path.write_text(
            "# Index\n## Section 1\n"
            "- [Gone](missing.md#some-anchor)\n",
            encoding="utf-8",
        )

        auditor = DocAudit(self.root)
        broken = auditor.check_broken_anchors()
        # missing.md doesn't exist — no anchor error (dead link is separate)
        self.assertEqual(broken, [])

    def test_anchor_check_skips_line_references(self):
        """GitHub line references (#L123, #L10-L20) are not heading anchors."""
        target = self.docs_dir / "adr" / "doc1.md"
        target.write_text("# Doc 1\nContent.", encoding="utf-8")

        self.index_path.write_text(
            "# Index\n## Section 1\n"
            "- [Line ref](adr/doc1.md#L42)\n"
            "- [Range ref](adr/doc1.md#L10-L20)\n",
            encoding="utf-8",
        )

        auditor = DocAudit(self.root)
        broken = auditor.check_broken_anchors()
        self.assertEqual(broken, [])

    def test_anchor_check_skips_non_markdown(self):
        """Anchor links to non-.md files (e.g. .py, .rs) are not checked."""
        py_file = self.docs_dir / "example.py"
        py_file.write_text("# not a heading\ndef foo(): pass\n")

        self.index_path.write_text(
            "# Index\n## Section 1\n"
            "- [Code](example.py#L5)\n"
            "- [Code 2](example.py#some-anchor)\n",
            encoding="utf-8",
        )

        auditor = DocAudit(self.root)
        broken = auditor.check_broken_anchors()
        self.assertEqual(broken, [])

    def test_anchor_check_ignores_external_links(self):
        """External links with anchors are not checked."""
        self.index_path.write_text(
            "# Index\n## Section 1\n"
            "- [GH](https://github.com/foo#readme)\n",
            encoding="utf-8",
        )

        auditor = DocAudit(self.root)
        broken = auditor.check_broken_anchors()
        self.assertEqual(broken, [])

    def test_broken_anchor_causes_audit_failure(self):
        """run_audit returns 1 when broken anchors are found."""
        target = self.docs_dir / "adr" / "doc1.md"
        target.write_text("# Doc 1\nContent only.", encoding="utf-8")

        self.index_path.write_text(
            "# Index\n## Section 1\n"
            "- [Doc 1](adr/doc1.md)\n"
            "- [Bad anchor](adr/doc1.md#no-such-section)\n",
            encoding="utf-8",
        )

        auditor = DocAudit(self.root)
        self.assertEqual(auditor.run_audit(), 1)


if __name__ == '__main__':
    unittest.main()
