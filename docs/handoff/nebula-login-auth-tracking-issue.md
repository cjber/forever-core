# Tracking: login, vault and session persistence failures block all authenticated automation

**Labels:** bug, area:auth, area:browser, area:integrations
**Type:** tracking issue
**Opened by:** @cillian (reported through the #wow-addons channel)

## Summary

Authenticated automation in this workspace is currently impossible end to end. Four distinct faults chain together: the Bitwarden integration is reported as connected in the member's settings UI but is absent from the agent runtime; the only services we need to sign into (CurseForge and friends) have no password login at all, so vault credentials cannot be typed anywhere; the hosted browser cannot satisfy Google's passkey prompt and its auth challenge is inconsistent between runs; and browser sessions die with the run, so a sign-in cannot be reused. The net effect is that every task needing a signed-in third-party session has been blocked for days, and the member has asked three times to "just use Bitwarden".

## Environment

- Member: cillian (workspace 38f1, slug `cillian`)
- Agents involved: WoW Addons Maintainer, Device Operator, Claude Code, Codex
- Cloud sandboxes: "Personal Computer" (dev_06a15f41dd527a1280006c228cb6e1cf), "cayman" (dev_06adc8bfe0d17f8d8000e15bf82c3841)
- Browser: hosted browser automation tool, not a local browser
- Target site: curseforge.com (a Google-SSO-only site)

## Impact

- CurseForge comment replies are paused with a live backlog: 38 on skillup-forever, 63 on shortest-path-forever, 12 on adventure-guide-forever, 3 on legacy-forever, 3 on tweaks-forever.
- CurseForge and Wago publishing and the GitHub-side release replies that need a signed-in session cannot run.
- Any future task requiring a signed-in third-party site inherits the same block. The work is not addon-specific.

## Repro A - Bitwarden shows connected, runtime says not connected

1. Settings > integrations shows Bitwarden as connected for the member.
2. Ask an agent to use the vault for a site login. The result is a "connect a vault" card, i.e. the runtime treats Bitwarden as not connected.
3. Inspect agent-side: the integration exists in the catalogue but reports `not_connected` and asks for API credentials. There are no vault tools, no Bitwarden CLI, no vault file on the sandbox, and no stored variables at all for this workspace.

Observed 2026-10-23 and again unchanged 2026-10-25.

Control: Gmail, Google Calendar, Google Sheets, Reddit, Strava, YouTube, GitHub and Telegram are all connected in the same settings page and all resolve correctly agent-side, so the app-list lookup itself works and this is not a general integration-plumbing outage.

## Repro B - CurseForge has no password login, so vault entries cannot help

1. Open a CurseForge addon page signed out: "Want to Join the Conversation? Sign In to continue".
2. Click Sign In. The only options are Google, Discord, GitHub, Twitch and WeChat. There is no email/password form anywhere on CurseForge.
3. A CurseForge vault entry therefore has no field to be typed into. The instruction "log in with the Bitwarden password" cannot be satisfied on this site even with a working vault.

Observed 2026-10-23.

## Repro C - Google SSO cannot be completed in the hosted browser

1. Click "Log in with Google" from CurseForge.
2. Run 1 (2026-10-23): the browser entered the account address, then Google served "Use your passkey to confirm it's really you". A cloud browser cannot satisfy a passkey, so the run ended there.
3. Run 2 (2026-10-23): the run stalled at the same Google passkey prompt, having reached the sign-in page with the account name resolved but the password field empty.
4. Run 3 (2026-10-25): "Log in with Google" now reached Google's "Sign in to continue to CurseForge" page showing the Email or phone field, i.e. a password path was offered this time.

So the auth challenge Google serves is not stable between runs (passkey-only one day, password field the next), which makes any scripted flow unreliable.

## Repro D - session does not persist beyond a run

1. Complete (or attempt) a sign-in inside a run.
2. Start a new run and open the same site: it is signed out again.
3. Consequence: sign-in and the authenticated action (posting a batch of replies) have to happen inside a single run, which makes the passkey/2FA window a hard blocker rather than an inconvenience.

Observed 2026-10-23 and 2026-10-25.

## Related - browser engine reliability

On 2026-10-23 the browser engine failed in three different ways across attempts at the same page: attempt 1 rendered the page correctly but the agent reported "unverified / did not complete"; attempt 2 returned a hard "browser unavailable" upstream error with zero steps; the retry then worked. Relevant because it makes "did the sign-in fail or did the tooling fail?" indistinguishable.

## Related - unable to file this as a GitHub issue from the workspace

Every attempt to reach the Nebula backend repository from the workspace is refused:

`GitHub access denied: this request targets the GitHub owner 'agent-labs-dev', but this workspace's GitHub App is installed only for cjber`

Confirmed on both cloud sandboxes, with `gh api` and with the workspace GitHub toolkit, and there is no personal GitHub login to fall back on (`gh auth status` reports not signed in). Since admin action is needed either way: install the workspace GitHub App for the `agent-labs-dev` owner, or supply a scoped credential, so future reports land as trackable issues instead of email.

## Timeline

| When | What |
|---|---|
| 2026-10-23 | Bitwarden found absent from the runtime while the UI shows it connected; browser could not get past Google's passkey prompt. |
| 2026-10-23 18:36 BST | Report emailed from cillian@nebula.me to support@nebula.gg, subject "Bug: Bitwarden shows connected in settings but is absent from the agent runtime". Read-back confirmed in the sent mail. |
| 2026-10-25 | Re-verified: Bitwarden still `not_connected` agent-side; CurseForge still signed out; Google now offers a password field instead of a passkey. No change from the email. |

## Suggested angles

- The Bitwarden connection may be recorded client-side only, written per-member but never surfaced to the runtime that builds the agent-side app list, or scoped per-member vs per-workspace incorrectly.
- The vault bridge may not reach the hosted browser's credential injection, which is what the "it's automatic" expectation depends on.
- Passkey/2FA challenge handling needs a documented, supported path for a hosted browser (or an explicit "unsupported, use a login card" contract surfaced before the run starts).
- Session persistence across runs needs stating as either a supported feature or not, so agents stop promising it.

## Acceptance criteria

- A member who connects Bitwarden sees it connected agent-side, or the UI stops claiming it is connected while the runtime cannot use it.
- SSO-only sites can be authenticated through a documented supported path, or the limitation is surfaced up front rather than mid-run.
- Whatever auth challenge Google serves (password, passkey, device prompt) has a defined behaviour.
- Cross-run session behaviour is documented.
- Workspace GitHub access covers the backend repository so tracking issues can be filed directly.
