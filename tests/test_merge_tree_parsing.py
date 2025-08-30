"""Test merge-tree output parsing for conflict analysis."""

import unittest
from pathlib import Path

from rich.console import Console

from cherrytree.git_interface import GitInterface


class TestMergeTreeParsing(unittest.TestCase):
    """Test parsing of git merge-tree output for conflict detection."""

    def setUp(self):
        """Set up test environment."""
        # Use current directory as repo_path for testing
        self.git_interface = GitInterface(repo_path=Path.cwd(), console=Console())

    def test_no_conflicts_empty_output(self):
        """Test parsing when there are no conflicts (empty output)."""
        empty_output = ""
        result = self.git_interface._parse_merge_tree_output(empty_output)

        self.assertEqual(result["conflicts"], [])
        self.assertFalse(result["has_conflicts"])

    def test_single_file_conflict(self):
        """Test parsing a single file with conflicts."""
        merge_tree_output = """
--- a/src/components/Button.tsx
+++ b/src/components/Button.tsx
@@ -1,10 +1,15 @@
 import React from 'react';

+<<<<<<< HEAD
+interface ButtonProps {
+  onClick: () => void;
+  children: React.ReactNode;
+}
+=======
 interface Props {
   click: () => void;
   label: string;
 }
+>>>>>>> branch

 export const Button = ({ onClick, children }: ButtonProps) => {
   return <button onClick={onClick}>{children}</button>;
        """

        result = self.git_interface._parse_merge_tree_output(merge_tree_output)

        # Debug: print the actual result
        print(f"\nDEBUG - Parse result: {result}")
        if result["conflicts"]:
            for i, conflict in enumerate(result["conflicts"]):
                print(f"Conflict {i}: {conflict}")

        self.assertTrue(result["has_conflicts"])
        self.assertEqual(len(result["conflicts"]), 1)

        conflict = result["conflicts"][0]
        self.assertEqual(conflict["file"], "src/components/Button.tsx")
        self.assertEqual(conflict["type"], "merge_conflict")
        self.assertGreater(conflict["conflicted_lines"], 0)
        self.assertGreater(conflict["region_count"], 0)

    def test_multiple_files_with_conflicts(self):
        """Test parsing multiple files with conflicts."""
        merge_tree_output = """
--- a/src/utils/api.ts
+++ b/src/utils/api.ts
@@ -5,8 +5,13 @@
 const API_BASE = 'https://api.example.com';

+<<<<<<< HEAD
+export const fetchData = async (endpoint: string) => {
+  return fetch(`${API_BASE}/${endpoint}`);
+};
+=======
 export const getData = (url: string) => {
   return fetch(API_BASE + url);
 };
+>>>>>>> branch

--- a/src/components/Form.tsx
+++ b/src/components/Form.tsx
@@ -12,7 +12,11 @@
   const handleSubmit = () => {
     // Handle form submission
+<<<<<<< HEAD
+    validateForm(data);
+=======
     validate(formData);
+>>>>>>> branch
   };
        """

        result = self.git_interface._parse_merge_tree_output(merge_tree_output)

        self.assertTrue(result["has_conflicts"])
        self.assertEqual(len(result["conflicts"]), 2)

        # Check first file
        api_conflict = next((c for c in result["conflicts"] if "api.ts" in c["file"]), None)
        self.assertIsNotNone(api_conflict)
        self.assertEqual(api_conflict["type"], "merge_conflict")
        self.assertGreater(api_conflict["conflicted_lines"], 0)

        # Check second file
        form_conflict = next((c for c in result["conflicts"] if "Form.tsx" in c["file"]), None)
        self.assertIsNotNone(form_conflict)
        self.assertEqual(form_conflict["type"], "merge_conflict")
        self.assertGreater(form_conflict["conflicted_lines"], 0)

    def test_complex_conflict_with_multiple_regions(self):
        """Test parsing a file with multiple conflict regions."""
        merge_tree_output = """
--- a/src/database/models.py
+++ b/src/database/models.py
@@ -1,5 +1,9 @@
 from sqlalchemy import Column, Integer, String
+<<<<<<< HEAD
+from sqlalchemy.ext.declarative import declarative_base
+=======
 from sqlalchemy.orm import declarative_base
+>>>>>>> branch

 Base = declarative_base()

@@ -15,8 +19,12 @@
     id = Column(Integer, primary_key=True)
     name = Column(String(50), nullable=False)
+<<<<<<< HEAD
+    email = Column(String(100), unique=True, nullable=False)
+=======
     email_address = Column(String(255), unique=True)
+>>>>>>> branch

     def __repr__(self):
         return f'<User({self.name})>'
        """

        result = self.git_interface._parse_merge_tree_output(merge_tree_output)

        self.assertTrue(result["has_conflicts"])
        self.assertEqual(len(result["conflicts"]), 1)

        conflict = result["conflicts"][0]
        self.assertEqual(conflict["file"], "src/database/models.py")
        self.assertEqual(conflict["type"], "merge_conflict")
        self.assertGreater(conflict["conflicted_lines"], 5)  # Should count multiple conflict lines
        self.assertGreater(conflict["region_count"], 1)  # Should detect multiple regions

    def test_conflict_parsing_edge_cases(self):
        """Test edge cases in conflict parsing."""
        # Test with malformed output
        malformed_output = "some random text without proper git format"
        result = self.git_interface._parse_merge_tree_output(malformed_output)
        self.assertEqual(result["conflicts"], [])
        self.assertFalse(result["has_conflicts"])

        # Test with only conflict markers but no file headers
        markers_only = """
<<<<<<< HEAD
some content
=======
other content
>>>>>>> branch
        """
        result = self.git_interface._parse_merge_tree_output(markers_only)
        # Should handle gracefully even without proper file headers
        self.assertIsInstance(result["conflicts"], list)
        self.assertIsInstance(result["has_conflicts"], bool)


if __name__ == "__main__":
    unittest.main()
