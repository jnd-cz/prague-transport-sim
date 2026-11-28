# Line 17 announcement pilot

Google Cloud Text-to-Speech created these 129 Czech MP3s with the stock Chirp 3 HD voices Aoede,
Algieba and Sulafat at 0.85×. Google documents use of generated audio in applications under the
Google Cloud terms. [Cloud Text-to-Speech usage](https://docs.cloud.google.com/text-to-speech/docs/basics)

`manifest.json` maps each GTFS stop occurrence to an ordered list of segments and each segment to its text
and clip per voice. `spoken` gives an alternate pronunciation, used by both the generator and browser speech.
The 37 stop names are reused for current and upcoming stops. Six shared clips cover the next-stop cue, two transfers,
two request-stop notices and the terminus.
The stop sequence, transfer icons and request flags come from the 77 matching line 17 timetables in the pinned PID GTFS snapshot
(ROPID / PID, CC BY 4.0). The roadway notice at Březiněveská applies only towards Kobylisy, per `data/truth.json`.
The pilot runs towards Líbeznická. The sequence and terminus message come from the maintainer's ride observation in #894.
The pilot reads metro before rail where both apply. It adds `Zastávka na znamení.` after the current
request stop and `Příští zastávka je na znamení.` after the upcoming request stop. The shift starts with
the selected departure stop's announcement. The next stop's clips load at the preceding stop.

To regenerate, fetch the built data and use an authenticated Google Cloud CLI and a project with
Text-to-Speech enabled. The generator reads the pinned PID feed from `raw/` or the machine cache.

```sh
python -I tools/announcements.py --project PROJECT_ID
```

In the test build, choose line 17 and set **Announcement voice** and **Announcement timing** in the menu.
**Browser Czech voice** appears when the device reports a Czech Web Speech voice and reads the manifest at playback.
For a timing comparison, start at Výstaviště with autoplay and repeat the same trip at 100 m, 50 m and on
arrival. Listen for Nádraží Holešovice, both transfers, and the next stop over the cab noise.
For the two request-stop notices, start at Modřanská rokle and ride to U Libušského potoka.
