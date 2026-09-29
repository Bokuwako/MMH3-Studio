"""Non-destructive playback edits. Generation state always retains its full tail."""
import json
import hashlib
import math
import subprocess
import tempfile
import uuid
from pathlib import Path


def probe(path):
    p = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)], capture_output=True, text=True, timeout=30)
    if p.returncode:
        raise ValueError('영상 정보를 읽을 수 없습니다.')
    data = json.loads(p.stdout)
    video = next(s for s in data['streams'] if s['codec_type'] == 'video')
    return {'duration': float(data['format']['duration']), 'width': video['width'], 'height': video['height'], 'fps': video.get('avg_frame_rate', '24/1'), 'audio': any(s['codec_type'] == 'audio' for s in data['streams'])}


def interval(start, end, duration):
    start = float(start or 0)
    end = duration if end in (None, '') else float(end)
    if not all(math.isfinite(x) for x in (start, end, duration)) or not 0 <= start < end <= duration + .001:
        raise ValueError('사용 구간은 영상 안에서 시작 < 끝으로 지정하세요.')
    return {'start': start, 'end': min(end, duration)}


def clip_path(project, basename):
    # Accept only a take recorded in the manifest, not arbitrary filesystem input.
    names = {t['basename'] for c in project.clips for t in project.takes_of(c['index'])}
    if basename not in names:
        raise ValueError('프로젝트에 없는 클립입니다.')
    directory = project.locate_pair(basename)
    if directory is None:
        raise ValueError('클립 파일이 없습니다.')
    return Path(directory) / (basename + '.mp4')


def export(project, edits, clips=None, boundary=False):
    clips = project.approved() if clips is None else clips
    if not clips:
        raise ValueError('먼저 사용할 클립 버전을 선택하세요.')
    sources = []
    for c in clips:
        path = clip_path(project, c['basename'])
        meta = probe(path)
        cut = interval(**{k: edits.get(c['basename'], {}).get(k) for k in ('start', 'end')}, duration=meta['duration'])
        sources.append((path, meta, cut))
    if boundary and len(sources)==2:
        sources[0][2]['start']=max(sources[0][2]['start'],sources[0][2]['end']-1)
        sources[1][2]['end']=min(sources[1][2]['end'],sources[1][2]['start']+1)
    first = sources[0][1]
    width, height = first['width'] // 2 * 2, first['height'] // 2 * 2
    fps = first['fps'] if first['fps'] != '0/0' else '24/1'
    destination = Path(project.clips_dir).parent / ('studio_previews' if boundary else 'studio_exports')
    destination.mkdir(exist_ok=True)
    key=json.dumps([(str(path),path.stat().st_mtime_ns,path.stat().st_size,cut) for path,meta,cut in sources],sort_keys=True)
    target = destination / ('edit_' + hashlib.sha256(key.encode()).hexdigest()[:20] + '.mp4')
    if target.is_file():return target
    partial=destination / ('partial_'+uuid.uuid4().hex+'.mp4')
    with tempfile.TemporaryDirectory(prefix='studio-edit-') as work:
        parts = []
        for n, (path, meta, cut) in enumerate(sources):
            part = Path(work) / f'{n:04d}.mp4'
            length = cut['end'] - cut['start']
            command = ['ffmpeg', '-v', 'error', '-nostdin', '-y', '-ss', str(cut['start']), '-i', str(path)]
            if not meta['audio']:
                command += ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
            command += ['-t', str(length), '-map', '0:v:0', '-map', '0:a:0' if meta['audio'] else '1:a:0', '-vf', f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,fps={fps},setsar=1', '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-ar', '48000', '-ac', '2', '-af', 'apad', str(part)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=1800)
            if result.returncode:
                raise ValueError('구간 내보내기 실패: ' + result.stderr[-1000:])
            parts.append(part)
        manifest = Path(work) / 'concat.txt'
        manifest.write_text(''.join("file '" + p.as_posix() + "'\n" for p in parts), encoding='utf-8')
        result = subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-f', 'concat', '-safe', '0', '-i', str(manifest), '-c', 'copy', '-movflags', '+faststart', str(partial)], capture_output=True, text=True, timeout=1800)
        if result.returncode:
            partial.unlink(missing_ok=True)
            raise ValueError('연결 내보내기 실패: ' + result.stderr[-1000:])
        partial.replace(target)
    return target
