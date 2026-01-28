import unittest
from pathlib import Path
import tempfile
import shutil
import sys
import os

# Add tools dir to path to import the tool
# Assuming this test is in tools/context_packer/
sys.path.append(str(Path(__file__).parent))

# We will implement this class in the actual script
from docsearch import DocGraph, Node, IndexParser

class TestDocGraph(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.root = Path(self.test_dir)
        
        # Create a mock documentation structure
        # root/
        #   index.md
        #   design/
        #     design.md
        #   adr/
        #     adr-001.md
        #     adr-002.md
        
        (self.root / "design").mkdir()
        (self.root / "adr").mkdir()
        
        self.index = self.root / "index.md"
        self.design = self.root / "design" / "design.md"
        self.adr1 = self.root / "adr" / "adr-001.md"
        self.adr2 = self.root / "adr" / "adr-002.md"
        
        # Write content with links
        self.index.write_text("""
# Index
## Section 1
- [Design Guide](design/design.md)
        """)
        
        self.design.write_text("""
# Design
References [ADR 1](../adr/adr-001.md) for architecture.
Also see [ADR 2](../adr/adr-002.md).
        """)
        
        # Cycle: ADR 1 links back to Design
        self.adr1.write_text("""
# ADR 1
Implements [Design](../design/design.md).
        """)
        
        self.adr2.write_text("# ADR 2\nNo links.")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_resolve_path(self):
        """Test resolving relative paths to absolute canonical paths."""
        graph = DocGraph(self.root)
        
        # From root
        resolved = graph.resolve_path(self.index, "design/design.md")
        self.assertEqual(resolved, self.design.resolve())
        
        # From subdir (../)
        resolved = graph.resolve_path(self.design, "../adr/adr-001.md")
        self.assertEqual(resolved, self.adr1.resolve())

    def test_parse_links(self):
        """Test extracting markdown links."""
        graph = DocGraph(self.root)
        links = graph.extract_links(self.design)
        
        self.assertEqual(len(links), 2)
        # We expect resolved absolute paths
        self.assertIn(self.adr1.resolve(), links)
        self.assertIn(self.adr2.resolve(), links)

    def test_build_graph_cycle(self):
        """Test that the graph builds and handles cycles without infinite recursion."""
        graph = DocGraph(self.root)
        # Manually trigger build logic (simulated for unit test)
        
        neighbors_index = graph.extract_links(self.index)
        self.assertIn(self.design.resolve(), neighbors_index)
        
        neighbors_design = graph.extract_links(self.design)
        self.assertIn(self.adr1.resolve(), neighbors_design)
        
        neighbors_adr1 = graph.extract_links(self.adr1)
        self.assertIn(self.design.resolve(), neighbors_adr1) # The cycle

    def test_traverse_depth_0(self):
        """Test getting just the seed file."""
        graph = DocGraph(self.root)
        results = graph.traverse([self.index], depth=0)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], self.index.resolve())

    def test_traverse_depth_1(self):
        """Test getting immediate children."""
        graph = DocGraph(self.root)
        results = graph.traverse([self.index], depth=1)
        # Index -> Design
        self.assertEqual(len(results), 2)
        self.assertIn(self.index.resolve(), results)
        self.assertIn(self.design.resolve(), results)

    def test_traverse_depth_2(self):
        """Test getting grandchildren (Index -> Design -> ADRs)."""
        graph = DocGraph(self.root)
        results = graph.traverse([self.index], depth=2)
        # Index -> Design -> ADR1, ADR2
        self.assertEqual(len(results), 4)
        self.assertIn(self.adr1.resolve(), results)
        self.assertIn(self.adr2.resolve(), results)

    def test_traverse_deduplication(self):
        """Test that visited nodes are not duplicated (Cycle handling)."""
        # Start at Design (links to ADR1). ADR1 links to Design.
        # Infinite depth loop check.
        graph = DocGraph(self.root)
        results = graph.traverse([self.design], depth=5)
        
        # Should contain Design, ADR1, ADR2.
        # Should NOT contain duplicate Design or ADR1.
        self.assertEqual(len(results), 3) 
        self.assertEqual(len(set(results)), 3) # Assert unique

    def test_index_parser(self):
        """Test parsing the Index file for topics."""
        parser = IndexParser(self.index)
        topics = parser.parse()
        
        self.assertIn("Section 1", topics)
        self.assertEqual(len(topics["Section 1"]), 1)
        self.assertEqual(topics["Section 1"][0], self.design.resolve())

    def test_keyword_parsing(self):
        """Test parsing keywords from Index."""
        # Add keywords to index
        self.index.write_text("""
# Index
## Intelligence
*Keywords: AI, ML, Learning*
- [Design Guide](design/design.md)
""")
        parser = IndexParser(self.index)
        topics = parser.parse()
        
        self.assertIn("Intelligence", topics)
        # Check keywords
        keywords = parser.topic_keywords.get("Intelligence", [])
        self.assertIn("AI", keywords)
        self.assertIn("Learning", keywords)
        
        # Test matching
        matches = parser.match_topic("ML", topics)
        self.assertIn("Intelligence", matches)

    def test_pack_format(self):
        """Test that pack() returns correct XML format."""
        graph = DocGraph(self.root)
        # Force load content
        graph.get_node(self.adr2).content = "Content"
        
        packed = graph.pack([self.adr2])
        
        expected = f"""<document path="adr{os.sep}adr-002.md">
Content
</document>"""
        
        self.assertEqual(packed.strip(), expected.strip())

if __name__ == '__main__':
    unittest.main()
