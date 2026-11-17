T2R 6004 / TR37 partial sound pack, 0.2.0

Shipped with the game (assets/vehicles.json, #636) for the hybrid T3 (t3h): pick it in the menu's Sounds.
The default stays the built-in sounds.
The game plays the .ogg files (Ogg Opus). Each names its .wav as its fallback, which a browser that cannot
decode Opus plays (Safari before 18.4). The .wav files are the masters: after a change to one, or to an event,
run python -P -E tools/sound_encode.py assets/jnd.t2r6004 (it also refreshes the files' sizes and hashes).
Starts: both complete user-trimmed takes; release: only the first selected clack.
Release gain: 0.25 at zero current, linearly rising to 1 at 480 A; master mute/pause still apply.
These are listening settings, not measured physical constants. One release take keeps gain ordering consistent.
Bell: medium; short/long are retained alternatives (name one in sounds.json's bell event and re-encode).
Door warning: full 3.2 s one-shot at the existing closing event. The loop is retained, not mapped.
Other sounds use the built-in synthesis. No ambient recording is assigned as an isolated motor/MG loop.
The .wav files preserve the approved bytes. See provenance.json for hashes and credits.
The package uses AGPL-3.0-or-later. See LICENSE.txt for the terms and the earlier CC0 release.
