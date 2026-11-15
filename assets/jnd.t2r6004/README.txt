T2R 6004 / TR37 partial sound pack, 0.1.0

Requires game vehicle interface 1.2 (#590) and the hybrid T3 (t3h).
Install its ZIP or package.json address from Vehicles... in the game menu.
On a local dev server, the address is /assets/jnd.t2r6004/package.json.
Starts: both complete user-trimmed takes; release: only the first selected clack.
Release gain: 0.25 at zero current, linearly rising to 1 at 480 A; master mute/pause still apply.
These are listening settings, not measured physical constants. One release take keeps gain ordering consistent.
Bell: medium; short/long are retained alternatives (edit the bell event before installing).
Door warning: full 3.2 s one-shot at the existing closing event. The loop is retained, not mapped.
Other sounds use the built-in synthesis. No ambient recording is assigned as an isolated motor/MG loop.
All WAV files preserve the approved bytes. Source hashes and credits: provenance.json; CC0: LICENSE.txt.
