# Score excerpts

`dovahkiin-opening.json` transcribes the repeated opening phrase in measures 2–5
of the sheet-music image supplied in the chat. It is an excerpt, not the complete
page, and omits the initial measure. It uses written B-flat trumpet pitches
(B4, C-sharp5, D5), without concert-pitch transposition. To sound at concert pitch,
transpose each frequency down two semitones (multiply by 2 ** (-2 / 12)).

Tempo 120 quarter-note beats per minute is a playback choice because no numeric
tempo is visible. Eighth notes are 0.5 beats and sixteenths are 0.25 beats.
Each 6/8 measure totals 3 quarter-note beats. Dynamics and accents are omitted
from the current frequency/duration-only format. The excerpt contains no rest;
the default demonstration score still supplies the PS2 five-notes-and-rest demo.

From the project root, with main.py running and a separate status watcher:

```sh
python src/test_commands.py score --score-file scores/dovahkiin-opening.json --performance dovahkiin-opening
python src/test_commands.py start --scope section --performance dovahkiin-opening
python src/test_commands.py stop --scope section --performance dovahkiin-opening
```

Only execute STOP if you want to interrupt playback. The selected section comes
from config.json. This is a melody part; harmony and rhythm are not supplied by
the single trumpet staff in the reference.
