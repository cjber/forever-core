### For addon authors

- **The API kit shares world map markers and two more not-ready reasons.** `APIKit.RegisterMapMarkers(addonName, read)` and `APIKit.MapMarkers(map, except?)` replace the `ForeverMapMarkers` global each addon copied. `NotReady` also takes `"combat"` and `"unreachable"`, and `docs/api-conventions.md` says to answer anything else with `"none"`. `check_api_docs.py` now fails a hand-written `return nil, "invalid"` and any literal reason outside that set. (cjber/forever-core#961)
- **ForeverCore publishes its own API.** It is the `"ForeverCore"` entry of `APIKit.Addons()`; `ForeverCore.API` stays a number.
- **`ForeverCore.Journey` is removed.** No addon called it.
