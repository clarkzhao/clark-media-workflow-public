"""Offline reference-conditioned TTS. All inputs/outputs are local paths."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import random
import socket
import time


def dependency_versions(engine):
    packages = ['torch', 'transformers', 'numpy', 'soundfile',
                'voxcpm' if engine == 'voxcpm2' else 'qwen-tts']
    return {name: importlib.metadata.version(name) for name in packages}


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def prepare_jobs(a, p):
    base = a.batch.resolve().parent if a.batch else Path.cwd()
    rows = json.loads(a.batch.read_text(encoding='utf-8-sig')) if a.batch else [
        {'text': str(a.text), 'output': str(a.output)}]
    if not isinstance(rows, list) or not rows:
        p.error('Batch must be a nonempty JSON list of text/output path objects')
    jobs, outputs, inputs = [], set(), {a.reference, a.transcript}
    if a.batch:
        inputs.add(a.batch.resolve())
    for row in rows:
        if not isinstance(row, dict) or not all(isinstance(row.get(k), str) for k in ['text', 'output']):
            p.error('Each job requires text and output paths')
        source = (base / row['text']).resolve(strict=True)
        text = source.read_text(encoding='utf-8-sig').strip()
        output = (base / row['output']).resolve()
        receipt = output.with_suffix('.json')
        if not text or len(text) > 200:
            p.error('Each target requires 1–200 characters')
        if output.suffix.lower() != '.wav' or any(x.exists() or x in outputs for x in [output, receipt]):
            p.error('Outputs and receipts must be new, unique paths')
        outputs.update([output, receipt])
        inputs.add(source)
        jobs.append((source, text, output, receipt))
    manifest = a.batch.resolve().with_suffix('.model.json') if a.batch else None
    if outputs & inputs or any(x == a.model or a.model in x.parents for x in outputs):
        p.error('Outputs must not overwrite inputs or reside inside model directory')
    if manifest and (manifest.exists() or manifest in outputs or manifest in inputs or a.model in manifest.parents):
        p.error('Batch model manifest must be a new path outside model directory')
    return jobs, manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--engine', choices=['voxcpm2', 'qwen3'], required=True)
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--reference', type=Path, required=True)
    p.add_argument('--transcript', type=Path, required=True)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--text', type=Path)
    mode.add_argument('--batch', type=Path, help='Local JSON list of text/output paths')
    p.add_argument('--output', type=Path)
    p.add_argument('--seed', type=int, default=10403)
    p.add_argument('--cfg', type=float, default=2.0)
    p.add_argument('--steps', type=int, default=10)
    a = p.parse_args()
    if bool(a.text) != bool(a.output):
        p.error('--text requires --output; --batch forbids --output')
    if a.cfg <= 0 or a.steps < 1:
        p.error('cfg and steps must be positive')
    for key in ['model', 'reference', 'transcript']:
        setattr(a, key, getattr(a, key).resolve(strict=True))
    if not a.model.is_dir() or a.reference.suffix.lower() not in {'.wav', '.flac'}:
        p.error('Use a local model directory and WAV/FLAC reference')
    prompt = a.transcript.read_text(encoding='utf-8-sig').strip()
    if not prompt:
        p.error('Reference transcript must be nonempty')
    jobs, manifest = prepare_jobs(a, p)
    versions = dependency_versions(a.engine)
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                      HF_HUB_DISABLE_TELEMETRY='1', DO_NOT_TRACK='1',
                      WANDB_MODE='disabled', GRADIO_ANALYTICS_ENABLED='False')

    def deny(*args, **kwargs):
        raise RuntimeError('Network connections disabled in voice inference process')
    socket.socket.connect = deny
    socket.socket.connect_ex = deny
    socket.create_connection = deny
    import numpy as np
    import soundfile as sf
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA required; no silent CPU fallback')
    ref, sr = sf.read(a.reference, dtype='float32', always_2d=True)
    if ref.shape[1] != 1:
        p.error('Prepare a mono reference first')
    if not 3 <= len(ref)/sr <= 30 or not np.isfinite(ref).all() or np.max(np.abs(ref)) < .001:
        p.error('This recipe requires a finite, non-silent 3–30 second reference')
    started = time.time()
    model_hashes = {path.relative_to(a.model).as_posix(): digest(path)
                    for path in sorted(a.model.rglob('*')) if path.is_file()}
    shared = dict(engine=a.engine, model=str(a.model), model_files_sha256=model_hashes,
        reference_sha256=digest(a.reference), transcript_sha256=digest(a.transcript),
        script_sha256=digest(Path(__file__)), versions=versions,
        cuda=torch.version.cuda, gpu=torch.cuda.get_device_name(0))
    if a.engine == 'voxcpm2':
        from voxcpm import VoxCPM
        model = VoxCPM.from_pretrained(str(a.model), load_denoiser=False,
            optimize=False, local_files_only=True, device='cuda')
    else:
        from qwen_tts import Qwen3TTSModel
        model = Qwen3TTSModel.from_pretrained(str(a.model), device_map='cuda:0',
            dtype=torch.bfloat16, attn_implementation='sdpa', local_files_only=True)
    setup_s = time.time() - started
    if manifest:
        manifest.write_text(json.dumps(shared, ensure_ascii=False, indent=2), encoding='utf-8')
        shared = {'model_manifest': str(manifest), 'model_manifest_sha256': digest(manifest)}
    for source, text, output, receipt in jobs:
        random.seed(a.seed)
        np.random.seed(a.seed)
        torch.manual_seed(a.seed)
        torch.cuda.manual_seed_all(a.seed)
        torch.cuda.reset_peak_memory_stats()
        started = time.time()
        with torch.inference_mode():
            if a.engine == 'voxcpm2':
                wave = model.generate(text=text, prompt_wav_path=str(a.reference),
                    prompt_text=prompt, reference_wav_path=str(a.reference),
                    cfg_value=a.cfg, inference_timesteps=a.steps, normalize=False,
                    denoise=False, retry_badcase=False)
                rate = model.tts_model.sample_rate
            else:
                waves, rate = model.generate_voice_clone(text=text, language='Chinese',
                    ref_audio=(ref[:, 0], sr), ref_text=prompt)
                wave = waves[0]
        wave = np.asarray(wave, dtype=np.float32).squeeze()
        if wave.ndim != 1 or not len(wave) or not np.isfinite(wave).all():
            raise RuntimeError('Invalid generated waveform')
        report = dict(shared, text_sha256=digest(source), seed=a.seed,
            cfg=a.cfg if a.engine == 'voxcpm2' else None,
            steps=a.steps if a.engine == 'voxcpm2' else None,
            sample_rate=rate, duration_s=len(wave)/rate,
            setup_s=setup_s, generation_s=time.time()-started,
            peak_allocated_gib=torch.cuda.max_memory_allocated()/2**30,
            python_socket_connect_blocked=True, human_listening_verified=False)
        output.parent.mkdir(parents=True, exist_ok=True)
        sf.write(output, wave, rate, subtype='FLOAT')
        report['output_sha256'] = digest(output)
        receipt.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'output': str(output), 'receipt': str(receipt),
                          'duration_s': report['duration_s']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
