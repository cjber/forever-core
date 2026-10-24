# Final shared TrackerHost (source: shortest-path-forever main after #186, commit 60300a7)
Port these byte for byte from cjber/shortest-path-forever main into your repo, then verify with sha256sum:
- UI/TrackerHost.lua                  f8d56a4e3bbee7b24aeb7dfa37b79dd1d8dcb8e71f1eb6e10aab040a04debb7e
- tests/tracker_host_spec.lua         d9e5ac17af3576b59e9060d6f8a1abf66c5ddc38cbb5d092dcbfdb2c3b679ee7  (byte-identical if your harness allows; otherwise adapt only the loader lines and say so)
- tools/fetch_tracker_ui.py           719b044739a302e616d0a55563ab936de4af893f9f71afa9cd59387f20e8e71f
  REVISION = b401e0332adfbf0460d319b06d8ea29279a941f1 (Gethe forever / tag 1.60.1, build 70425). The FILES checksums are unchanged.
If AGENTS.md names REVISION as a hand pin with a note, update the note. The spec is now 1000 lines, sift's no-growth limit.
Run the full gate, including the tracker host spec against the fetched 70425 source. One PR: "fix: shared tracker host from SPF 60300a7 (70425 UI)".
