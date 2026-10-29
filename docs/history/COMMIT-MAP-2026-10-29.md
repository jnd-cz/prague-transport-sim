# Commit ids before and after the author rewrite (2026-10-29)

On 2026-10-29 every commit's author and committer address was changed to the GitHub private address
(`2506000+jnd-cz@users.noreply.github.com`) before the repository was shared. The file trees are
unchanged; the commit ids changed. Older notes, session transcripts and the remote copy's documents
(REMOTE-CHANGES.md, ARCHITECTURE-PROPOSAL.md: "base 6839a81") cite the old ids: look them up here.

| old | new | subject |
|---|---|---|
| `6504637` | `f6880db` | Model decks: the other track's half of the structure on our bridges, a wider window, and a… |
| `c6cd39e` | `80c9a19` | GTFS shape matching starts on the right-hand track (line 37 ran 1.7 km on the left track f… |
| `6839a81` | `780153b` | Fine terrain near the tracks (2 m DMR 5G blocks) for all lines, local OSM extract for buil… |
| `f7181d6` | `8cb6cda` | Bridge models trimmed to the surveyed decks (Štefánikův most), Vienna check without the tr… |
| `7756a87` | `ae2fdda` | Priority 1 and A2: tunnels and bridges as whole chains (portals, abutments, cut-off ends),… |
| `57ddb20` | `edb60db` | Exact nearest point on a route (the Letenská interlaced track is a gauntlet again on line … |
| `cb0fd30` | `5862ce6` | Consolidated project state: PLAN §1 (state, done today, open proposals, user observations … |
| `8514dd2` | `3c8aa00` | Line 17: world to ~220 m, lanes from OSM lane tags and the surveyed carriageway (divider b… |
| `cc16cfa` | `4eeb17a` | Lane quality lint (off carriageway, tram bed, stops, kinks, doubled, walkers on roads), or… |
| `2a758a6` | `d4989bc` | Plane-fitted street surfaces, minimum track spacing, road tunnels and the Vyšehrad tunnel |
| `54f81c6` | `7d59457` | Inspect mode (?inspect or I): autopilot at 1/4x-32x time with pause, orbit and fly mouse c… |
| `00e5814` | `5d8aabc` | Measured street/track look: five new lints, level spans, vertical curves, support under ra… |
| `b686887` | `2710b2e` | Line 17 fixes: survey outliers above ground rejected, one track height for drawn tracks an… |
| `9ccef30` | `0e6406f` | Line 17 on the surveyed streets (DTM, all districts), two levels at bridges and underpasse… |
| `fb6e0a6` | `0ef38e4` | Docs: HANDOFF §16 (lint-driven work, findings, open items), PLAN status and next steps, RE… |
| `c0acbb8` | `ca8e541` | Junction controllers with fixed cycles and tram priority; oncoming trams obey them; traffi… |
| `82cfae8` | `1989886` | Trams stop behind cars on their track (AI trams and autopilot); the crossing wait only for… |
| `be60ce9` | `25debef` | Bridges: poles stand on the deck, track ramps at most 6 % from a span's ends, no bridge mo… |
| `7e8c148` | `f0186c8` | Cars see trams, walkers and cars on their path; sidewalks beyond the surveyed kerb; no jun… |
| `876049c` | `0e6a129` | Banked curves: smooth cant profile with linear run-in/out (100 mm per 30 m), level at stop… |
| `7185347` | `0d84a49` | Lane graph for cars: smooth lanes per road and direction, junction connectors, curve speed… |
| `91af658` | `7096661` | Tier A done: hung signals may use bracket arms; new baselines; plan: grade separation, lin… |
| `fa11db4` | `5416c52` | Mirror inside the cab frame on a realistic arm; performance overlay and automatic-switch m… |
| `929a274` | `f0f8eb0` | Calm autopilot heating (hysteresis, 20 s between changes), smooth cab pitch at a dead stop… |
| `00b5a38` | `59fec74` | Curve speeds from lateral acceleration, OSM posted speeds (OpenRailwayMap data), cant on d… |
| `aaa2319` | `d99a2d1` | Signals never along a platform; hung signals and signs clear of the tram envelope (lint: t… |
| `9b47169` | `62cb868` | Vegetation by register category: bushes, planters, no climbers; trees clear of buildings |
| `d6ca0ff` | `81330e0` | No invented retaining walls where the surveyed streets describe the ground (lint: invented… |
| `1f7dc95` | `174b4f0` | PLAN: reordered priorities with the evening issues, findings on curve speeds, walls, trees… |
| `413000e` | `170ec89` | Headless traffic run with slide/jump/overlap/walker lints (PLAN step 2) |
| `2c1542b` | `4b7bd81` | Lint runner with baselines (PLAN step 1); routes continue past both termini (two-car set a… |
| `546c353` | `f38ebc4` | Street model pilot (Karlovo nám. – Jana Masaryka), bot slope-aware steps, PLAN.md |
| `655800d` | `5b2bdec` | Ground truth file and report upload endpoint for the lint runner (PLAN step 1, part) |
| `5a83b45` | `398a25f` | Street model pilot (line 22, Karlovo nám. - Jana Masaryka), PLAN.md with priorities and ap… |
| `e6b1e67` | `9d8b447` | Street bot (?bot) and DTM street fixes: lanes fitted to kerbs, one drawn surface height, i… |
| `a37548a` | `eeabdd4` | Prague DTM pilot (line 22, Praha 2 + 10), real junctions for cars |
| `44ca73f` | `cd4a061` | Credit the T3 model: Jakub Vaja (conflig) on Sketchfab |
| `68573d5` | `fcaf7d3` | Fit T3 to its wheels, exact route boxes, kerb/hung signals, deploy package |
| `1e2c882` | `70f1553` | Add Continue / Back to menu buttons to the pause screen |
| `b49626b` | `958c8f1` | Line runs, platforms, heating, mirror, bridges, detailed T3 and more |
| `4c984ab` | `028549d` | Note the git setup in the handoff notes |
| `998c94d` | `5b494e2` | Initial commit: Tatra T3 Prague tram browser game |
