import re
import unittest
from pathlib import Path


class DocumentationTests(unittest.TestCase):
    """Protege a documentação pública contra instruções específicas de uma máquina."""

    def test_public_markdown_does_not_contain_local_machine_paths(self):
        root = Path(__file__).resolve().parents[1]
        forbidden = re.compile(
            r"C:\\Users\\|/Users/|/home/|Administrator|Downloads\\Teste",
            re.IGNORECASE,
        )
        offenders = []
        for path in root.rglob("*.md"):
            if any(part.startswith(".") for part in path.relative_to(root).parts):
                continue
            text = path.read_text(encoding="utf-8")
            if forbidden.search(text):
                offenders.append(str(path.relative_to(root)))
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
