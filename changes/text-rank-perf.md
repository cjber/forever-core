### Fixed

- **Search ranking no longer builds a blanked copy of every title it ranks.** Ranking a name in a search list (Adventure Guide Forever) rebuilt the title with punctuation blanked, and a word list for the query, on every call. It now scans the title's own word starts directly, at the same ranking.
