"""Command-line entry point: ``uv run tour <command>``."""

from __future__ import annotations

import argparse
import base64
import json
import re
import shutil
import sys
from pathlib import Path

from . import config, eleven, master, publish, render
from . import route as route_tools
from .script import Problem, check_file, load_tracks
from .spend import Guard, read_ledger

WORDS_PER_MINUTE = 130
DEFAULT_MODEL = "eleven_v4"


def cmd_estimate(args: argparse.Namespace) -> None:
    """Character counts per track, so every paid step can be priced first."""
    tour = config.tour(args.tour, args.draft)
    tracks = load_tracks(tour.draft)
    total_chars = 0
    print(f"{'track':<10} {'words':>6} {'chars':>7} {'pause s':>8} {'~min':>6}  title")
    for t in tracks:
        minutes = t.word_count / WORDS_PER_MINUTE + t.pause_seconds / 60
        total_chars += t.char_count
        print(
            f"{t.id:<10} {t.word_count:>6} {t.char_count:>7} {t.pause_seconds:>8.0f}"
            f" {minutes:>6.1f}  {t.title}"
        )
    print(f"{'total':<10} {'':>6} {total_chars:>7}")
    if args.verbose:
        for t in tracks:
            print(f"\n=== {t.id}: {t.title} ===")
            for seg in t.segments:
                print(f"  {seg}")
    errors = sum(p.error for p in check_file(tour.draft, tour.settings))
    if errors:
        print(f"\n{errors} script error(s); see `tour check {tour.slug}`", file=sys.stderr)


def cmd_check(args: argparse.Namespace) -> None:
    """Report everything in the draft that breaks docs/script-format.md; exit 1 on errors."""
    tour = config.tour(args.tour, args.draft)
    problems = check_file(tour.draft, tour.settings)
    for t in load_tracks(tour.draft):
        problems += [Problem(t.line, msg) for msg in render.retired(tour, t)]
    problems.sort(key=lambda p: p.line)
    path = tour.draft.relative_to(config.REPO_ROOT)
    for p in problems:
        where = f"{path}:{p.line}" if p.line else str(path)
        print(f"{where}: {'error' if p.error else 'warning'}: {p.message}")
    errors = sum(p.error for p in problems)
    tracks = load_tracks(tour.draft)
    print(f"{len(tracks)} tracks, {errors} errors, {len(problems) - errors} warnings")
    if errors:
        sys.exit(1)


def cmd_account(_: argparse.Namespace) -> None:
    sub = eleven.subscription()
    used, limit = sub.get("character_count"), sub.get("character_limit")
    print(f"tier:    {sub.get('tier')}")
    print(f"credits: {used:,} used of {limit:,} this period ({limit - used:,} left)")
    reset = sub.get("next_character_count_reset_unix")
    if reset:
        from datetime import datetime

        print(f"resets:  {datetime.fromtimestamp(reset):%Y-%m-%d %H:%M}")


def cmd_models(_: argparse.Namespace) -> None:
    for m in eleven.models():
        print(f"{m['model_id']:<32} {m.get('name', '')}")


def cmd_voices(args: argparse.Namespace) -> None:
    for v in eleven.voices(args.search):
        labels = ", ".join(f"{k}={val}" for k, val in (v.get("labels") or {}).items())
        print(f"{v['voice_id']}  {v['name']:<28} {v.get('category', ''):<10} {labels}")
        if args.previews and v.get("preview_url"):
            print(f"    preview: {v['preview_url']}")


def passage(tour: config.Tour, track_id: str, paragraphs: int) -> str:
    tracks = {t.id: t for t in load_tracks(tour.draft)}
    if track_id not in tracks:
        raise SystemExit(f"No track {track_id}; known: {', '.join(tracks)}")
    return "\n\n".join(tracks[track_id].paragraphs[:paragraphs])


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def cmd_audition(args: argparse.Namespace) -> None:
    """Render the same passage (or test sentence) with several voices into build/auditions/."""
    tour = config.tour(args.tour)
    text = args.text or passage(tour, args.track, args.paragraphs)
    stem = f"say-{slug(args.text)[:40]}" if args.text else args.track
    voices = [v.split("=", 1) for v in args.voice]
    guard = Guard(tour, max_chars=args.max_chars, assume_yes=args.yes)
    guard.approve(f"audition total ({len(voices)} voices)", len(text) * len(voices))
    guard.assume_yes = True  # the batch was approved as a whole above
    out_dir = tour.build / "auditions"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, voice_id in voices:
        request = {"kind": "tts", "text": text, "voice_id": voice_id, "model_id": args.model}
        path, _ = guard.run(
            f"audition {name}",
            request,
            len(text),
            lambda: eleven.tts(text, voice_id, args.model),
        )
        out = out_dir / f"{stem}-{slug(name)}-{args.model}.mp3"
        shutil.copyfile(path, out)
        print(f"  -> {out.relative_to(config.REPO_ROOT)}")


def cmd_design(args: argparse.Namespace) -> None:
    """Voice Design previews reading a script passage; saves MP3s, not voices."""
    tour = config.tour(args.tour)
    text = args.text or passage(tour, args.track, args.paragraphs)
    if not 100 <= len(text) <= 1000:
        raise SystemExit(f"Preview text must be 100-1000 chars; got {len(text)}.")
    guard = Guard(tour, max_chars=args.max_chars, assume_yes=args.yes)
    request = {
        "kind": "design",
        "description": args.description,
        "text": text,
        "model_id": args.model,
        "seed": args.seed,
    }

    def call() -> tuple[bytes, dict]:
        result, meta = eleven.design_voice(args.description, text, args.model, args.seed)
        return json.dumps(result).encode(), meta

    path, _ = guard.run(f"design {args.name}", request, len(text), call, suffix=".json")
    result = json.loads(path.read_text())
    out_dir = tour.build / "auditions"
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, preview in enumerate(result["previews"], 1):
        out = out_dir / f"{args.track}-design-{slug(args.name)}-{i}.mp3"
        out.write_bytes(base64.b64decode(preview["audio_base_64"]))
        print(f"  -> {out.relative_to(config.REPO_ROOT)}  generated_voice_id={preview['generated_voice_id']}")


def cmd_save_voice(args: argparse.Namespace) -> None:
    """Save a Voice Design preview as a library voice, so TTS can use it. Free, but it takes one
    of the plan's custom-voice slots; an unsaved preview id is a 404 for TTS."""
    v = eleven.save_designed_voice(args.name, args.description, args.generated_voice_id,
                                   labels={"tour": args.tour, "series": "audio-tours"})
    if "voice_id" not in v:
        raise SystemExit(f"Not saved (is the custom-voice limit reached?): {v}")
    print(f"saved {args.name}: voice_id = {v['voice_id']}")
    print(f"Record it in tours/{args.tour}/tour.toml as [voices.<key>] with name, voice_id, source,"
          " and a comment with the date and why it was chosen.")


def cmd_ledger(args: argparse.Namespace) -> None:
    entries = read_ledger(config.tour(args.tour))
    for e in entries:
        cost = "?" if e["credits"] is None else f"{e['credits']:,}"
        print(f"{e['time']}  {e['label']:<36} {e['chars']:>6} chars {cost:>7} credits")
    chars = sum(e["chars"] for e in entries)
    credits = sum(e["credits"] or 0 for e in entries)
    unknown = sum(1 for e in entries if e["credits"] is None)
    print(f"{'total':<56} {chars:>6} chars {credits:>7} credits")
    if unknown:
        print(f"({unknown} entr{'y' if unknown == 1 else 'ies'} with unknown cost; compare with `tour account`)")


def cmd_render(args: argparse.Namespace) -> None:
    """Render a track's narration chunks (with timestamps) and write its manifest."""
    tour = config.tour(args.tour, args.draft)
    guard = Guard(tour, max_chars=args.max_chars, assume_yes=args.yes)
    render.render_track(tour, args.track_id, guard, args.dry_run)


def cmd_sfx(args: argparse.Namespace) -> None:
    """Generate the sound-effect variants defined in tour.toml into build/sfx/."""
    tour = config.tour(args.tour)
    guard = Guard(tour, max_chars=args.max_chars, assume_yes=args.yes)
    render.generate_sfx(tour, args.names, guard, args.max_seconds)


def cmd_master(args: argparse.Namespace) -> None:
    master.master_track(config.tour(args.tour, args.draft), args.track_id)


def cmd_combine(args: argparse.Namespace) -> None:
    master.combine_tour(config.tour(args.tour))


def cmd_publish(args: argparse.Namespace) -> None:
    publish.publish(config.tour(args.tour))


def cmd_pages(_: argparse.Namespace) -> None:
    publish.pages()


def cmd_route(args: argparse.Namespace) -> None:
    """Fetch each [route.<leg>] from OSRM (cached), simplify it and write route.json."""
    tour = config.tour(args.tour)
    content, legs = route_tools.build(tour, refresh=args.refresh, spacing=args.spacing)
    for line in route_tools.leg_table(legs):
        print(line)
    out = Path(args.out).resolve() if args.out else tour.root / "route.json"
    current = tour.root / "route.json"
    if args.out and current.exists():
        for line in route_tools.compare(content, json.loads(current.read_text())):
            print(f"vs {config.show(current)}: {line}")
    route_tools.write(content, out)
    print(f"  -> {config.show(out)}")


def cmd_plan_check(args: argparse.Namespace) -> None:
    """Offline: check the stops against route.json and docs/process/2-stops.md; exit 1 on errors."""
    tour = config.tour(args.tour, args.draft)
    path = Path(args.route).resolve() if args.route else tour.root / "route.json"
    if not path.exists():
        raise SystemExit(f"No {config.show(path)}; run `uv run tour route {tour.slug}` first.")
    rows, findings, trip = route_tools.check(tour, json.loads(path.read_text()))
    print(f"route: {config.show(path)}")
    for line in route_tools.report(rows, findings, trip):
        print(line)
    if any(f.level == "error" for f in findings):
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(prog="tour")
    sub = parser.add_subparsers(required=True)

    p = sub.add_parser("estimate", help="offline: word/character counts per track")
    p.add_argument("tour", help="tour slug under tours/, e.g. hobart")
    p.add_argument("-v", "--verbose", action="store_true", help="print parsed segments")
    p.add_argument("--draft", metavar="FILE", help="another draft in tours/<tour>/source/ (builds into build/<its name>/)")
    p.set_defaults(func=cmd_estimate)

    p = sub.add_parser("check", help="offline: check the draft against docs/script-format.md")
    p.add_argument("tour", help="tour slug under tours/, e.g. hobart")
    p.add_argument("--draft", metavar="FILE", help="another draft in tours/<tour>/source/ (builds into build/<its name>/)")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("account", help="free: plan tier and credits remaining")
    p.set_defaults(func=cmd_account)

    p = sub.add_parser("models", help="free: models available to this API key")
    p.set_defaults(func=cmd_models)

    p = sub.add_parser("voices", help="free: list library voices")
    p.add_argument("--search", help="filter by name/description")
    p.add_argument("--previews", action="store_true", help="show free preview MP3 URLs")
    p.set_defaults(func=cmd_voices)

    def paid(p: argparse.ArgumentParser, max_chars: int) -> None:
        p.add_argument("tour", help="tour slug under tours/, e.g. hobart")
        p.add_argument("--track", default="ch01")
        p.add_argument("--paragraphs", type=int, default=3, help="leading paragraphs to read")
        p.add_argument("--text", help="text to read instead of the track's leading paragraphs")
        p.add_argument("--max-chars", type=int, default=max_chars, help="refuse above this")
        p.add_argument("-y", "--yes", action="store_true", help="skip the confirmation prompt")

    p = sub.add_parser("audition", help="PAID: same passage, several voices")
    paid(p, max_chars=2500)
    p.add_argument("--voice", action="append", required=True, metavar="NAME=VOICE_ID")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.set_defaults(func=cmd_audition)

    p = sub.add_parser("design", help="PAID: Voice Design previews of a passage")
    paid(p, max_chars=1000)
    p.add_argument("--name", required=True, help="label for the output files")
    p.add_argument("--description", required=True)
    p.add_argument("--model", default="eleven_ttv_v3")
    p.add_argument("--seed", type=int)
    p.set_defaults(func=cmd_design)

    p = sub.add_parser("save-voice", help="free, but uses a custom-voice slot: save a design preview")
    p.add_argument("tour")
    p.add_argument("--name", required=True, help="library name, e.g. Tour-Platypus")
    p.add_argument("--description", required=True, help="the design description")
    p.add_argument("--generated-voice-id", required=True, help="from `tour design` output")
    p.set_defaults(func=cmd_save_voice)

    p = sub.add_parser("render", help="PAID: render a track's narration in chunks")
    p.add_argument("tour")
    p.add_argument("track_id", help="e.g. ch01")
    p.add_argument("--max-chars", type=int, default=6000, help="refuse above this")
    p.add_argument("-n", "--dry-run", action="store_true", help="show chunks and cost only")
    p.add_argument("--draft", metavar="FILE", help="another draft in tours/<tour>/source/ (builds into build/<its name>/)")
    p.add_argument("-y", "--yes", action="store_true", help="skip the confirmation prompt")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("sfx", help="PAID: generate sound-effect variants from tour.toml")
    p.add_argument("tour")
    p.add_argument("names", nargs="*", help="[sfx.NAME] entries (default: all)")
    p.add_argument("--max-seconds", type=float, default=120, help="refuse above this much audio")
    p.add_argument("--max-chars", type=int, default=2000, help="refuse prompts above this")
    p.add_argument("-y", "--yes", action="store_true", help="skip the confirmation prompt")
    p.set_defaults(func=cmd_sfx)

    p = sub.add_parser("master", help="offline: mix, master and tag a rendered track")
    p.add_argument("tour")
    p.add_argument("track_id")
    p.add_argument("--draft", metavar="FILE", help="another draft in tours/<tour>/source/ (builds into build/<its name>/)")
    p.set_defaults(func=cmd_master)

    p = sub.add_parser("combine", help="offline: join mastered tracks into one MP3 with chapters")
    p.add_argument("tour")
    p.set_defaults(func=cmd_combine)

    p = sub.add_parser("publish", help="offline: write site/<tour>/ (tour.json, audio, page) and the tour list")
    p.add_argument("tour")
    p.set_defaults(func=cmd_publish)

    p = sub.add_parser("pages", help="offline: rewrite every published tour's page and the tour list from site/player/ templates")
    p.set_defaults(func=cmd_pages)

    p = sub.add_parser("ledger", help="offline: spend recorded for a tour")
    p.add_argument("tour")
    p.set_defaults(func=cmd_ledger)

    p = sub.add_parser("route", help="free (OSRM): fetch the route legs, write route.json, print the leg table")
    p.add_argument("tour")
    p.add_argument("--out", metavar="FILE", help="write here instead of tours/<tour>/route.json, and compare with it")
    p.add_argument("--spacing", type=float, default=route_tools.SPACING, help="metres between kept points")
    p.add_argument("--refresh", action="store_true", help="ask OSRM again instead of using cache/osrm/")
    p.set_defaults(func=cmd_route)

    p = sub.add_parser("plan-check", help="offline: check triggers, timing, radii and strict against route.json")
    p.add_argument("tour")
    p.add_argument("--route", metavar="FILE", help="another route.json, e.g. one written by `tour route --out`")
    p.add_argument("--draft", metavar="FILE", help="another draft in tours/<tour>/source/ (builds into build/<its name>/)")
    p.set_defaults(func=cmd_plan_check)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
