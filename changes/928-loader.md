### For addon authors

- A Forever addon loaded on demand after world entry now gets `PLAYER_ENTERING_WORLD` replayed with `false, false` (neither a login nor a reload) instead of nil arguments, so a saved debug capture resumes or stops correctly.
