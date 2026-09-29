"""Studio's revisions of the PromptDirector writer rules and brief builders.

The pack files stay untouched. pack_bridge loads the pack as `studio_pack` and calls
apply() once; that swaps rule text on the loaded modules and wraps the brief builders
that changed. Revision proposal v3: A1 reference scope and names, A2 POV, A3 voices out
of the soundscape, B1 jump cut, B2 stale checklist reference. Also the act-part
checklist: act rows drop the clauses about parts the shot card switched off.

Every text swap names the exact upstream text it replaces. When the pack changes that
text, the swap is skipped and reported instead of guessed.
"""
import threading

import act_parts
from studio_pack.mmh3 import acts, guideline, shotcards, shotlist

_misses = []
# Notes from the act filter for the brief being built; shotcards.build runs one per thread.
_shot = threading.local()


def _swap(text, old, new, where):
    if old not in text:
        _misses.append(where)
        return text
    return text.replace(old, new)


def _row(rows, key, index, old, new, where):
    for i, row in enumerate(rows):
        if row[0] == key:
            rows[i] = row[:index] + (_swap(row[index], old, new, where),) + row[index + 1:]
            return
    _misses.append(where)


# ---------------------------------------------------------------- guideline

JUMP_RULE = """
For a requested jump cut, use the shot cuts to and state that the camera, framing and
background stay exactly the same while the change happens instantly."""

SOUNDSCAPE_OLD = """overall_soundscape: 1-4 English sentences describing ambience, physical sounds and
nonverbal human sounds. Put dialogue, singing and in-world music on the shot timeline.
Use N/A for requested silence or a disabled soundscape setting."""

SOUNDSCAPE_NEW = """overall_soundscape: 1-4 English sentences describing ambience and physical sounds only.
Every human voice, including dialogue, singing, humming, whispers, murmurs, laughter and
breathing, goes on the shot timeline at the moment it occurs, and in-world music does too.
Include background voices such as a crowd only when the brief asks for them.
Use N/A for requested silence or a disabled soundscape setting."""

OPERATOR_OLD = """For POV, the lens represents the named observer's eyes. Establish what they see using
explicit gaze, camera targets and scene geometry. POV alone does not request eye-level
framing, a horizontal gaze or a head turn. Do not add those as defaults. Show the observer's
own body only where it enters their view; retain explicitly requested reflections."""

OPERATOR_NEW = """For POV, the lens is the named observer's eyes, placed at the eye height of the observer's
actual posture (seated, lying, kneeling, standing). Gaze direction is a separate setting;
when it is unspecified, add no level gaze or head turn. Establish what they see using
explicit gaze, camera targets and scene geometry. Write the observer's head and eye
movements as movements of the view (the view tilts down to, the view turns toward) rather
than as actions of a visible person. The observer's own body appears where their posture
and gaze put it in view; retain explicitly requested reflections."""

POV_DEFINITION_OLD = "For a POV person define only content applicable to their actual visible parts across shots."

POV_DEFINITION_NEW = """For a POV person, identify whose eyes supply the view and which shots use that POV.
Follow each shot's POV body-visibility choice in subject_definitions, retention_analysis
and shot prose together. Auto: describe only body parts naturally visible from posture,
gaze and framing. Show: include naturally visible parts, or the parts explicitly requested;
do not force a full-body view. Hide: frame the view without the observer's own body while
preserving their physical pose and actions; off-screen action can still occur.
Omit the observer's face description unless the user explicitly requests a visible face
through a mirror or another plausible reflection. Do not invent a reflection to show it.
Define and retain only the visual attributes actually used in those shots, within the
reference's assigned role. A hidden observer may still need a label for viewpoint or speech;
do not invent visible identity or outfit retention just to fill the section.
If other shots show that person externally, keep their relevant identity and outfit there:
a POV shot's visibility choice does not delete definitions needed by other shots.
Refer to referenced people by their Subject label and role (the male character, the
female character). Names typed in the brief only identify who is who; write a character's
proper name in the prompt only when the must-happen list asks for it. Names inside spoken
lines stay as written."""

DESCRIPTION_OLD = """DESCRIPTION
At first appearance, describe important identifying features, position and current action
within the actual view. Later shots use stable labels plus relevant visible details and
changes. Recompute framing from each shot's camera. A reference's framing applies only if
its assigned role is a frame or composition anchor at that point."""

DESCRIPTION_NEW = """DESCRIPTION
For each attribute a reference is assigned to govern, subject_definitions states that the
attribute follows that picture, within that role's scope only: a face reference covers the
face, a full-character reference covers face, hair, body and outfit, an outfit reference
covers clothing. Describe in the shots only the changes the brief requests to those
attributes. Attributes that no assigned role covers come from the brief. An image inventory,
when supplied, may add confirmed features inside a picture's role that matter in that shot.
At first appearance, give each person's position and current action within the actual view.
Later shots use stable labels plus relevant visible changes. Recompute framing from each
shot's camera. A reference's framing applies only if its assigned role is a frame or
composition anchor at that point."""


def _guideline():
    rules = guideline.BASE_RULES
    rules = _swap(rules, "prefer continuous action rather than inventing extra shots.",
                  "prefer continuous action rather than inventing extra shots." + JUMP_RULE,
                  "guideline.BASE_RULES SHOTS")
    guideline.BASE_RULES = _swap(rules, SOUNDSCAPE_OLD, SOUNDSCAPE_NEW, "guideline.BASE_RULES AUDIO FIELDS")
    guideline.CONSTRAINT_OPERATOR = _swap(guideline.CONSTRAINT_OPERATOR, OPERATOR_OLD, OPERATOR_NEW,
                                          "guideline.CONSTRAINT_OPERATOR")
    guideline.CONSTRAINT_VIEWPOINT = _swap(
        guideline.CONSTRAINT_VIEWPOINT,
        "Do not add an eye-level angle or horizontal gaze merely because the shot is POV.",
        "In a POV shot the camera height follows the observer's posture; add no level gaze or head\n"
        "turn that the brief did not request.",
        "guideline.CONSTRAINT_VIEWPOINT")
    guideline.CONSTRAINT_NONVERBAL = _swap(
        guideline.CONSTRAINT_NONVERBAL,
        "timeline, with a stable speaker ID. The soundscape may summarize them.",
        "timeline, with a stable speaker ID, at the moment they occur. Keep them out of\n"
        "overall_soundscape.",
        "guideline.CONSTRAINT_NONVERBAL")
    block = guideline.MODE_BLOCKS["REF2VA"]
    block = _swap(block, POV_DEFINITION_OLD, POV_DEFINITION_NEW, "guideline REF2VA POV definition")
    guideline.MODE_BLOCKS["REF2VA"] = _swap(block, DESCRIPTION_OLD, DESCRIPTION_NEW, "guideline REF2VA DESCRIPTION")


# ---------------------------------------------------------------- brief

POV_TIP = ("이 이미지 인물의 정체성과 의상을 참조한다. "
           "POV의 자기 시야 또는 어깨너머의 전경 가시성은 해당 시점을 쓰는 샷에만 적용한다. "
           "다른 샷에서는 그 샷의 카메라에 보이는 얼굴과 신체를 정상적으로 서술한다.")

POV_TIP_EXTRA = (" POV 샷에서는 자기 몸 표시 선택과 실제 시야에 맞는 특징만 쓴다. "
                 "자기 얼굴 묘사는 명시적으로 요청한 거울·반사 등으로 보이는 경우에만 허용한다. "
                 "subject_definitions·retention_analysis도 같은 가시 범위를 따르며, "
                 "다른 샷에서 필요한 정체성·의상 정보는 유지한다.")

POV_ONLY_TIP = ("모든 샷이 이 인물의 1인칭 시점이다. 출처 이미지와 시점 주인을 식별하되, "
                "각 샷의 자기 몸 표시 선택에 따라 실제로 보이는 특징·의상만 참조한다. "
                "몸이 전혀 보이지 않으면 불필요한 외형·의상 보존 문장을 만들지 않는다. "
                "자기 얼굴은 명시적으로 요청한 반사 등에서 실제로 보일 때만 묘사한다. "
                "subject_definitions·retention_analysis와 본문에 동일하게 적용한다.")


def pov_body_directive(card):
    if card.get("viewpoint") != "pov":
        return ""
    choice = card.get("pov_body") or "auto"
    modes = {
        "auto": "자동 — 자세·시선·프레이밍상 실제로 보이는 자기 신체만 묘사한다. 표시나 숨김을 강제하지 않는다.",
        "show": "표시 — 시야에 자연스럽게 들어오는 자기 신체를 묘사한다. 사용자가 보일 부위를 지정하면 그 범위를 따른다. 전신을 억지로 넣거나 몸을 보이려고 자세·시선을 바꾸지 않는다.",
        "hide": "숨김 — 자기 몸이 프레임에 들어오지 않는 시야로 작성한다. 실제 자세·행동은 유지하며 화면 밖에서 진행할 수 있다. 선택한 앵글이나 필수 동작과 양립 불가능하면 충돌로 알린다.",
    }
    if choice not in modes:
        raise ValueError("POV 자기 몸 표시 선택이 잘못되었습니다.")
    return (" POV 자기 몸: " + modes[choice] +
            " 이 선택은 이 샷의 시점 주인에게만 적용한다. 자기 얼굴은 명시적으로 요청한 반사 등에서 "
            "실제로 보일 때만 묘사한다. subject_definitions·retention_analysis·샷 본문에 일관되게 "
            "적용하고, 다른 샷에서 이 인물이 외부 시점으로 보일 때 필요한 외형 정보는 유지한다.")

POV_CAMERA_OLD = ("POV identifies the observer only. Unspecified angle and gaze remain unspecified "
                  "rather than being filled with defaults")
# The VIEWPOINT row above already places the lens at the posture's eye height.
POV_CAMERA_NEW = "Unspecified gaze direction remains unspecified rather than being filled with defaults"

LAST_LINE = "마지막 대사 뒤에는 브리프가 요청한 발성(웃음·노래·숨소리 등)만 있고, 새로 지어낸 말은 없다."

JUMP_CONTINUITY = ("점프컷: 샷 {}의 카메라 위치·구도·배경·조명·인물의 외형과 의상을 그대로 이어받는다. "
                   "인물의 위치와 자세만 이 샷의 내용과 행위가 정한 상태로 컷 순간에 바뀐다. 본문에 "
                   "'The camera, framing and background stay exactly the same' 과 'instantly' 를 적는다.")

CAMERA_FIELDS = ("viewpoint", "angle", "facing", "size", "shot_type", "motion")


def _brief():
    s = shotcards
    _row(s.VIEWPOINT, "pov", 3, "a first-person POV through {who}'s own eyes",
         "a first-person POV through {who}'s own eyes, at the eye height of {who}'s actual posture",
         "shotcards.VIEWPOINT pov")
    _row(s.REF_ROLE, "character_full", 2, "옷을 하나하나 묘사하라.",
         "subject_definitions 에는 외형과 의상이 이 이미지를 따른다고 적고, 본문에는 브리프가 요청한 변화만 적어라.",
         "shotcards.REF_ROLE character_full")
    if not any(row[0] == "jump" for row in s.TRANSITION):
        s.TRANSITION.append(("jump", "점프컷", "카메라·구도·배경은 그대로 두고 인물의 위치나 자세만 순간적으로 바뀝니다.",
                             "the shot cuts to"))
    s.TABLES.update(viewpoint=s._table(s.VIEWPOINT), ref_role=s._table(s.REF_ROLE),
                    transition=s._table(s.TRANSITION))
    s.ROLE_EXCLUDE["face"] = _swap(s.ROLE_EXCLUDE["face"], "체형 체크리스트는 이 이미지에 적용되지 않는다. ", "",
                                   "shotcards.ROLE_EXCLUDE face")
    _row(shotlist.POV_MODE, "pov", 2,
         "First-person POV: the camera represents the specified character's eyes. "
         "Angle and gaze are separate choices; do not default to eye-level framing "
         "or a horizontal gaze. Show only what enters that view, including visible "
         "body parts or explicitly requested reflections.",
         "First-person POV: the camera is the specified character's eyes, at the eye height of that "
         "character's actual posture. Gaze direction is a separate choice. Show only what enters that "
         "view, including the character's own body where posture and gaze put it in view, or "
         "explicitly requested reflections.",
         "shotlist.POV_MODE pov")

    camera_sentence, refs_block = s.camera_sentence, s.refs_block
    dialogue_block, continuity_line = s.dialogue_block, s.continuity_line
    recompose_line, build = s.recompose_line, s.build

    def pov_camera_sentence(card, who, frame_anchored=False):
        return camera_sentence(card, who, frame_anchored).replace(POV_CAMERA_OLD, POV_CAMERA_NEW) + pov_body_directive(card)

    def pov_refs_block(refs, cards=None):
        text, axes = refs_block(refs, cards)
        text = "\n".join(line.replace("정체성과 의상 참조는 유지하되", "정체성 참조는 유지하되") if "이 이미지에서 의상은 가져오지 마라." in line else line for line in text.split("\n"))
        for r in refs or []:
            n = r.get("n")
            if (r.get("role") or "").strip() != "pov_self" or n in (None, ""):
                continue
            pov = [c for c in cards or [] if c.get("viewpoint") == "pov" and c.get("vp_target") == "pic:{}".format(n)]
            tip = POV_ONLY_TIP if cards and len(pov) == len(cards) else POV_TIP + POV_TIP_EXTRA
            head = "- 이미지 {}: {} — ".format(n, s.ko("ref_role", "pov_self"))
            text = text.replace(head + POV_TIP, head + tip)
        return text, axes

    def voiced_dialogue_block(card, language="Korean"):
        text = dialogue_block(card, language)
        return text + "\n" + LAST_LINE if text else text

    def jump_continuity_line(card, n):
        if (card or {}).get("transition") == "jump":
            return JUMP_CONTINUITY.format(n - 1)
        return continuity_line(card, n)

    def jump_recompose_line(card, n, refs=None):
        if card.get("transition") == "jump":
            return ""
        return recompose_line(card, n, refs)

    def checked_build(cards, *args, **kwargs):
        for n, c in enumerate(cards or [], start=1):
            if n == 1 or not isinstance(c, dict) or c.get("transition") != "jump":
                continue
            if c.get("link") in ("new_scene", "same_moment"):
                raise ValueError("샷 {}: 점프컷은 '새 장면'이나 '같은 순간'과 함께 쓸 수 없습니다. 연결을 기본값으로 두세요.".format(n))
            if any(c.get(k) for k in CAMERA_FIELDS):
                raise ValueError("샷 {}: 점프컷은 앞 샷의 카메라를 그대로 씁니다. 이 샷의 카메라 설정을 비우세요.".format(n))
        _shot.n, _shot.notes = 0, []
        body, axes, problems = build(cards, *args, **kwargs)
        return body, axes, list(problems) + _shot.notes

    s.camera_sentence = pov_camera_sentence
    s.refs_block = pov_refs_block
    s.dialogue_block = voiced_dialogue_block
    s.continuity_line = jump_continuity_line
    s.recompose_line = jump_recompose_line
    s.build = checked_build


# ---------------------------------------------------------------- act parts

FRAME_EDGE = ("화면 경계: {} 은(는) 이 샷의 프레임 밖이다. 본문에 이 부위를 적지 말고, "
              "프레임이 실제로 담는 범위만 긍정형으로 적어라.")


def _act_parts():
    """Filter each act row's directive by the parts the shot card switched off.

    A row carries `off` (["A:legs", ...]) and `keep_name` from the Studio checklist. The
    filtered directive goes in under a temporary act key for this one act_block call, so
    act_block's own formatting, mover override and name rule all apply unchanged.
    """
    act_block = acts.act_block

    def framed_act_block(card, label_fn, pov_target=None):
        _shot.n = getattr(_shot, "n", 0) + 1
        notes = getattr(_shot, "notes", [])
        rows, temp, hidden = [], [], []
        for index, row in enumerate(card.get("acts") or []):
            key = (row.get("act") or "").strip() if isinstance(row, dict) else ""
            off = {p for p in (row.get("off") or []) if isinstance(p, str)} if key else set()
            keep_name = row.get("keep_name") is not False if key else True
            if key not in act_parts.ACT_PARTS or (not off and keep_name):
                rows.append(row)
                continue
            text, conflicts = act_parts.render(key, off, keep_name)
            name = "{}~studio{}".format(key, index)
            base = acts._ACT[key]
            acts._ACT[name] = base[:3] + (text,) + base[4:]
            acts.ACT_NAMES[name] = acts.ACT_NAMES[key] if keep_name else ""
            temp.append(name)
            rows.append(dict(row, act=name))
            people = {"A": row.get("a"), "B": row.get("b")}
            gone = []
            for tag in sorted(off):
                slot, part = tag.split(":", 1)
                if people.get(slot) and part in act_parts.PARTS:
                    gone.append("<{}>의 {}".format(label_fn(people[slot]), act_parts.PARTS[part]))
            hidden += gone
            label = base[1]
            if gone:
                notes.append("샷 {}: {} — 화면 밖으로 뺀 부위: {}".format(_shot.n, label, ", ".join(gone)))
            if not keep_name:
                notes.append("샷 {}: {} — 행위 이름 제외".format(_shot.n, label))
            for text in conflicts:
                notes.append("샷 {}: {} — 위치 구절의 부위가 모두 꺼져 있어 성립하기 어렵습니다: {}".format(_shot.n, label, text))
        if not temp:
            return act_block(card, label_fn, pov_target)
        try:
            text = act_block(dict(card, acts=rows), label_fn, pov_target)
        finally:
            for name in temp:
                acts._ACT.pop(name, None)
                acts.ACT_NAMES.pop(name, None)
        if hidden:
            text += "\n" + FRAME_EDGE.format(", ".join(hidden))
        return text

    acts.act_block = framed_act_block


def apply():
    """Install the revisions once; return the swaps skipped because the pack text changed."""
    if getattr(shotcards, "_studio_overrides", False):
        return []
    _guideline()
    _brief()
    _act_parts()
    shotcards._studio_overrides = True
    return list(_misses)
