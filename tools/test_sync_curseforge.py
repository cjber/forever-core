import unittest

from sync_curseforge import _Stored, compare, expected_links, normalise


class SyncCurseforgeTest(unittest.TestCase):
    def test_linkout_wrapper_compares_as_its_destination(self):
        wrapped = "https://www.curseforge.com/linkout?remoteUrl=https%253a%252f%252fko-fi.com%252fcjber"
        self.assertEqual(normalise(wrapped), "https://ko-fi.com/cjber")

    def test_expected_links_include_image_and_link_targets(self):
        markdown = "[![Ko-fi](https://raw.githubusercontent.com/x/y/main/docs/kofi-button.png)](https://ko-fi.com/x/)\n"
        self.assertEqual(
            expected_links(markdown),
            {"https://raw.githubusercontent.com/x/y/main/docs/kofi-button.png", "https://ko-fi.com/x"},
        )

    def test_stored_html_links_and_images_are_read_exactly(self):
        parser = _Stored()
        parser.feed(
            '<p><a href="https://www.curseforge.com/linkout?remoteUrl=https%253a%252f%252fko-fi.com%252fx">'
            '<img src="https://raw.githubusercontent.com/x/y/main/docs/kofi-button.png"></a></p>'
        )
        self.assertEqual(
            parser.urls, {"https://ko-fi.com/x", "https://raw.githubusercontent.com/x/y/main/docs/kofi-button.png"}
        )

    MARKDOWN = (
        "<!-- forever-family -->\n## Tracks it\n\nIt's **free**: [sponsor me](https://github.com/sponsors/x).\n\n"
        "![Shot](https://raw.githubusercontent.com/x/y/main/docs/a.png)\n"
    )
    HTML = (
        "<h2>Tracks it</h2><p>It&rsquo;s <strong>free</strong>: "
        '<a href="https://github.com/sponsors/x">sponsor me</a>.</p>'
        '<p><img src="https://raw.githubusercontent.com/x/y/main/docs/a.png" alt="Shot"></p>'
    )

    def stored(self, html):
        parser = _Stored()
        parser.feed(html)
        return parser

    def test_description_stored_as_written_passes(self):
        self.assertEqual(
            compare(self.MARKDOWN, self.stored(self.HTML)), (True, "stored description matches word for word")
        )

    def test_description_stored_twice_fails_although_its_links_match(self):
        ok, detail = compare(self.MARKDOWN, self.stored("<p>Old text.</p>" + self.HTML))
        self.assertFalse(ok)
        self.assertIn("stored 'old text'", detail)


if __name__ == "__main__":
    unittest.main()
