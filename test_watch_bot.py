#!/usr/bin/env python3
"""
Unit tests for the pure helper functions in watch_bot.py (no network calls).
Run with: python3 -m unittest test_watch_bot.py -v
"""

import unittest

import watch_bot


class TestStripHtml(unittest.TestCase):
    def test_removes_tags(self):
        self.assertEqual(
            watch_bot.strip_html("<p>Hello <b>world</b></p>"), "Hello world"
        )

    def test_unescapes_entities(self):
        self.assertEqual(watch_bot.strip_html("Tom &amp; Jerry &gt; cat"), "Tom & Jerry > cat")

    def test_handles_none(self):
        self.assertEqual(watch_bot.strip_html(None), "")

    def test_handles_empty_string(self):
        self.assertEqual(watch_bot.strip_html(""), "")

    def test_strips_surrounding_whitespace(self):
        self.assertEqual(watch_bot.strip_html("  <p>padded</p>  "), "padded")


class TestMergeLinks(unittest.TestCase):
    def test_appends_new_links_in_order(self):
        result = watch_bot.merge_links(["a", "b"], ["c", "d"], max_size=10)
        self.assertEqual(result, ["a", "b", "c", "d"])

    def test_does_not_duplicate_already_seen_links(self):
        result = watch_bot.merge_links(["a", "b"], ["b", "c"], max_size=10)
        self.assertEqual(result, ["a", "b", "c"])

    def test_caps_to_max_size_evicting_oldest_first(self):
        result = watch_bot.merge_links(["a", "b", "c"], ["d", "e"], max_size=3)
        self.assertEqual(result, ["c", "d", "e"])

    def test_large_feed_does_not_lose_items_within_cap(self):
        # Regression test: a feed with more entries than any previous run
        # must not have its whole history discarded, only the oldest excess.
        old = [f"link{i}" for i in range(198)]
        new = ["link198", "link199", "link200"]
        result = watch_bot.merge_links(old, new, max_size=200)
        self.assertEqual(len(result), 200)
        self.assertEqual(result[-1], "link200")
        self.assertEqual(result[0], "link1")  # link0 evicted, oldest first

    def test_empty_state_first_run(self):
        result = watch_bot.merge_links([], ["a", "b", "c"], max_size=200)
        self.assertEqual(result, ["a", "b", "c"])


class TestChunkList(unittest.TestCase):
    def test_splits_into_even_chunks(self):
        self.assertEqual(
            watch_bot.chunk_list([1, 2, 3, 4], 2), [[1, 2], [3, 4]]
        )

    def test_splits_with_remainder(self):
        self.assertEqual(
            watch_bot.chunk_list([1, 2, 3, 4, 5], 2), [[1, 2], [3, 4], [5]]
        )

    def test_chunk_size_larger_than_list(self):
        self.assertEqual(watch_bot.chunk_list([1, 2], 5), [[1, 2]])

    def test_empty_list(self):
        self.assertEqual(watch_bot.chunk_list([], 5), [])


class TestBuildEmbed(unittest.TestCase):
    def test_basic_fields(self):
        embed = watch_bot.build_embed(
            "Test Source", "A Title", "https://example.com/a", "A summary", []
        )
        self.assertEqual(embed["title"], "A Title")
        self.assertEqual(embed["url"], "https://example.com/a")
        self.assertEqual(embed["description"], "A summary")
        self.assertEqual(embed["footer"]["text"], "Source: Test Source")
        self.assertNotIn("fields", embed)

    def test_tags_add_a_field(self):
        embed = watch_bot.build_embed(
            "Test Source", "Title", "https://x", "Summary", ["Security", "AI"]
        )
        self.assertEqual(embed["fields"], [{"name": "Tags", "value": "Security, AI"}])

    def test_title_is_truncated(self):
        embed = watch_bot.build_embed("S", "T" * 300, "https://x", "", [])
        self.assertEqual(len(embed["title"]), 256)

    def test_description_is_truncated_and_html_stripped(self):
        embed = watch_bot.build_embed(
            "S", "T", "https://x", "<p>" + "a" * 400 + "</p>", []
        )
        self.assertEqual(len(embed["description"]), 300)
        self.assertNotIn("<p>", embed["description"])


if __name__ == "__main__":
    unittest.main()
