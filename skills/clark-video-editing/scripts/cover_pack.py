"""Prepare image_gen prompts and package finished covers without altering pixels."""
from pathlib import Path
import argparse, hashlib, html, json, shutil, datetime
from PIL import Image

SKILL = Path(__file__).resolve().parents[1]
RATIOS = ('16:9', '4:3', '3:4', '9:16')

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')

def resolve(value, base):
    path = Path(value).expanduser()
    return (path if path.is_absolute() else base / path).resolve(strict=True)

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def prompts(args):
    out = Path(args.output).resolve()
    if out.exists():
        raise ValueError(f'Output already exists; use a new version: {out}')
    paths = [resolve(x, Path.cwd()) for x in (args.style, args.hero, args.couple)]
    for path in paths:
        with Image.open(path) as im:
            im.verify()
    templates = read(SKILL / 'assets/cover-prompts.json')
    fields = dict(label=args.label, title=args.title, subtitle=args.subtitle,
                  hero_subject=args.hero_subject, composition_notes=args.composition_notes)
    result = {
        'tool_mode': 'built-in image_gen; tool calls performed by the agent',
        'input_roles': [{'role': role, 'path': str(path), 'sha256': digest(path)}
                        for role, path in zip(templates['input_order'], paths)],
        'candidate_prompt': templates['candidate_common'].format(**fields),
        'ratio_prompts': [{'ratio': ratio, 'prompt': templates['variant_common'].format(**fields)
                          + ' ' + templates['layouts'][ratio],
                          'referenced_image_paths': [str(p) for p in paths]}
                         for ratio in RATIOS],
        'wording': {k: fields[k] for k in ('label', 'title', 'subtitle')},
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    save(out, result)
    print(str(out))

def deliver(args):
    config_path = Path(args.config).resolve(strict=True)
    config = read(config_path)
    out = Path(args.out).resolve()
    images = config['images']
    if set(images) != set(RATIOS):
        raise ValueError('Provide exactly 16:9, 4:3, 3:4, 9:16 in images')
    prompt_path = resolve(config['prompt_record'], config_path.parent) if config.get('prompt_record') else None
    if prompt_path:
        read(prompt_path)
    rows = []
    for ratio in RATIOS:
        src = resolve(images[ratio], config_path.parent)
        with Image.open(src) as im:
            width, height = im.size
            fmt = im.format
            im.verify()
        if fmt not in ('PNG', 'JPEG', 'WEBP'):
            raise ValueError(f'Unsupported delivery image format: {src}')
        a, b = map(int, ratio.split(':'))
        error = abs(width * b - height * a)
        exact = error == 0
        if error > max(a, b) or (args.strict_ratio and not exact):
            raise ValueError(f'{ratio} does not match actual {width}x{height}: {src}')
        suffix = {'PNG': '.png', 'JPEG': '.jpg', 'WEBP': '.webp'}[fmt]
        dest = out / ('cover_' + ratio.replace(':', 'x') + suffix)
        rows.append({'ratio': ratio, 'ratio_exact': exact, 'width': width, 'height': height,
                     'source': str(src), 'path': str(dest), 'bytes': src.stat().st_size,
                     'sha256': digest(src), 'filename': dest.name})
    targets = [Path(r['path']) for r in rows] + [out / 'cover_manifest.json', out / 'cover_preview.html']
    if prompt_path:
        targets.append(out / 'cover_prompts.json')
    if any(p.exists() for p in targets):
        raise ValueError('Delivery files already exist; use a new version directory')
    out.mkdir(parents=True, exist_ok=True)
    for row in rows:
        shutil.copy2(row['source'], row['path'])
        if digest(Path(row['path'])) != row['sha256']:
            raise RuntimeError('Copied file hash differs from source')
    if prompt_path:
        shutil.copy2(prompt_path, out / 'cover_prompts.json')
    manifest = {'title': config.get('title', ''), 'selected_candidate': config.get('selected_candidate'),
                'files': rows, 'pixel_changes_applied_by_packager': False,
                'visual_review_not_inferred': True,
                'prompt_record': str(out / 'cover_prompts.json') if prompt_path else None,
                'created_local': datetime.datetime.now().isoformat(timespec='seconds')}
    save(out / 'cover_manifest.json', manifest)
    title = html.escape(str(config.get('title') or '封面'))
    cards = ''.join('<article><h2>' + r['ratio'] + '</h2><a href="' + r['filename']
                    + '" target="_blank"><img src="' + r['filename'] + '"></a><p><a href="'
                    + r['filename'] + '" download>下载原图</a></p></article>' for r in rows)
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'''+title+''' · 四种比例</title><style>body{margin:30px auto;max-width:1600px;padding:0 24px;background:#132730;color:#faf1de;font:18px/1.6 sans-serif}h1{font-size:28px}.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:30px}article{padding:18px;background:#1d3640;border-radius:12px}img{display:block;max-width:100%;max-height:820px;margin:auto}h2{margin:0 0 18px;font-size:23px}a{color:#bae4e8}@media(max-width:750px){.grid{grid-template-columns:1fr}}</style><h1>'''+title+''' · 四种比例</h1><div class="grid">'''+cards+'''</div></html>'''
    (out / 'cover_preview.html').write_text(page, encoding='utf8')
    print(str(out / 'cover_preview.html'))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prompt = sub.add_parser('prompts', help='Write parameterized image_gen prompt set')
    for flag in ('label', 'title', 'subtitle', 'hero-subject', 'style', 'hero', 'couple', 'output'):
        prompt.add_argument('--' + flag, required=True)
    prompt.add_argument('--composition-notes', default='')
    prompt.set_defaults(run=prompts)
    pack = sub.add_parser('deliver', help='Copy and validate four finished image formats')
    pack.add_argument('--config', required=True)
    pack.add_argument('--out', required=True)
    pack.add_argument('--strict-ratio', action='store_true')
    pack.set_defaults(run=deliver)
    args = parser.parse_args()
    try:
        args.run(args)
    except (ValueError, KeyError, OSError) as exc:
        parser.exit(2, f'{exc}\n')

if __name__ == '__main__':
    main()
