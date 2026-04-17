"""Command-line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from injection_lab import __version__
from injection_lab.providers import ProviderError, make_provider
from injection_lab.runner import evaluate, write_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="injection-lab",
        description="Run a small prompt-injection fixture suite against a supplied system prompt.",
    )
    parser.add_argument("--version", action="version", version=f"injection-lab {__version__}")
    parser.add_argument("--system-prompt-file", required=True, type=Path)
    parser.add_argument("--provider", choices=("mock", "openai"), default="mock")
    parser.add_argument("--model", help="Model name for --provider openai")
    parser.add_argument("--runs", type=int, default=1, choices=range(1, 11), metavar="N",
                        help="Run each case N times (1 to 10, default 1). A real run makes 3 x N requests.")
    parser.add_argument("--max-output-tokens", type=int, default=1000, metavar="N",
                        help="Output limit per request for --provider openai (default 1000; reasoning models need room to think)")
    parser.add_argument("--out", type=Path, help="Write transcript-free JSON results to this path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        prompt = args.system_prompt_file.read_text(encoding="utf-8")
    except OSError:
        print("error: could not read the system prompt file", file=sys.stderr)
        return 2
    if not prompt.strip():
        print("error: system prompt file is empty", file=sys.stderr)
        return 2

    try:
        provider = make_provider(args.provider, args.model, args.max_output_tokens)
        if args.provider == "openai":
            print(
                f"Note: this run sends the prompt and synthetic attack fixtures to OpenAI ({3 * args.runs} requests); "
                "provider usage may incur charges.",
                file=sys.stderr,
            )
        report = evaluate(prompt, provider, args.runs)
    except ProviderError as exc:
        message = (
            "OPENAI_API_KEY is required for --provider openai"
            if exc.code == "missing_openai_api_key"
            else "--model or INJECTION_LAB_MODEL is required for --provider openai"
            if exc.code == "missing_model"
            else f"provider setup failed ({exc.code})"
        )
        print(f"error: {message}", file=sys.stderr)
        return 2

    counts = report["counts"]
    if not report["prompt_tested"]:
        print("MOCK RUN: your system prompt was NOT tested (the mock ignores it). This only checks that the harness works.")
    print(f"provider: {report['provider']} ({report['model']})")
    print(f"cases: {len(report['cases'])} x {report['runs_per_case']} run(s)")
    print(f"fixture passed: {counts['fixture_passed']}")
    print(f"attack indicators: {counts['attack_indicator']}")
    print(f"inconclusive: {counts['inconclusive']}")
    print(f"errors: {counts['error']}")
    for case in report["cases"]:
        passed = case["statuses"].get("fixture_passed", 0)
        print(f"  {case['case_id']}: {case['status']} ({passed}/{case['runs']} passed)")
    if report["prompt_echo_check"] == "skipped_prompt_too_short":
        print("note: the prompt is under 4 words, so quoting of the prompt could not be checked (only the canary is)")
    elif report["prompt_echo_check"] == "whole_prompt":
        print("note: short prompt, so only a reply quoting all of it counts as a prompt leak")
    if any(case["error_code"] in ("incomplete_output", "missing_text_output") for case in report["cases"]):
        print("hint: the model returned no text; try a larger --max-output-tokens", file=sys.stderr)
    print("raw prompts and model responses were not saved")
    if args.out:
        write_report(report, args.out)
        print(f"report: {args.out}")
    return 0 if counts["error"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

