"""Conversational prompt editing with the local Ollama model.

Each turn sends the guideline, the lessons learned while building this project,
the current prompt in full and the recent conversation. The model answers with a
short Korean explanation and, when it changes something, the whole prompt again
between explicit markers. Studio never applies that prompt on its own: the user
presses Apply, and every applied version is kept so any turn can be restored.
"""
import asyncio
import json
import math
import re
import time
import uuid
from pathlib import Path

from aiohttp import web, ClientSession, ClientTimeout

PROMPT_OPEN, PROMPT_CLOSE = '<<<PROMPT', 'PROMPT>>>'
HISTORY_TURNS = 6


def chat_settings(body):
    """Validate chat-only settings; legacy clients retain their previous defaults."""
    raw = body.get('llm')
    source = body if raw is None else raw
    if not isinstance(source, dict):
        raise ValueError('대화 LLM 설정 형식이 잘못되었습니다.')
    model = str(source.get('model') or '').strip()
    if not model:
        raise ValueError('대화 LLM 설정에서 모델을 선택하세요.')

    def number(key, default, low, high, integer=False):
        value = source.get(key, default)
        try:
            n = float(value)
        except (TypeError, ValueError):
            raise ValueError('대화 LLM 설정: ' + key + ' 값이 잘못되었습니다.')
        if isinstance(value, bool) or not math.isfinite(n) or not low <= n <= high or (integer and not n.is_integer()):
            raise ValueError('대화 LLM 설정: ' + key + ' 값이 허용 범위를 벗어났습니다.')
        return int(n) if integer else n

    settings = {'model': model, 'think': source.get('think', False),
                'history_turns': number('history_turns', HISTORY_TURNS, 0, 30, True),
                'options': {'temperature': number('temperature', .3, 0, 2),
                            'num_ctx': number('num_ctx', 25600, 2048, 131072, True),
                            'num_predict': number('num_predict', -1, -1, 32768, True)}}
    if not isinstance(settings['think'], bool):
        raise ValueError('대화 LLM 설정: think 값은 true 또는 false여야 합니다.')
    if settings['options']['num_predict'] == 0:
        raise ValueError('최대 응답 토큰은 -1(제한 없음) 또는 1 이상이어야 합니다.')
    return settings

# Pitfalls found while making real clips. The local model does not diagnose
# these on its own, so they are stated up front.
CHECKLIST = """Known MiniMax H3 pitfalls. Check the prompt against every one of them.
1. A state written in the present tense is drawn immediately and for the whole clip.
   "She sits in the left chair" makes a seated ghost appear even while she is standing.
   Give only positions and ownership in shared blocks ("the left chair belongs to her");
   put postures and changes into the shot text with a timestamp ("At 00:02.000 she sits down").
2. In a Continuum clip after the first, the opening frames are the previous clip's last
   frames (the length is given in the setup below). [Shot 1] must continue that final
   state; any cut goes after that carried span.
3. POV is first-person through the named observer's eyes, at the eye height of their
   actual posture. Gaze is separate. Express head movements as changes of the view.
   Follow shot-local body visibility: Auto uses actual posture/gaze/framing; Show includes
   naturally visible body parts or expressly requested parts, not an obligatory full body;
   Hide frames out the observer's body without erasing their off-screen actions.
   Keep this consistent in subject_definitions, retention_analysis and shot prose. Define
   only visual attributes used in that shot. Preserve identity/outfit needed by other
   externally viewed shots. Omit the observer's face unless an explicitly requested mirror
   or plausible reflection makes it visible; never add a reflection on your own.
   Do not turn a camera-only change into a change of physical pose or gaze.
4. Left and right belong to the shot they are written in. When the camera side changes,
   say who is on whose side and how that places them in this frame.
5. Dialogue must fit the time: Japanese runs about 6-7 morae per second. In 5 seconds
   there is room for about two short lines. Give each line a start time and say that
   nobody speaks afterwards, or the model fills the gap with talk.
6. If two things move (a swaying lantern and a drifting view), give them different axes
   or rhythms, or they read as one motion.
7. Keep every cut time in one place: the [Shot N] header. Never write a second time.
8. When something must be absent (a man who left, empty chairs), state the empty state
   plainly in the shot where it matters, in your own words for that scene.
9. A reference governs only the attributes of its role (face, outfit, whole character).
   For those, say they follow the picture, and describe only the changes the user asked
   for. Do not guess what the picture shows.
10. overall_soundscape holds ambience and physical sounds only. Every voice (lines,
   humming, whispers, murmurs, laughter, breathing) goes on the shot timeline at its time;
   a voice written in the soundscape fills the gaps between lines.
11. Call referenced people by Subject label and role. Use a character's proper name only
   when the user asks for it; names inside spoken lines stay."""

RULES = """You are the prompt editor for MiniMax H3 video prompts, working with the user in a conversation.
Answer in Korean. Be brief: at most six short lines of explanation.
When the user reports a problem, first say in one or two lines what in the prompt causes it.
When you change the prompt, output the WHOLE prompt again, every clip and every section,
between a line containing only <<<PROMPT and a line containing only PROMPT>>>.
Keep everything the user did not ask to change exactly as it is, word for word.
Preserve the existing distribution format and clip count for ordinary edits. An explicit
request to add, remove or reorder clips overrides count preservation. Do not confuse a new
[Shot N] inside one clip with a new clip. When the user asks for a next clip in Continuum:
- Preserve existing clips verbatim unless the user also requests changes to them.
- In List mode, append a standalone --- separator and the complete new clip, including all
  fields required by the current generation mode. The prompt block contains the existing
  clips plus the new clip, not only the addition. Each clip restarts at [Shot 1].
- Use the last existing clip's known ending as the opening state. Each clip has its own
  time origin at 0 seconds; the carried prefix is INSIDE that timeline. Continue ongoing
  motion during the prefix; put NEW events, dialogue and cuts after the actual carried
  duration given below. Use the suggested start only when the user has not specified a
  valid time. Never hardcode 2 seconds or add the previous clips' lengths to timestamps.
- Restate only the known continuity needed for the new clip to stand alone. Do not replay
  the previous events or invent unseen final-frame details. Ask briefly if an essential
  ending state is unknown. A next clip without a requested cut can stay in [Shot 1], with
  an event timestamp after the prefix; do not invent [Shot 2] just to mark a new event.
- Keep the per-clip duration. If the prefix leaves insufficient time, explain the conflict
  rather than shortening supplied dialogue or changing timing/settings silently.
- For Auto, an existing standalone --- list may be extended the same way. For Fixed or
  Timeline, explain that independent clips separated by --- require List mode; do not
  silently convert their format or pretend the production mode has changed.
Report a mismatch between the resulting List clip count and the configured chunks. The
user applies the proposed text; this does not change production settings automatically.
If the user only asks a question, answer it and do not output a prompt block.
After the prompt block, list what you changed as short bullet points."""


def _extract(text):
    """Split a reply into explanation and the full prompt, if one was given."""
    pattern = re.escape(PROMPT_OPEN) + r'\s*\n(.*?)\n\s*' + re.escape(PROMPT_CLOSE)
    match = re.search(pattern, text, re.S)
    if not match:
        return text.strip(), None
    prompt = match.group(1).strip()
    explanation = (text[:match.start()] + '\n' + text[match.end():]).strip()
    return explanation, prompt


def _checks(pack, prompt, duration):
    """Run a few of the pack's validators on each clip; never fail the turn."""
    notes = []
    try:
        from studio_pack.mmh3 import validator as v
    except Exception:
        return notes
    for index, clip in enumerate(prompt.split('\n---\n'), 1):
        for fn in ('check_structure', 'check_dialogue_rate', 'check_camera_vocabulary'):
            check = getattr(v, fn, None)
            if not check:
                continue
            try:
                result = check(clip, duration) if fn == 'check_dialogue_rate' else check(clip)
            except Exception:
                continue
            items = result if isinstance(result, (list, tuple)) else [result] if result else []
            for item in items:
                text = item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)
                if text.strip():
                    notes.append(('클립 %d: ' % index if '---' in prompt else '') + text.strip())
    return notes[:12]


def _setup_text(r, duration, prompt=""):
    """The production settings, read fresh every turn, so advice matches the render."""
    def val(key, default=None):
        v = r.get(key, default)
        return default if v in (None, '') else v
    if val('engine') == 'continuum':
        chunks = int(val('chunks', 1))
        carry = int(val('context_length', 39))
        mode = str(val('prompt_mode', 'List'))
        layout = {'List': 'one prompt per clip, separated by a line containing only ---',
                  'Fixed': 'one prompt reused for every clip',
                  'Timeline': '[start-end] section headers on their own lines',
                  'Auto': 'detected automatically'}.get(mode, mode)
        lines = [
            'Engine: Continuum. Configured generation count: %d clips, each %.1f seconds long.' % (chunks, duration),
            'Current text contains %d non-empty blocks separated by standalone --- lines; this is not the production chunk setting.' % len([x for x in re.split(r'(?m)^\s*---\s*$', prompt) if x.strip()]),
            'Prompt distribution: %s (%s).' % (mode, layout),
            "Every clip after the first opens with %d carried frames at 24 fps: %.6f seconds "
            "inside its own timeline. New events, new dialogue and cuts must start AFTER that span. "
            "Suggested new-event start when no time is requested: %.3f s (only if before clip end). "
            "[Shot 1] begins at 0 in the carried state; ongoing motion continues there."
            % (carry, carry / 24.0, (math.floor(carry / 24.0 * 2) + 1) / 2 if carry else 0),
            'Audio carry-over is %s.' % ('on' if val('audio_continuity', True) else 'off'),
        ]
    else:
        lines = ['Engine: Normal. The prompt is a single clip of %.1f seconds.' % duration]
    lines.append('Generation mode: %s.' % val('mode', 'REF2VA'))
    lines.append('High-resolution finish: %s.' % ('on' if val('finish', 'now') == 'now' else 'off'))
    return '\n'.join(lines)


def install(routes, data_dir, cfg, remote, idle, pack, kill_now):
    folder = Path(data_dir) / 'chats'
    folder.mkdir(exist_ok=True)
    busy = asyncio.Lock()

    def path(cid):
        if not re.fullmatch(r'[0-9a-f]{32}', str(cid)):
            raise ValueError('잘못된 대화 ID입니다.')
        return folder / (cid + '.json')

    def read(cid):
        p = path(cid)
        if not p.is_file():
            raise ValueError('대화를 찾을 수 없습니다.')
        return json.loads(p.read_text(encoding='utf-8'))

    def write(chat):
        chat['updated'] = time.time()
        p = path(chat['id'])
        tmp = p.with_suffix('.tmp')
        tmp.write_text(json.dumps(chat, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(p)

    @routes.get('/api/chats')
    async def chats(r):
        items = []
        for p in folder.glob('*.json'):
            try:
                c = json.loads(p.read_text(encoding='utf-8'))
            except Exception:
                continue
            items.append({'id': c['id'], 'title': c.get('title', ''), 'updated': c.get('updated', 0),
                          'turns': sum(1 for m in c.get('messages', []) if m.get('role') == 'user')})
        items.sort(key=lambda c: c['updated'], reverse=True)
        return web.json_response(items)

    @routes.post('/api/chats')
    async def chat_new(r):
        body = await r.json()
        chat = {'id': uuid.uuid4().hex, 'title': str(body.get('title') or '새 대화')[:60],
                'created': time.time(), 'messages': [], 'versions': []}
        if body.get('prompt'):
            chat['versions'].append({'prompt': body['prompt'], 'at': time.time(), 'label': '시작 프롬프트'})
        write(chat)
        return web.json_response(chat)

    @routes.get('/api/chats/{cid}')
    async def chat_get(r):
        return web.json_response(read(r.match_info['cid']))

    @routes.post('/api/chats/{cid}/rename')
    async def chat_rename(r):
        chat = read(r.match_info['cid'])
        chat['title'] = str((await r.json()).get('title') or chat['title'])[:60]
        write(chat)
        return web.json_response(chat)

    @routes.post('/api/chats/{cid}/delete')
    async def chat_delete(r):
        path(r.match_info['cid']).unlink(missing_ok=True)
        return web.json_response({'deleted': True})

    @routes.post('/api/chats/{cid}/applied')
    async def chat_applied(r):
        """Record that a reply's prompt was applied, so it can be restored later."""
        chat = read(r.match_info['cid'])
        body = await r.json()
        chat['versions'].append({'prompt': body.get('prompt', ''), 'at': time.time(),
                                 'label': str(body.get('label') or '적용')[:60]})
        write(chat)
        return web.json_response(chat)

    @routes.post('/api/chats/{cid}/send')
    async def chat_send(r):
        chat = read(r.match_info['cid'])
        body = await r.json()
        message = str(body.get('message', '')).strip()
        if not message:
            raise ValueError('메시지를 입력하세요.')
        llm = chat_settings(body)
        model = llm['model']
        prompt = str(body.get('prompt') or '').strip()
        duration = float(body.get('duration') or 5)
        system = '\n\n'.join([RULES, CHECKLIST, _setup_text(body.get('render') or {}, duration, prompt)])
        history = []
        recent = chat.get('messages', [])[-llm['history_turns'] * 2:] if llm['history_turns'] else []
        for m in recent:
            # Earlier replies are sent without their prompt block; the current prompt
            # below is the only copy the model should edit.
            content = m.get('content', '')
            if m.get('role') == 'assistant':
                content = _extract(content)[0] or '(프롬프트를 수정했음)'
            history.append({'role': m['role'], 'content': content})
        current = ('Current prompt:\n' + PROMPT_OPEN + '\n' + prompt + '\n' + PROMPT_CLOSE) if prompt \
            else 'There is no prompt yet.'
        messages = [{'role': 'system', 'content': system}] + history + \
                   [{'role': 'user', 'content': current + '\n\nUser request:\n' + message}]

        async with busy:
            await idle()
            # Hand VRAM to Ollama for this turn, as prompt writing already does.
            await kill_now()
            payload = {'model': model, 'messages': messages, 'stream': False,
                       'think': llm['think'],
                       'keep_alive': '10m',
                       'options': llm['options']}
            async with ClientSession(timeout=ClientTimeout(total=900)) as session:
                async with session.post(cfg['ollama_url'].rstrip('/') + '/api/chat', json=payload) as resp:
                    data = await resp.json(content_type=None)
                    if resp.status >= 400 or data.get('error'):
                        raise ValueError('Ollama: ' + str(data.get('error') or resp.status))
        reply = (data.get('message') or {}).get('content', '').strip()
        explanation, new_prompt = _extract(reply)
        notes = await asyncio.to_thread(_checks, pack, new_prompt, duration) if new_prompt else []
        if new_prompt and (body.get('render') or {}).get('engine') == 'continuum':
            render = body.get('render') or {}
            if render.get('prompt_mode', 'List') in ('List', 'Auto'):
                count = len([x for x in re.split(r'(?m)^\s*---\s*$', new_prompt) if x.strip()])
                configured = int(render.get('chunks') or 1)
                if count != configured:
                    notes.append('프롬프트는 %d클립, 제작 설정은 %d클립입니다. 적용 후 제작의 클립 수를 확인하세요. 설정은 자동 변경하지 않습니다.' % (count, configured))


        now = time.time()
        chat['messages'].append({'role': 'user', 'content': message, 'at': now})
        chat['messages'].append({'role': 'assistant', 'content': reply, 'at': now,
                                 'explanation': explanation, 'prompt': new_prompt, 'checks': notes})
        if chat.get('title') in ('', '새 대화'):
            chat['title'] = message[:40]
        write(chat)
        return web.json_response({'explanation': explanation, 'prompt': new_prompt, 'checks': notes,
                                  'chat': chat})
