# Line 17 announcement pilot

Google Cloud Text-to-Speech created these 111 Czech MP3s with the stock Chirp 3 HD voices Aoede,
Algieba and Sulafat at 0.85×. Google documents use of generated audio in applications under the
Google Cloud terms. [Cloud Text-to-Speech usage](https://docs.cloud.google.com/text-to-speech/docs/basics)

`manifest.json` records the text, voice, GTFS platform ID and clip for each stop occurrence. The stop
sequence and transfer icons come from the 77 matching line 17 timetables in the pinned PID GTFS snapshot
(ROPID / PID, CC BY 4.0). The Březiněveská roadway notice follows the directional stop fact in
`data/truth.json`. The sequence and terminus message come from the maintainer's ride observation in #894.
The pilot reads metro before rail where both apply.

To regenerate, fetch the built data and use an authenticated Google Cloud CLI and a project with
Text-to-Speech enabled. The generator reads the pinned PID feed from `raw/` or the machine cache.

```sh
python -I tools/announcements.py --project PROJECT_ID
```

In the test build, choose line 17 and set **Announcement voice** and **Announcement timing** in the menu.
For a timing comparison, start at Výstaviště with autoplay and repeat the same trip at 100 m, 50 m and on
arrival. Listen for Nádraží Holešovice, both transfers, and the next stop over the cab noise.
