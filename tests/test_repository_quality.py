import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.repository_quality import check_repository


class RepositoryQualityTests(unittest.TestCase):
    def make_required_tree(self, root: Path) -> None:
        from tools.repository_quality import REQUIRED_PATHS

        for relative in REQUIRED_PATHS:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()

    def test_valid_local_markdown_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_required_tree(root)
            (root / "README.md").write_text("[Install](INSTALLATION.md)\n", encoding="utf-8")
            self.assertEqual(check_repository(root), [])

    def test_broken_local_markdown_link_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_required_tree(root)
            (root / "README.md").write_text("[Missing](docs/DOES_NOT_EXIST.md)\n", encoding="utf-8")
            errors = check_repository(root)
            self.assertTrue(any("broken local link" in error for error in errors))

    def test_missing_required_path_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_required_tree(root)
            (root / "PROTOCOL_SPEC.md").unlink()
            errors = check_repository(root)
            self.assertIn("missing required path: PROTOCOL_SPEC.md", errors)


if __name__ == "__main__":
    unittest.main()
