"""Local encoded-video motion screening; residual motion is not semantic proof."""
from pathlib import Path
import math


def probe_motion(path: Path, spec: dict) -> dict:
    """Compare ROI samples after compensating whole-region affine motion.

    window_s and roi (normalized x0,y0,x1,y1) refer to the encoded artifact.
    All thresholds are explicit project configuration. Alignment/decode problems
    yield unknown, never passed. Imports are lazy so core review needs only Python.
    """
    import av
    import cv2
    import numpy as np

    start, end = spec["window_s"]
    x0, y0, x1, y1 = spec["roi"]
    samples = spec["samples"]
    pixel_delta = spec["pixel_delta"]
    minimum = spec["min_changed_fraction"]
    required_pairs = spec["min_pairs"]
    minimum_correlation = spec["min_alignment_correlation"]
    numbers = (start, end, x0, y0, x1, y1, pixel_delta, minimum, minimum_correlation)
    if not all(isinstance(n, (int, float)) and not isinstance(n, bool) and math.isfinite(n) for n in numbers):
        raise ValueError("finite numeric motion configuration required")
    if not (0 <= start < end and 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
        raise ValueError("invalid time window or normalized ROI")
    if not (isinstance(samples, int) and 3 <= samples <= 60 and isinstance(required_pairs, int)
            and 1 <= required_pairs < samples and 0 < pixel_delta < 255
            and 0 < minimum <= 1 and 0 < minimum_correlation <= 1):
        raise ValueError("invalid sample count or motion threshold")
    times = np.linspace(start, end, samples)
    images, actual_times = [], []
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        origin = float((stream.start_time or 0) * stream.time_base)
        for requested in times:
            container.seek(int((origin + requested) / stream.time_base), stream=stream, backward=True)
            found = None
            for frame in container.decode(stream):
                if frame.pts is None:
                    continue
                timestamp = float(frame.pts * frame.time_base) - origin
                if timestamp + 1e-6 >= requested:
                    found = frame.to_ndarray(format="gray")
                    actual_times.append(timestamp)
                    break
            if found is None:
                return dict(status="unknown", reason="requested sample exceeds decoded video", requested_s=float(requested))
            h, w = found.shape
            cropped = found[round(y0*h):round(y1*h), round(x0*w):round(x1*w)]
            if min(cropped.shape) < 64:
                raise ValueError("ROI must be at least 64 pixels on each side")
            scale = min(1, 640 / max(cropped.shape))
            resized = cv2.resize(cropped, (round(cropped.shape[1]*scale), round(cropped.shape[0]*scale)))
            images.append(cv2.GaussianBlur(resized, (0, 0), 1))
    if len(set(actual_times)) != samples:
        return dict(status="unknown", reason="sampling repeatedly selected the same frame")
    comparisons = []
    for a, b in zip(images, images[1:]):
        transform = np.eye(2, 3, dtype=np.float32)
        try:
            correlation, transform = cv2.findTransformECC(
                a, b, transform, cv2.MOTION_AFFINE,
                (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 100, 0.0001), None, 3)
        except cv2.error:
            return dict(status="unknown", reason="affine alignment failed", comparisons=comparisons)
        if not np.isfinite(transform).all() or correlation < minimum_correlation:
            return dict(status="unknown", reason="alignment confidence below configured minimum")
        size = (a.shape[1], a.shape[0])
        flags = cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP
        aligned = cv2.warpAffine(b, transform, size, flags=flags)
        mask = cv2.warpAffine(np.ones_like(b), transform, size,
                             flags=cv2.INTER_NEAREST | cv2.WARP_INVERSE_MAP).astype(bool)
        margin = max(4, round(min(a.shape) * 0.04))
        mask[:margin] = False
        mask[-margin:] = False
        mask[:, :margin] = False
        mask[:, -margin:] = False
        if mask.mean() < 0.65:
            return dict(status="unknown", reason="insufficient aligned overlap")
        residual = np.abs(a.astype(float) - aligned.astype(float))[mask]
        comparisons.append(dict(alignment_correlation=float(correlation),
                                changed_fraction=float((residual > pixel_delta).mean()),
                                mean_residual=float(residual.mean())))
    moving = sum(p["changed_fraction"] >= minimum for p in comparisons)
    return dict(status="passed" if moving >= required_pairs else "failed", comparisons=comparisons,
                moving_pairs=moving, required_pairs=required_pairs, sampled_times_s=actual_times,
                scope="ROI motion screening only; requires continuous semantic review")
