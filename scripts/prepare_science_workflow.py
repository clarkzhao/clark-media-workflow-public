"""Prepare the recorded local FLUX recipe offline; never starts or submits a job."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build_graph(prompt, seed, width, height, prefix):
    if not prompt.strip():
        raise ValueError('A visual prompt is required.')
    if not 0 <= seed < 2**64:
        raise ValueError('Seed must be an unsigned 64-bit integer.')
    # This preserved recipe uses a 16-pixel grid, not a universal model claim.
    if any(v <= 0 or v % 16 for v in (width, height)):
        raise ValueError('This recipe requires positive width/height divisible by 16.')
    if not prefix or prefix.startswith(('/', '\\')) or ':' in prefix or '..' in Path(prefix.replace('\\', '/')).parts:
        raise ValueError('Use a relative output prefix without parent traversal.')
    graph = json.loads((ROOT / 'workflows/flux2-klein-science.api.json').read_text(encoding='utf-8'))
    graph['4']['inputs']['text'] = prompt.strip()
    graph['7']['inputs']['noise_seed'] = seed
    for node in ('6', '9'):
        graph[node]['inputs'].update(width=width, height=height)
    graph['13']['inputs']['filename_prefix'] = prefix
    return graph


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prompt-file', type=Path)
    parser.add_argument('--seed', type=int, default=2026100613)
    parser.add_argument('--width', type=int, default=1536)
    parser.add_argument('--height', type=int, default=864)
    parser.add_argument('--prefix', default='science_illustration/run_01')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prompt = args.prompt_file.read_text(encoding='utf-8-sig') if args.prompt_file else json.loads((ROOT/'prompts/science-illustration.json').read_text(encoding='utf-8'))['selected_case_prompt']
    graph = build_graph(prompt, args.seed, args.width, args.height, args.prefix)
    receipt_path = args.output.with_suffix('.recipe.json')
    if args.output.exists() or receipt_path.exists():
        parser.error('Output or recipe receipt exists; choose a new version.')
    data = json.dumps(graph, ensure_ascii=False, indent=2).encode('utf-8')
    receipt = {'state':'prepared_only', 'submitted':False, 'human_accepted':False,
               'graph_sha256':hashlib.sha256(data).hexdigest(),
               'template_sha256':hashlib.sha256((ROOT/'workflows/flux2-klein-science.api.json').read_bytes()).hexdigest(),
               'seed':args.seed, 'size':[args.width,args.height],
               'note':'Validate local node schemas/models and queue before executing. No network or GPU work performed.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('xb') as target:
        target.write(data)
    with receipt_path.open('x', encoding='utf-8') as target:
        json.dump(receipt, target, ensure_ascii=False, indent=2)
    print(args.output)


if __name__ == '__main__':
    main()
