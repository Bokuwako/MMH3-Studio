"""Each act directive from PromptDirector acts.ACTS cut into its original clauses.

Joining a preset's segments gives back the directive character for character. Kinds:
  name   - the act's name sentence. Kept unless the shot turns the act name off.
  core   - postures, who is where, contacts that keep the other person drawn. Always kept.
  place  - placement that needs the tagged parts in frame. Always kept; when every
           tagged part is off the brief reports a conflict instead of guessing.
  act    - the main action. Its tags are the parts the action implies even when they are
           not named. When all of them are off it is replaced by `frame`, a neutral
           sentence about what stays visible in frame.
  part   - detail about the tagged parts. Dropped when every tagged part is off.
  motion - movement detail of the tagged parts. Same rule as part.
Removable segments start with their own separator and hold no sentence-final period.
"""

PARTS = {
    "face": "얼굴·입", "neck": "목·어깨", "chest": "가슴", "arms": "팔", "hands": "손",
    "waist": "허리", "back": "등", "hips": "골반", "buttocks": "엉덩이", "genitals": "성기",
    "thighs": "허벅지", "legs": "다리", "feet": "발",
}


def S(text, kind="core", *parts, frame=None):
    return {"text": text, "kind": kind, "parts": parts, "frame": frame}


def free(who, *parts):
    names = {"hands": "hands", "face": "face", "head": "head"}
    words = " and ".join(names[p] for p in parts)
    tags = [who + ":" + ("face" if p == "head" else p) for p in parts]
    return S("; {%s}'s %s are free" % (who, words), "part", *tags)


BOTH_GENITALS = ("A:genitals", "B:genitals")
ROCK = ", and moves against {A} in a steady rhythm, their upper bodies rocking together"

ACT_PARTS = {
    "missionary": [
        S("Missionary.", "name"), S(" {A} lies face up"), S(" with legs apart", "part", "A:legs"), S("."),
        S(" {B} lies over {A}"), S(" between {A}'s spread legs", "part", "A:legs"),
        S(", chest to chest", "core", "A:chest", "B:chest"), S(" and hips to hips", "part", "A:hips", "B:hips"),
        S(", and thrusts into {A}", "act", *BOTH_GENITALS, frame=ROCK),
        S(", {B}'s hips driving forward and back along the line of {A}'s body", "motion", "B:hips"),
        S(". {A} stays lying beneath {B}."),
    ],
    "missionary_knees": [
        S("Missionary, legs raised.", "name"), S(" {A} lies face up beneath {B}"),
        S(" with {A}'s legs raised and wrapped around {B}'s waist", "part", "A:legs", "B:waist"), S("."),
        S(" {B} lies over {A}"), S(" between {A}'s thighs", "part", "A:thighs"),
        S(", chest to chest", "core", "A:chest", "B:chest"), S(" and hips to hips", "part", "A:hips", "B:hips"),
        S(", and thrusts into {A}", "act", *BOTH_GENITALS, frame=ROCK),
        S(", {B}'s hips driving forward and back along the line of {A}'s body", "motion", "B:hips"),
        S(". {A} stays lying beneath {B}."),
    ],
    "mating_press": [
        S("Mating press.", "name"), S(" {A} lies face up."), S(" {B} kneels over {A} from above"),
        S(", leaning down with {B}'s weight"),
        S(", and presses {A}'s legs back toward {A}'s own shoulders", "part", "A:legs", "A:neck"), S("."),
        S(" {B} thrusts steeply downward into {A}.", "act", *BOTH_GENITALS,
          frame=" {B} moves over {A} in a steady downward rhythm, their upper bodies rocking together."),
        S(" {A} stays pinned under {B} and does not thrust"), free("A", "hands", "face"), S("."),
    ],
    "side_front": [
        S("Side by side, facing.", "name"), S(" {A} and {B} both lie on their sides facing each other"),
        S(", legs interlocked", "part", "A:legs", "B:legs"), S("."),
        S(" {B} thrusts into {A} with short strokes, back and forth.", "act", *BOTH_GENITALS,
          frame=" {B} moves against {A} with short, steady motions, their upper bodies rocking together."),
        S(" {A} stays on {A}'s side."),
    ],
    "lotus": [
        S("Lotus, seated face to face.", "name"), S(" {B} sits"), S(" with legs crossed", "part", "B:legs"), S("."),
        S(" {A} sits in {B}'s lap facing {B}", "core", "B:thighs"), S(", legs around {B}'s waist", "part", "A:legs", "B:waist"),
        S(", chests together", "core", "A:chest", "B:chest"), S("."),
        S(" {A} thrusts vertically with short rises and drops onto {B}.", "act", *BOTH_GENITALS,
          frame=" {A} rises and sinks against {B} in a steady rhythm, their upper bodies rocking together."),
        S(" {B} stays seated and does not thrust"), S(", holding {A}'s hips", "part", "B:hands", "A:hips"), S("."),
    ],
    "standing_front": [
        S("Standing, facing.", "name"), S(" {A} and {B} stand chest to chest", "core", "A:chest", "B:chest"),
        S(" and hips to hips", "part", "A:hips", "B:hips"),
        S(", {A} with one leg raised and held by {B}", "part", "A:legs", "B:hands"), S("."),
        S(" {B} thrusts upward into {A}.", "act", *BOTH_GENITALS,
          frame=" {B} moves against {A} in a steady upward rhythm, their upper bodies rocking together."),
        S(" {A} stays standing and holds onto {B}.", "core", "A:hands", "A:arms"),
    ],
    "carry": [
        S("Standing carry from behind.", "name"), S(" {B} stands upright and holds {A} up from behind", "core", "B:arms"),
        S(" by the backs of {A}'s thighs", "part", "A:thighs", "B:hands"),
        S(", {A}'s legs held apart and hanging over {B}'s forearms", "part", "A:legs", "B:arms"), S("."),
        S(" {A} faces away from {B}"), S(", {A}'s back against {B}'s chest", "core", "A:back", "B:chest"),
        S(", and {A} does not hold onto {B}"), S("."),
        S(" {B} thrusts upward from below, lifting and dropping {A}", "act", *BOTH_GENITALS,
          frame=" {B} lifts and drops {A} in a steady rhythm, their upper bodies rocking together"),
        S(" onto {B}'s cock", "part", "B:genitals"), S("."),
        S(" {A} hangs in {B}'s arms and does not thrust.", "core", "B:arms"),
    ],
    "carry_front": [
        S("Standing carry, face to face.", "name"), S(" {B} stands upright and holds {A} up", "core", "B:arms"),
        S(" by the backs of {A}'s thighs", "part", "A:thighs", "B:hands"), S("."),
        S(" {A} faces {B}"), S(", chest to chest", "core", "A:chest", "B:chest"),
        S(" and hips to hips", "part", "A:hips", "B:hips"),
        S(", {A}'s legs wrapped around {B}'s waist", "part", "A:legs", "B:waist"),
        S(" and {A}'s arms around {B}'s neck", "part", "A:arms", "B:neck"), S("."),
        S(" {B} thrusts upward, lifting and dropping {A}", "act", *BOTH_GENITALS,
          frame=" {B} lifts and drops {A} in a steady rhythm, their upper bodies rocking together"),
        S(" onto {B}'s cock", "part", "B:genitals"), S("."),
        S(" {A} holds on and does not thrust.", "core", "A:arms"),
    ],
    "edge": [
        S("On the edge of the bed.", "name"), S(" {A} lies face up"),
        S(" with {A}'s hips at the edge and {A}'s legs apart", "part", "A:hips", "A:legs"), S("."),
        S(" {B} stands on the floor between {A}'s legs", "place", "A:legs"),
        S(", hips to hips", "part", "A:hips", "B:hips"), S(", holding {A}'s thighs apart", "part", "B:hands", "A:thighs"),
        S(", and thrusts into {A}", "act", *BOTH_GENITALS, frame=ROCK),
        S(", {B}'s hips driving forward and back along the line of {A}'s body", "motion", "B:hips"),
        S("."), S(" {A} stays lying back"), free("A", "hands", "face"), S("."),
    ],
    "doggy": [
        S("Doggy style, from behind.", "name"), S(" {A} is on hands and knees", "core", "A:hands", "A:legs"),
        S(", back arched", "part", "A:back"), S(", facing away from {B}"), S("."),
        S(" {B} kneels upright behind {A}", "core", "B:legs"),
        S(" and thrusts into {A} from behind", "act", *BOTH_GENITALS,
          frame=" and moves against {A} in a steady rhythm, both bodies rocking together"),
        S(", {B}'s hips driving back and forth along the line of {A}'s spine", "motion", "B:hips"), S("."),
        S(" {A} stays braced and does not thrust"), free("A", "head", "hands"), S("."),
    ],
    "prone": [
        S("Prone.", "name"), S(" {A} lies flat face down"), S(" with legs together", "part", "A:legs"), S("."),
        S(" {B} lies over {A}'s back", "core", "A:back"), S(", {B}'s hips against {A}'s buttocks", "part", "B:hips", "A:buttocks"),
        S(", and thrusts into {A} from behind", "act", *BOTH_GENITALS,
          frame=", and moves against {A} in a steady rhythm, both bodies rocking together"),
        S(", {B}'s hips driving back and forth along the line of {A}'s spine", "motion", "B:hips"),
        S(". {A} stays flat underneath {B}."),
    ],
    "spooning": [
        S("Spooning.", "name"), S(" {A} and {B} both lie on their sides facing the same way, {B} behind {A}"),
        S(", {B}'s chest against {A}'s back", "core", "B:chest", "A:back"),
        S(" and {B}'s hips against {A}'s buttocks", "part", "B:hips", "A:buttocks"), S("."),
        S(" {B} thrusts into {A} from behind back and forth with shallow strokes.", "act", *BOTH_GENITALS,
          frame=" {B} moves against {A} from behind with shallow, steady motions, both bodies rocking together."),
        S(" {A} stays curled on {A}'s side."),
    ],
    "seated_behind": [
        S("Seated from behind.", "name"), S(" {B} sits upright."),
        S(" {A} sits down in {B}'s lap facing away from {B}", "core", "B:thighs"),
        S(", back against {B}'s chest", "core", "A:back", "B:chest"), S("."),
        S(" {A} thrusts vertically, rising and dropping onto {B}.", "act", *BOTH_GENITALS,
          frame=" {A} rises and sinks against {B} in a steady rhythm, their upper bodies rocking together."),
        S(" {B} stays seated"), S(" and holds {A}'s hips", "part", "B:hands", "A:hips"), S("."),
    ],
    "standing_behind": [
        S("Standing from behind.", "name"), S(" {A} stands bent forward at the waist", "core", "A:waist"),
        S(", hands braced on a surface", "part", "A:hands"), S(", facing away from {B}"), S("."),
        S(" {B} stands behind {A}"),
        S(" and thrusts into {A} back and forth.", "act", *BOTH_GENITALS,
          frame=" and moves against {A} in a steady rhythm, both bodies rocking together."),
        S(" {A} stays braced and does not thrust"), free("A", "head", "hands"), S("."),
    ],
    "wall": [
        S("Against the wall.", "name"), S(" {A} stands facing the wall"), S(" with both palms flat on it", "part", "A:hands"),
        S(", hips pushed back", "part", "A:hips"), S("."), S(" {B} stands behind {A}"),
        S(", pressed against {A}'s back", "core", "A:back"),
        S(", and thrusts into {A} forward and back, pressing {A} toward the wall.", "act", *BOTH_GENITALS,
          frame=", and moves against {A} in a steady rhythm, pressing {A} toward the wall."),
        S(" {A} stays braced against the wall."),
    ],
    "cowgirl": [
        S("Cowgirl, facing.", "name"), S(" {B} lies face up."),
        S(" {A} straddles {B}'s hips upright, facing {B}.", "place", "B:hips"),
        S(" {A} thrusts vertically, raising and dropping", "act", *BOTH_GENITALS,
          frame=" {A} rises and sinks in a steady rhythm, {A}'s upper body rocking with it"),
        S(" onto {B}'s cock", "part", "B:genitals"), S("."),
        S(" {B} stays lying down and does not thrust"), free("B", "hands", "face"), S("."),
    ],
    "reverse_cowgirl": [
        S("Reverse cowgirl.", "name"), S(" {B} lies face up."),
        S(" {A} straddles {B}'s hips upright, turned the opposite way round from {B}", "place", "B:hips"),
        S(", facing {B}'s feet", "core", "B:feet"), S("."),
        S(" {A} thrusts vertically, raising and dropping", "act", *BOTH_GENITALS,
          frame=" {A} rises and sinks in a steady rhythm, {A}'s upper body rocking with it"),
        S(" onto {B}'s cock", "part", "B:genitals"), S("."),
        S(" {B} stays lying down and does not thrust"), free("B", "hands", "face"), S("."),
    ],
    "blowjob": [
        S("Blowjob.", "name"), S(" {B} stands upright"), S(" with legs apart", "part", "B:legs"), S("."),
        S(" {A} kneels on the floor in front of {B}, facing {B}", "core", "A:legs"),
        S(", {A}'s head level with {B}'s hips", "place", "A:face", "B:hips"), S("."),
        S(" {A} takes {B}'s cock into {A}'s mouth and sucks it", "act", "B:genitals",
          frame=" {A} stays close against {B}, {A}'s head moving in a slow, steady rhythm"),
        S(", {A}'s head bobbing vertically along its length", "motion", "A:face", "B:genitals"),
        S(", one of {A}'s hands gripping the base", "part", "A:hands", "B:genitals"), S("."),
        S(" {B} stands still and does not thrust."),
    ],
    "cunnilingus": [
        S("Cunnilingus.", "name"), S(" {B} lies back"), S(" with legs apart", "part", "B:legs"), S("."),
        S(" {A} lies between {B}'s thighs", "place", "B:thighs"),
        S(" and licks {B}'s pussy", "act", "B:genitals", frame=", {A}'s head moving in a slow, steady rhythm"),
        S(", {A}'s tongue moving in slow strokes", "motion", "A:face", "B:genitals"), S("."), S(" {B} stays lying back."),
    ],
    "rimming": [
        S("Rimming.", "name"), S(" {B} is on hands and knees facing away.", "core", "B:hands", "B:legs"),
        S(" {A} kneels behind {B}", "core", "A:legs"),
        S(" and licks {B}'s asshole in slow strokes.", "act", "B:buttocks",
          frame=", {A}'s head moving in a slow, steady rhythm."),
        S(" {B} stays braced"), free("B", "head", "hands"), S("."),
    ],
    "sixtynine": [
        S("69.", "name"), S(" {B} lies on {B}'s back."),
        S(" {A} lies on top of {B} inverted, head to hips, so each mouth is at the other's crotch.", "place",
          "A:face", "B:face", "A:genitals", "B:genitals"),
        S(" {A} and {B} go down on each other at the same time — neither is only receiving.", "act", *BOTH_GENITALS,
          frame=" {A} and {B} move against each other in a slow, steady rhythm."),
    ],
    "handjob": [
        S("Handjob.", "name"), S(" {B} stands upright."), S(" {A} kneels or sits beside {B}, facing {B}"),
        S(", {A}'s upper body turned toward {B}'s hips", "part", "A:chest", "B:hips"), S("."),
        S(" {A} grips {B}'s cock in one hand and strokes it vertically, up and down, at a steady rhythm.", "act",
          "B:genitals", frame=" {A}'s arm moves in a steady rhythm."),
        S(" {B} stands still and does not thrust"), free("B", "hands", "face"), S("."),
    ],
    "fingering": [
        S("Fingering.", "name"), S(" {B} lies back"), S(" with {B}'s legs apart and knees raised", "part", "B:legs"), S("."),
        S(" {A} kneels or sits beside {B}"), S(", {A}'s hand between {B}'s spread legs", "part", "A:hands", "B:legs"), S("."),
        S(" {A} works two fingers into {B}'s pussy and thrusts them in and out", "act", "B:genitals",
          frame=" {A}'s arm moves in a steady rhythm"),
        S(", {A}'s thumb on {B}'s clit", "part", "A:hands", "B:genitals"), S("."),
        S(" {B} stays lying back and open"), free("B", "hands", "face"), S("."),
    ],
    "rubbing": [
        S("{B} lies back"), S(" with {B}'s legs apart", "part", "B:legs"), S("."),
        S(" {A} kneels or sits beside {B}"), S(", {A}'s hand between {B}'s spread legs", "part", "A:hands", "B:legs"), S("."),
        S(" {A} rubs {B}'s pussy and clit with {A}'s fingers in small fast circles.", "act", "B:genitals",
          frame=" {A}'s arm moves in small, quick motions."),
        S(" {B} stays lying back"), free("B", "hands", "face"), S("."),
    ],
    "mutual_hands": [
        S("{A} and {B} sit or lie side by side facing each other, close enough to reach."),
        S(" Each has a hand between the other's legs", "act", *BOTH_GENITALS, frame=" Each reaches for the other"),
        S(" — {A}'s hand on {B}'s crotch and {B}'s hand on {A}'s crotch —", "part", "A:hands", "B:hands", *BOTH_GENITALS),
        S(" and both stroke steadily at the same time."), S(" Neither is only receiving."),
    ],
    "titfuck": [
        S("Titfuck.", "name"), S(" {B} stands upright."), S(" {A} kneels in front of {B}, facing {B}.", "core", "A:legs"),
        S(" {A} presses {A}'s breasts together around {B}'s cock", "act", "B:genitals",
          frame=" {A} leans in close against {B}"),
        S(" with both hands", "part", "A:hands"),
        S(" and strokes {B}'s cock vertically", "act", "B:genitals", frame=" and moves in a steady rhythm"),
        S(", moving {A}'s chest up and down", "motion", "A:chest"), S("."),
        S(" {B} stands still and does not thrust"), free("B", "hands"), S("."),
    ],
    "thighjob": [
        S("Thigh job.", "name"), S(" {A} stands or lies with {B} close behind {A}."),
        S(" {A} presses {A}'s thighs tightly together with {B}'s cock between them from behind.", "act",
          "A:thighs", "B:genitals", frame=" {B} stays pressed close behind {A}."),
        S(" {B} thrusts back and forth between {A}'s thighs.", "act", "A:thighs", "B:genitals",
          frame=" {B} moves against {A} in a steady rhythm, both bodies rocking together."),
        S(" {A} keeps the thighs closed and does not thrust", "act", "A:thighs", frame=" {A} stays still and does not thrust"),
        free("A", "hands", "face"), S("."),
    ],
    "footjob": [
        S("Footjob.", "name"), S(" {B} lies back on {B}'s elbows", "core", "B:arms"), S(" with legs apart", "part", "B:legs"), S("."),
        S(" {A} sits facing {B}"), S(", leaning back on {A}'s hands", "part", "A:hands"),
        S(", {A}'s legs extended toward {B}'s hips", "place", "A:legs", "B:hips"), S("."),
        S(" {A} holds {B}'s cock between both of {A}'s feet and strokes it vertically, up and down.", "act",
          "A:feet", "B:genitals", frame=" {A} moves in a steady rhythm, leaning back."),
        S(" {B} stays lying back"), free("B", "hands", "face"), S("."),
    ],
    "intercrural": [
        S("Intercrural.", "name"), S(" {A} lies on {A}'s side or stands bent forward, with {B} close behind {A}."),
        S(" {B}'s cock is between {A}'s legs from behind, sliding under {A} rather than inside.", "act",
          "A:legs", "B:genitals", frame=" {B} stays pressed close behind {A}."),
        S(" {B} thrusts back and forth.", "act", "A:legs", "B:genitals",
          frame=" {B} moves against {A} in a steady rhythm, both bodies rocking together."),
        S(" {A} stays braced."),
    ],
    "frottage": [
        S("{A} and {B} stand pressed together face to face"),
        S(", {A}'s chest against {B}'s chest", "core", "A:chest", "B:chest"),
        S(" and {A}'s crotch against {B}'s crotch", "part", *BOTH_GENITALS), S("."),
        S(" Both grind their hips against each other, moving in opposite time.", "act", "A:hips", "B:hips",
          frame=" Both press and move against each other in a steady rhythm, their upper bodies rocking."),
        S(" Both are active."),
    ],
    "tribadism": [
        S("Tribadism.", "name"), S(" {A} and {B} lie facing each other"),
        S(" and press their pussies together", "act", *BOTH_GENITALS, frame=" and press close together"),
        S(", legs scissored", "part", "A:legs", "B:legs"),
        S(", and grind against each other back and forth.", "act", *BOTH_GENITALS,
          frame=", and move against each other in a steady rhythm."),
        S(" Both are active."),
    ],
    "kiss": [S("{A} and {B} are kissing, mouth to mouth, both actively — neither is only receiving.", "core", "A:face", "B:face")],
    "neck_kiss": [
        S("{A} kisses along {B}'s neck and collarbone, slowly.", "place", "A:face", "B:neck"),
        S(" {B} tilts {B}'s head back", "core", "B:face"), S("; {B}'s hands are free", "part", "B:hands"), S("."),
    ],
    "breast_play": [
        S("{A} works on {B}'s breasts with {A}'s mouth and hands, sucking and squeezing.", "act", "B:chest",
          frame="{A} leans in close over {B}, {A}'s head moving slowly."),
        S(" {B} holds still under {A}'s mouth and hands"),
        S("; {B}'s own hands and face are free", "part", "B:hands", "B:face"), S("."),
    ],
    "caress": [
        S("{A} runs {A}'s hands over {B}'s body", "core", "A:hands"), S(", shoulders to hips", "part", "B:neck", "B:hips"),
        S(", slowly and continuously."), S(" {B} stays where {B} is"), free("B", "hands", "face"), S("."),
    ],
    "embrace": [S("{A} and {B} hold each other tightly, bodies pressed together full length. Both are holding on.",
                  "core", "A:arms", "B:arms", "A:chest", "B:chest")],
    "masturbate_m": [S("{A} strokes {A}'s own cock vertically, up and down, at a steady rhythm.", "act", "A:genitals",
                       frame="{A}'s arm moves in a steady rhythm.")],
    "masturbate_f": [S("{A} works {A}'s own fingers between {A}'s legs in small fast circles.", "act", "A:genitals",
                       frame="{A}'s arm moves in small, quick motions.")],
    "mutual_watch": [
        S("{A} and {B} face each other"),
        S(" and touch themselves while watching the other.", "act", *BOTH_GENITALS,
          frame=", watching each other, their arms moving slowly."),
        S(" {A} and {B} stay apart and do not touch each other."),
    ],
}


def render(key, off, keep_name=True):
    """(directive, conflicts) for the parts switched off in `off` ({"A:legs", ...})."""
    out, conflicts = [], []
    for seg in ACT_PARTS[key]:
        kind, parts, text = seg["kind"], seg["parts"], seg["text"]
        gone = bool(parts) and all(p in off for p in parts)
        if kind == "name" and not keep_name:
            continue
        if kind in ("part", "motion") and gone:
            continue
        if kind == "act" and gone:
            text = seg["frame"]
        if kind == "place" and gone:
            conflicts.append(text.strip())
        out.append(text)
    return "".join(out).strip(), conflicts


def checklist(key):
    """Switchable parts per person, in first-seen order: {"A": ["legs", ...], "B": [...]}."""
    out = {}
    for seg in ACT_PARTS[key]:
        if seg["kind"] not in ("part", "motion", "act"):
            continue
        for p in seg["parts"]:
            who, part = p.split(":")
            if part not in out.setdefault(who, []):
                out[who].append(part)
    return out
