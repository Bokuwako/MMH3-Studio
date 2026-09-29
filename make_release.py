"""Build the public MMH3 Studio folder: code only, no models, assets or work data.

Copies an explicit allow-list into ../MMH3-Studio-release (its .git is kept), blanks the
model choices in the workflow templates, and refuses to finish if anything personal or
any media file slipped in. Run it before every push:

    python make_release.py
"""
import json
import os
import re
import shutil
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
DEST = SRC.parent / 'MMH3-Studio-release'
COMFY = Path(os.environ.get('MMH3_COMFY') or SRC.parent / 'ComfyUI_windows_portable_nvidia/ComfyUI_windows_portable/ComfyUI')
NODES = COMFY / 'custom_nodes' / 'ComfyUI-MMH3-Studio-Nodes'

ROOT_FILES = ['start.cmd', 'README.ko.md']
# Leftovers from the first template format; nothing imports them any more.
DEAD = {'comfy_client.py', 'make_workflow.py'}
TEMPLATES = ['current.json']
WEB_TYPES = {'.js', '.css', '.html', '.json'}
# Model choices are the user's own; the recipient picks theirs in Studio settings.
SCRUB = {
    'UNETLoader': ['unet_name'],
    'CLIPLoader': ['clip_name'],
    'VAELoader': ['vae_name'],
    'LoraLoaderModelOnly': ['lora_name'],
    'MMH3_PromptFreeze': ['revise_model'],
}
FORBIDDEN = re.compile(r'kmlee|orcarouter|Uncensored|DasiwaMinimaxH3_|@gmail\.com|C:[/\\]+Users', re.I)
MEDIA = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.mp4', '.webm', '.mov', '.wav', '.mp3', '.flac',
         '.safetensors', '.ckpt', '.pt', '.pth', '.gguf', '.bin', '.onnx'}


def skip(path):
    name = path.name
    return '__pycache__' in path.parts or '.bak' in name or name.endswith('.log')


def copy(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def main():
    DEST.mkdir(exist_ok=True)
    for item in DEST.iterdir():
        if item.name != '.git':
            shutil.rmtree(item) if item.is_dir() else item.unlink()

    for path in SRC.glob('*.py'):
        if path.name not in DEAD:
            copy(path, DEST / path.name)
    for name in ROOT_FILES:
        copy(SRC / name, DEST / name)
    for path in (SRC / 'web').rglob('*'):
        if path.is_file() and path.suffix in WEB_TYPES and not skip(path):
            copy(path, DEST / path.relative_to(SRC))
    for path in (SRC / 'workflows' / name for name in TEMPLATES):
        graph = json.loads(path.read_text(encoding='utf-8'))
        for node in graph.values():
            if isinstance(node, dict):
                for key in SCRUB.get(node.get('class_type'), []):
                    if key in node.get('inputs', {}):
                        node['inputs'][key] = ''
        out = DEST / 'workflows' / path.name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding='utf-8')
    for path in NODES.rglob('*'):
        if path.is_file() and not skip(path):
            copy(path, DEST / 'custom_nodes' / NODES.name / path.relative_to(NODES))

    release = SRC / 'release'
    for name in ('README.md', 'LICENSE', 'install.cmd'):
        copy(release / name, DEST / name)
    copy(release / 'gitignore', DEST / '.gitignore')
    # Windows PowerShell 5.1 reads a script without a BOM as the ANSI code page.
    text = (release / 'install.ps1').read_text(encoding='utf-8')
    (DEST / 'install.ps1').write_text(text, encoding='utf-8-sig')
    for path in DEST.glob('*.cmd'):
        path.write_bytes(path.read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))

    problems = []
    for path in DEST.rglob('*'):
        if not path.is_file() or '.git' in path.relative_to(DEST).parts:
            continue
        rel = path.relative_to(DEST)
        if path.suffix.lower() in MEDIA:
            problems.append('%s: media or model file' % rel)
        elif path.stat().st_size > 2_000_000:
            problems.append('%s: larger than 2 MB' % rel)
        else:
            text = path.read_text(encoding='utf-8', errors='ignore')
            for match in FORBIDDEN.finditer(text):
                if path.name == 'make_release.py':
                    break
                problems.append('%s: contains %r' % (rel, match.group(0)))
    if problems:
        print('RELEASE BLOCKED:')
        for line in problems:
            print('  ' + line)
        sys.exit(1)
    files = [p for p in DEST.rglob('*') if p.is_file() and '.git' not in p.relative_to(DEST).parts]
    print('release ready: %s (%d files, %.1f KB)' % (DEST, len(files), sum(p.stat().st_size for p in files) / 1024))


if __name__ == '__main__':
    main()
