"""Build a tiny synthetic revision. No private media, models or network access."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from media_review import review


def build_demo(root: Path) -> dict:
    root.mkdir(parents=True, exist_ok=False)

    def write(name, text):
        path = root / name
        path.write_text(text, encoding="utf-8")
        return dict(path=name, sha256=hashlib.sha256(path.read_bytes()).hexdigest())

    source = write("synthetic-results.json", json.dumps({"a_s": 90, "b_s": 30}))
    style = write("presentation.json", json.dumps({"unit": "min", "decimals": 1}))
    chart = write("chart.svg", '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="240">'
                  '<rect width="640" height="240" fill="#09121b"/>'
                  '<g fill="#eeeeee" font-family="sans-serif" font-size="24">'
                  '<text x="24" y="40">Synthetic fixture — not experimental results</text>'
                  '<text x="24" y="110">A: 1.5 min</text><text x="24" y="180">B: 0.5 min</text>'
                  '</g></svg>')
    caption = write("captions.txt", "Synthetic fixture: A 1.5 min; B 0.5 min.\n")
    preview = write("preview.html", '<!doctype html><meta charset="utf-8"><title>Synthetic review fixture</title>'
                    '<h1>Synthetic review fixture</h1><img src="chart.svg" alt="A 1.5 min, B 0.5 min">')
    for item in (chart, caption):
        item["depends_on"] = {"results": source["sha256"], "style": style["sha256"]}
    preview["depends_on"] = {"chart": chart["sha256"]}
    manifest = dict(
        schema_version=1, revision="synthetic-demo-1",
        inputs={"results": source, "style": style},
        artifacts={"chart": chart, "captions": caption, "preview": preview},
        experiments={"demo": dict(input="results", kind="sample", metric="illustrative duration",
                                  population="no real subjects", conditions="synthetic fixture only",
                                  method="hand-authored test values, not a scientific estimate",
                                  unit="s", display_unit="min", decimals=1)},
        facts={"A": dict(experiment="demo", pointer="/a_s"), "B": dict(experiment="demo", pointer="/b_s")},
        bindings=[dict(artifact=a, fact=f, value=v, unit="min")
                  for a in ("chart", "captions") for f, v in (("A", "1.5"), ("B", "0.5"))],
        decisions=[dict(id="units", instruction="Use minutes in both chart and captions", scope="demo only",
                        targets=["chart", "captions"], applied={"chart": chart["sha256"], "captions": caption["sha256"]})],
        scenes=[dict(id="diagram", artifact="chart", media_kind="still", motion_required=False,
                     static_reason="This fixture intentionally demonstrates a static figure")],
        reviews=[], required_reviews=[])
    (root / "revision.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="New local directory")
    args = parser.parse_args()
    manifest = build_demo(args.out)
    report = review(manifest, args.out)
    (args.out / "review.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(dict(manifest=str((args.out / 'revision.json').resolve()),
                          automated_status=report['automated_status'], coverage=report['coverage']), indent=2))
