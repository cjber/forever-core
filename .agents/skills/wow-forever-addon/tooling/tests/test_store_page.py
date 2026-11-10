import tempfile
import unittest
from pathlib import Path

from forever_tools import family, store_page

REPO = "demo-forever"
RAW = f"https://raw.githubusercontent.com/cjber/{REPO}/main"


def page(shots=3, features=3, extra_heading=False):
    parts = ["Demo Forever shows things in the stock UI.", store_page.SPONSOR]
    for n in range(shots):
        parts += [f"![Shot {n}]({RAW}/docs/screenshots/s{n}.png)", f"Caption {n}."]
    parts += ["These images are generated previews of the Demo UI.", "## Features"]
    parts.append("\n".join(f"- **Thing {n}.** It does thing {n}." for n in range(features)))
    if extra_heading:
        parts += ["## Prices", "How prices work."]
    parts += [
        "## Usage",
        "Type `/demo`.",
        "For a bug report, paste `/demo report`.",
        "Translated into German (corrections welcome through the "
        f"[translation form](https://github.com/cjber/{REPO}/issues/new?template=translation.yml)).",
        family.BLOCK,
        store_page.source_line(REPO),
        store_page.AI_LINE,
        store_page.buttons(REPO),
    ]
    return "\n\n".join(parts) + "\n"


class StorePageTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / "docs/screenshots").mkdir(parents=True)
        for n in range(8):
            (self.root / f"docs/screenshots/s{n}.png").write_bytes(b"")
        for name in ("discord-button.png", "github-sponsors-button.png", "kofi-button.png"):
            (self.root / "docs" / name).write_bytes(b"")
        (self.root / "Demo.toc").write_text(
            f"## Interface: 16001\n## Title: |cff00ff00Demo Forever|r\n## X-Website: https://github.com/cjber/{REPO}\n",
            encoding="utf-8",
        )

    def check(self, text):
        (self.root / store_page.FILE).write_text(text, encoding="utf-8")
        return store_page.check(self.root)

    def test_template_page_passes(self):
        self.assertEqual(self.check(page()), [])
        self.assertEqual(self.check(page(shots=6, features=8, extra_heading=True)), [])

    def test_image_count_bounds(self):
        self.assertTrue(any("2 screenshots" in p for p in self.check(page(shots=2))))
        self.assertTrue(any("7 screenshots" in p for p in self.check(page(shots=7))))

    def test_missing_screenshot_file(self):
        text = page().replace("s0.png", "gone.png")
        self.assertTrue(any("gone.png is not in docs/screenshots/" in p for p in self.check(text)))

    def test_uncaptioned_image(self):
        text = page().replace("\n\nCaption 0.", "")
        self.assertTrue(any("no caption" in p for p in self.check(text)))

    def test_feature_bullet_form(self):
        text = page().replace("- **Thing 0.** It", "- **Thing 0**: it")
        self.assertTrue(any("bold name" in p for p in self.check(text)))

    def test_missing_usage_and_buttons(self):
        text = page().replace("## Usage", "## Help").replace(store_page.buttons(REPO), "")
        problems = self.check(text)
        self.assertTrue(any("`## Usage` missing" in p for p in problems))
        self.assertTrue(any("must end with" in p for p in problems))

    def test_pitch_opens_with_toc_title(self):
        text = page().replace("Demo Forever shows", "Shows")
        self.assertTrue(any("TOC title" in p for p in self.check(text)))

    def test_word_cap(self):
        text = page().replace("How prices work.", "") + ("word " * store_page.MAX_WORDS)
        self.assertTrue(any("prose words" in p for p in self.check(text)))


if __name__ == "__main__":
    unittest.main()
