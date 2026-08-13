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

        story = next(story for story in site_index["stories"] if story["story_id"] == STORY_ID)
        detail_path = ROOT / "site" / story["detail_path"]
        details = json.loads(detail_path.read_text(encoding="utf-8"))
        detail = details["stories"][story["detail_key"]]

        self.assertEqual(detail["story_id"], STORY_ID)
        self.assertEqual(len(detail["dialogue"]), story["turn_count"])
        self.assertEqual(
            [turn["meta"]["turn"] for turn in detail["dialogue"]],
            list(range(1, story["turn_count"] + 1)),
        )

    def test_page_contains_the_constellation_and_dialogue_reader(self):
        page = (ROOT / "site" / "index.html").read_text(encoding="utf-8")

        self.assertIn('id="graph-canvas"', page)
        self.assertIn('id="story-reader"', page)
        self.assertIn('id="turn-content"', page)

if __name__ == "__main__":
    unittest.main()
