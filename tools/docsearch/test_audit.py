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

if __name__ == '__main__':
    unittest.main()
