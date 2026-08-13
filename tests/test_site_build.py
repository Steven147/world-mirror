import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STORY_ID = "wm-20260813-fe7aa82e"


class SiteBuildTests(unittest.TestCase):
    def test_build_publishes_the_index_consumed_by_the_site(self):
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "build_site.py")],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        archive_index = json.loads(
            (ROOT / "stories" / "index.json").read_text(encoding="utf-8")
        )
        site_index = json.loads(
            (ROOT / "site" / "stories.json").read_text(encoding="utf-8")
        )

        self.assertEqual(archive_index, site_index)
        self.assertIn(STORY_ID, {story["story_id"] for story in site_index["stories"]})

if __name__ == "__main__":
    unittest.main()
