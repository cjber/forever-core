import unittest

from sync_curseforge import _Urls, expected_links, normalise


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
        parser = _Urls()
        parser.feed(
            '<p><a href="https://www.curseforge.com/linkout?remoteUrl=https%253a%252f%252fko-fi.com%252fx">'
            '<img src="https://raw.githubusercontent.com/x/y/main/docs/kofi-button.png"></a></p>'
        )
        self.assertEqual(
            parser.urls, {"https://ko-fi.com/x", "https://raw.githubusercontent.com/x/y/main/docs/kofi-button.png"}
        )


if __name__ == "__main__":
    unittest.main()
