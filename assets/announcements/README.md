# Czech stop announcements

The catalogue covers the five playable timetable runs. It includes the continuation from line 9
to line 10 at Nákladové nádraží Žižkov. Stops with the same name share a recording even when they
have different platform IDs. The ordered calls, request flags, platform IDs and pronunciation text
are in `manifest.json`.

Google Cloud Text-to-Speech generated the stock Czech Chirp 3 HD recordings in Aoede, Algieba and
Sulafat at 0.85×. [Generated audio usage](https://docs.cloud.google.com/text-to-speech/docs/basics)

The route order and the transfer notices come from the pinned PID GTFS timetable (ROPID / PID,
CC BY 4.0). Only transfers shared by the matching timetable trips are announced. The roadway and
pronunciation facts are in `data/truth.json`. The script matches the times and platform records
of both legs of the 9→10 run before assigning its announcements.

The game preloads recordings at the preceding stop and shares downloaded MP3s between runs using
the browser's Cache Storage when available. The catalogue's audio version changes when the clip
payload changes. A changed itinerary can use the same catalogue for known names, request flags
and the next-stop cue. Its transfer and roadway notices require a verified route sequence.
Browser Czech speech uses the text and the selected volume, with 100% at the platform's maximum.

To regenerate, fetch the built data and use an authenticated Google Cloud CLI and a project with
Text-to-Speech enabled. The generator reads the pinned PID feed from `raw/` or the machine cache.

```sh
python -I tools/announcements.py --project PROJECT_ID
```
