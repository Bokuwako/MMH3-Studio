"""Deferred high-resolution finishing.

Draft the whole story at base resolution, then finish it in one go: this
rebuilds every approved clip at final quality, in order, into a companion
project named "<project>-hq". Each clip after the first carries the previous
clip's COMPLETED refine tail, so the join survives the refine pass as well.
Nothing in the draft project is modified.
"""
import asyncio
import copy
import json
from urllib.parse import urlencode

from aiohttp import web

SUFFIX = '-hq'
LEDGER = 'clip_bodies.json'


class JsonBody:
    def __init__(self, body=None, pid=None): self.body = body; self.match_info = {'pid': pid}
    async def json(self): return copy.deepcopy(self.body)


def unpack(response): return json.loads(response.body)


def record(load, save, body, index):
    """Keep the exact render settings of each draft clip, keyed by clip order."""
    name = (body.get('project') or '').strip()
    if not name or name.endswith(SUFFIX) or not isinstance(index, int): return
    ledger = load(LEDGER, {})
    clips = {str(k): v for k, v in ledger.get(name, {}).items()}
    clips[str(index)] = {k: v for k, v in body.items() if not k.startswith('_')}
    ledger[name] = clips
    save(LEDGER, ledger)


def from_jobs(load, name):
    """Clips made before the ledger existed: rebuild their settings from job history.

    Submission order plus the chain flag gives the clip order: a clip with
    chaining off starts the chain again, and the newest job for a slot is the
    take that stands.
    """
    out = {}; index = -1
    for entry in load('jobs.json', {}).values():
        body = (entry.get('settings') or {})
        if entry.get('deleted') or entry.get('state') != 'completed': continue
        if (body.get('project') or '').strip() != name or body.get('maintenance'): continue
        index = index + 1 if body.get('chain') and index >= 0 else 0
        out[index] = {k: v for k, v in body.items() if not k.startswith('_')}
    return out


def install(app, routes, load, save, render, job, cancel, remote, idle):
    state = load('finish.json', {'state': 'idle'})
    if state.get('state') in ('running', 'stopping'):
        state.update(state='interrupted', error='서버가 재시작되어 고화질 마감이 중단되었습니다.')
    task = None; stop = False

    def update(**kw): state.update(kw); save('finish.json', state)

    def bodies(name):
        merged = {int(k): v for k, v in from_jobs(load, name).items()}
        merged.update({int(k): v for k, v in load(LEDGER, {}).get(name, {}).items()})
        return merged

    async def clips_of(name):
        data = await remote('/h3_suite/project/state?' + urlencode({'name': name}))
        return [c for c in data.get('clips', []) if c.get('status') == 'approved']

    async def plan(name):
        if not name or name.endswith(SUFFIX): raise ValueError('마감할 원본 프로젝트를 선택하세요.')
        saved = bodies(name)
        target = name + SUFFIX
        try: done = len(await clips_of(target))
        except Exception: done = 0
        items = [{'index': i, 'basename': c.get('basename'), 'ready': i in saved, 'done': i < done}
                 for i, c in enumerate(await clips_of(name))]
        return {'name': name, 'target': target, 'clips': items,
                'pending': [x for x in items if not x['done']],
                'missing': [x for x in items if not x['ready']]}

    async def runner(name):
        nonlocal stop
        try:
            info = await plan(name); saved = bodies(name); target = info['target']
            if not info['clips']: raise ValueError('승인된 클립이 없습니다.')
            await remote('/h3_suite/project/create', {'name': target})
            update(state='running', name=name, target=target, total=len(info['clips']),
                   completed=len(info['clips']) - len(info['pending']), error='', current=0)
            for item in info['clips']:
                if stop: break
                if item['done']: continue
                if not item['ready']:
                    raise ValueError('%d번 클립은 Studio로 만든 기록이 없어 마감할 수 없습니다. 그 클립만 다시 만들어 주세요.' % (item['index'] + 1))
                body = copy.deepcopy(saved[item['index']])
                # One execution per clip, exactly as the clip was drafted: the
                # refine pass then shares this run's conditioning, model state and
                # mask. Reusing only the stored latent loses all three.
                body.update(project=target, chain=item['index'] > 0, finish='now',
                            candidate_retry=True)
                await idle()
                pid = unpack(await render(JsonBody(body)))['id']
                update(current=item['index'] + 1, prompt_id=pid)
                while True:
                    status = unpack(await job(JsonBody(pid=pid)))
                    if status['state'] == 'completed': break
                    if status['state'] in ('failed', 'cancelled', 'unknown'):
                        raise ValueError('고화질 마감 중단: ' + '; '.join(status.get('errors', [])))
                    if stop:
                        await cancel(JsonBody(pid=pid)); break
                    await asyncio.sleep(2)
                if stop: break
                await remote('/h3_suite/project/approve', {'name': target})
                update(completed=item['index'] + 1, prompt_id=None)
            update(state='stopped' if stop else 'completed', prompt_id=None)
        except asyncio.CancelledError:
            update(state='interrupted'); raise
        except Exception as exc:
            update(state='failed', error=str(exc))

    @routes.get('/api/finish')
    async def status(r):
        name = r.query.get('name', '')
        return web.json_response({'run': state, **(await plan(name) if name else {})})

    @routes.post('/api/finish/start')
    async def start(r):
        nonlocal task, stop
        if task and not task.done(): raise ValueError('이미 고화질 마감 중입니다.')
        name = (await r.json()).get('name', '')
        info = await plan(name)
        if not info['pending']: raise ValueError('마감할 클립이 없습니다.')
        if info['missing']: raise ValueError('마감 기록이 없는 클립이 있습니다: ' + ', '.join(str(x['index'] + 1) for x in info['missing']))
        await idle(); stop = False
        state.clear(); update(state='running', name=name, target=info['target'], total=len(info['clips']), completed=0, error='')
        task = asyncio.create_task(runner(name))
        return web.json_response(state)

    @routes.post('/api/finish/stop')
    async def halt(r):
        nonlocal stop
        stop = True
        if task and not task.done():
            update(state='stopping')
            if state.get('prompt_id'): await cancel(JsonBody(pid=state['prompt_id']))
        return web.json_response(state)

    async def cleanup(app):
        if task and not task.done():
            task.cancel()
            try: await task
            except asyncio.CancelledError: pass
    app.on_cleanup.append(cleanup)
    return lambda: bool(task and not task.done())
