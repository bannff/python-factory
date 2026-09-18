# M8 — Rebrand: strip KiroCrew identity from the port

**Owner ruling (2026-09-14 14:29):** "kirocrew is a part of companion-x but i dont want it to be called kirocrew so i expect any kirocrew branded features to be stripped. companion-x is a sub project of python-factory which is a polylith mono-repo. I think at some point i'd like to make companion-x its own repo. For now, we can just create rebranding stories to strip any kirocrew branding from the feature migration. I'll need to know where we need to insert some substitute (like a link or icon)."

**Product name:** Companion-X (unchanged). KiroCrew is the *upstream reference* and, in exactly one place, a *data source* the importer reads. Nowhere else.

**Runs:** after M7.5 closes, before M9 Deferred features (owner order).

---

## 1. Principles

1. **One spelling.** `Companion-X` in prose and titles; `companion_x` in code identifiers; `companion-x` in slugs/IDs. Today the frontend has 34× "Companion X" and 2× "Companion-X" — story R-01 normalises.
2. **Branding is data, not code.** Every owner-supplied substitute (repo URL, docs URL, feedback URL, changelog source, logo) lives in ONE place — `projects/companion_x/branding.py` (a tiny Pydantic model with env overrides, exposed read-only through the existing Settings/About MCP surface) — so moving Companion-X to its own repo later is one edit, not a hunt. No hard-coded URLs in components.
3. **"KiroCrew" may appear only where it names the foreign source:** the Migration brick's `kirocrew-v1` adapter id, the Settings → Import copy ("Bring supported KiroCrew data into Companion-X"), and Lessons provenance ("Imported from KiroCrew"). Everything else is a defect.
4. **A KiroCrew-owned capability is never "pointed to".** If a KiroCrew feature is CORE for Companion-X, Companion-X implements it; a panel that says "turn this on in the KiroCrew app" is `PRESENT+BROKEN`.

## 2. Branding census (run at M8 start and at M8 exit — Gate 0 cites the numbers)

```bash
# user-facing branding leaks (should return ONLY the three legitimate importer/provenance sites at exit)
grep -rIn -iE "kiro ?crew|kirodotdev|kiro\.dev" frontends/next-dashboard/{app,components,lib} components/*/src bases/*/src projects/companion_x \
  | grep -vE "components/migration/|import-panel\.tsx|import-api|lesson-language\.ts|lessons/(runtime/identity|mcp/import_record)\.py"
# name consistency
grep -rIhoE "Companion[ -]X" frontends/next-dashboard/{app,components} | sort | uniq -c
```

Baseline 2026-09-14 14:29: 1 leak (`components/settings/computer-use-settings-panel.tsx:4`), 34/2 name split, 0 brand assets in `frontends/next-dashboard/public`, 0 upstream links.

## 3. Stories

Each story ends `PRESENT+WORKS` or `OWNER_NA`; the feature-map row is flipped in the same slice. "Substitute" = what the owner must hand over before that story can close (collected once, see §4).

### R-01 · Name consistency (new; not a feature-map row)
Normalise "Companion X" → "Companion-X" in all user-facing strings, titles, `<title>`, README, and the rail header. Add a vitest that fails on the unhyphenated spelling in `components/`, `app/`. **Substitute:** none.

### R-02 · Branding config (new; enables everything below)
`projects/companion_x/branding.py`: `product_name`, `repo_url`, `docs_url`, `feedback_url`, `changelog_url`, `logo_path`, `license_notice`. Env-overridable (`COMPANION_X_BRAND_*`). Exposed via the existing Settings → About read path (row 101). Consumed by R-05..R-08. **Substitute:** repo URL, docs URL (may equal repo README), feedback URL (may be repo Issues), logo SVG (may keep the current purple "X" tile — owner decides).

### R-03 · Computer Use is Companion-X's own (row 93, CORE by owner ruling)
Today the panel says "Turn Computer Use on in the KiroCrew app's Settings → Computer Use. Companion-X cannot see whether it is currently on or change it." Replace with a Companion-X capability: a `computer_use` capability surfaced by the agent runtime (macOS accessibility permission check, on/off owner preference in the durable Settings store, and the agent's tools gated by it), with the panel showing real state and a real toggle. Re-spec against upstream `kiro_crew/computer_use/` for the *behaviour contract* only. Needs meta-architect + security consult (permissions, tool gating). **Substitute:** none.

### R-04 · About page (row 101) and Releases (row 100, CORE)
About shows Companion-X name, version (from `projects/companion_x` package metadata), installed bricks/tools (already there), and links from R-02. Releases becomes Companion-X's own story: version + changelog rendered from `changelog_url`/`CHANGELOG.md` in this repo; **no self-update mechanism** (Companion-X is run from source via the launcher — say so plainly on the page). "Update check" compares the running version to the repo's latest tag when `repo_url` is set. **Substitute:** repo URL (for tag check); decide whether a `CHANGELOG.md` will be kept.

### R-05 · Row 119 Kiro sign-in → **OWNER_NA candidate**
Upstream: sign-in to the Kiro account/ACP. Companion-X has no Kiro account; models come from OpenRouter/Bedrock via `llm_gateway`. Proposed: N/A, with provider credential status shown on Settings → Secrets (row 98) instead. **Substitute:** owner's "yes N/A".

### R-06 · Row 117 Cloud launch → **OWNER_NA candidate**
Upstream: one-click launch of a KiroCrew instance in the user's AWS. Companion-X deployment lives in the separate `art-platform` repo. Proposed: N/A for now; revisit if Companion-X becomes its own repo with its own deploy. **Substitute:** owner's "yes N/A".

### R-07 · Row 118 Mobile connect → **OWNER_NA candidate**
Upstream: QR pairing of the KiroCrew mobile companion. No Companion-X mobile app exists. Proposed: N/A. **Substitute:** owner's "yes N/A".

### R-08 · Row 120 Source-provider review → re-spec
Upstream: the GitHub/GitLab connection review screen. Companion-X equivalent: the Connections tab already lists MCP servers/powers; add a "Source providers" section that shows the `@github` MCP power status and the `repo_url` from R-02. **Substitute:** repo URL.

### R-09 · Row 121 Crash report notice → re-spec (small)
Upstream: post-crash banner offering to send a report to KiroCrew. Companion-X: reuse the Notification inbox — on API restart after an unclean exit, post one owner notification linking to the local log (Developer → logs, row 104) and to `feedback_url`. No telemetry leaves the machine. **Substitute:** feedback URL.

### R-10 · Row 122 Startup feature video → **OWNER_NA candidate**
Upstream marketing onboarding video. Proposed: N/A; the Welcome canvas already exists. **Substitute:** owner's "yes N/A".

### R-11 · Row 123 OpenAI-compatible API → re-spec (later in M8)
Upstream: KiroCrew exposes itself as an OpenAI-compatible chat endpoint so other tools can call it. Genuinely useful for Companion-X (opencode and others could call Companion-X as a model). Re-spec as a `bases/api` route backed by the LangChain runtime, token-authenticated with the existing MCP local auth. Needs security consult. **Substitute:** none.

### R-12 · Rows 132–140 Redirects → **ditch**, keep one guard
Upstream: KiroCrew's old URLs forwarding to new ones. Companion-X has its own routes; nothing to forward. Ditch 132–139. Keep **row 140 "anything unmatched"** as Companion-X's own 404 page (branded, links back to Welcome). **Substitute:** none.

## 4. Substitutes the owner must supply (collected ONCE at M8 start)

| # | What | Used by | Default if not supplied |
|---|---|---|---|
| S-1 | GitHub repo URL for Companion-X | About, Source providers, Releases tag check, 404 page | none — those links are hidden until set |
| S-2 | Docs URL | About | repo README |
| S-3 | Feedback / issues URL | About, crash notice | repo Issues |
| S-4 | Logo (SVG) | rail header, About, 404 | keep current purple "X" tile |
| S-5 | Keep a `CHANGELOG.md`? yes/no | Releases | Releases shows version only |
| S-6 | N/A confirmations for R-05, R-06, R-07, R-10 | feature map | rows stay `OWNER_REBRAND` |

The owner has said Companion-X may become its own repo later — S-1..S-3 are therefore config values (R-02), never literals.

## 5. Exit

- Census (§2) returns only the three legitimate sites; name split is 0/N.
- All 16 `OWNER_REBRAND` rows are `PRESENT+WORKS` or `OWNER_NA` (owner's words quoted).
- R-01..R-04 done; R-03 has meta-architect + security verdict IDs.
- One screenshot each: About, Releases, Computer Use, 404.
