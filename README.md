# AI DJ Mixer

AI DJ Mixer is a personal project that turns a folder of tracks into a single continuous megamix — the kind of hook-cut set you'd hear from a DJ working a party, not a slow-blend club mix. It's not trying to replace a professional DJ; it's scratching my own itch to throw ML at a problem I actually care about: automatically finding good transition points and sequencing a set that holds energy across ~15 tracks in ~17 minutes.

The pipeline splits into three stages by iteration cost: an audio analysis stage (beat/downbeat tracking, chroma, cue-point detection) that's expensive and cached; a metadata-only planning stage that scores every possible track transition and searches for the best path through the set as an orienteering problem, not a BPM sort; and a deterministic render stage that executes the plan (crossfades, bass swaps, time-stretching) with no decision-making of its own. Framing transition-strategy selection as a cost term inside the search — rather than a fallback — was the main design problem worth solving here.

See `resources/ai-dj-domain-and-architecture.md` for the full design rationale and `resources/architecture_diagram.drawio` for the pipeline diagram.
