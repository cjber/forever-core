### Fixed

- **An addon carrying its own ForeverCore starts it in every case.** It also starts when the addon is turned on after you log in, and in a session where the game's login event did not reach it. Before, it could stay waiting with no error, leaving no Forever tracker column or settings page. (#837)
- **An outdated ForeverCore install is named.** If the separate ForeverCore you have installed is too old for the addons that carry their own copy, the error now names its version and says to update or turn it off, instead of the addons failing one by one. (#837)
