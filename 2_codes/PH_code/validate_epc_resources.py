from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable

import requests


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
INTERPRETER_DIR = PROJECT_ROOT / "2_codes" / "SSCC_sample_interpretor"

if str(INTERPRETER_DIR) not in sys.path:
    sys.path.insert(0, str(INTERPRETER_DIR))

from SSCC_interpretor import EPCDecodeError, TDS23SSCCDecoder  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate EPC resources using only SSCC_sample_interpretor logic."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=SCRIPT_DIR / "input.txt",
        help="Input file containing raw EPC values.",
    )
    parser.add_argument(
        "--input-format",
        choices=("auto", "rfid_scans", "plain"),
        default="auto",
        help="Input file format.",
    )
    parser.add_argument(
        "--hostname-override",
        default="ID.GHWPC.COM",
        help="Hostname override passed into the decoder.",
    )
    parser.add_argument(
        "--location-gln",
        default="0614141012350",
        help="GLN used when building observe URLs.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="HTTP request timeout in seconds.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit for the number of EPCs to validate.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=SCRIPT_DIR / "results.json",
        help="JSON results path.",
    )
    parser.add_argument(
        "--output-txt",
        type=Path,
        default=SCRIPT_DIR / "results.txt",
        help="Text summary path.",
    )
    return parser.parse_args()


def load_epcs(input_path: Path, input_format: str) -> list[dict]:
    raw_text = input_path.read_text(encoding="utf-8").strip()

    if input_format == "auto":
        if "get_rfid_tag_set" in raw_text:
            input_format = "rfid_scans"
        else:
            input_format = "plain"

    if input_format == "rfid_scans":
        payload = ast.literal_eval(raw_text)
        tag_map = payload.get("get_rfid_tag_set", {})
        return [
            {"epc_hex": epc_hex.strip(), "scan_count": count}
            for epc_hex, count in tag_map.items()
        ]

    return [
        {"epc_hex": line.strip(), "scan_count": None}
        for line in raw_text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def summarize_payload(response: requests.Response) -> str:
    content_type = response.headers.get("Content-Type", "")
    if "application/json" in content_type:
        try:
            return json.dumps(response.json(), ensure_ascii=True)
        except ValueError:
            pass
    text = response.text.strip()
    return text[:500]


def iter_status_lines(results: Iterable[dict]) -> Iterable[str]:
    for item in results:
        if item["decode_ok"]:
            yield (
                f"{item['epc_hex']} | scheme={item['scheme']} | sscc={item['sscc']} "
                f"| status={item.get('http_status')} | url={item.get('observe_url')}"
            )
        else:
            yield f"{item['epc_hex']} | decode_error={item['decode_error']}"


def build_text_report(summary: dict, results: list[dict]) -> str:
    lines = [
        f"Input EPC count: {summary['input_count']}",
        f"Decode success count: {summary['decode_success_count']}",
        f"Decode failure count: {summary['decode_failure_count']}",
        f"HTTP success count: {summary['http_success_count']}",
        "HTTP status counts:",
    ]

    for status, count in summary["http_status_counts"].items():
        lines.append(f"  {status}: {count}")

    lines.append("Detailed results:")
    lines.extend(iter_status_lines(results))
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    epc_items = load_epcs(args.input, args.input_format)
    if args.limit is not None:
        epc_items = epc_items[: args.limit]

    decoder = TDS23SSCCDecoder()
    results: list[dict] = []
    http_status_counts: Counter[str] = Counter()

    for epc_item in epc_items:
        epc_hex = epc_item["epc_hex"]
        record = {
            "epc_hex": epc_hex,
            "scan_count": epc_item["scan_count"],
            "decode_ok": False,
            "decode_error": None,
            "scheme": None,
            "sscc": None,
            "hostname": None,
            "gs1_digital_link": None,
            "observe_url": None,
            "http_status": None,
            "http_ok": False,
            "response_detail": None,
        }

        try:
            decoded = decoder.decode(epc_hex, hostname_override=args.hostname_override)
            observe_url = decoder.build_observe_url(
                decoded, location_gln=args.location_gln
            )

            record.update(
                {
                    "decode_ok": True,
                    "scheme": decoded.scheme,
                    "sscc": decoded.sscc,
                    "hostname": decoded.hostname,
                    "gs1_digital_link": decoded.gs1_digital_link,
                    "observe_url": observe_url,
                }
            )

            response = requests.get(observe_url, timeout=args.timeout)
            record["http_status"] = response.status_code
            record["http_ok"] = response.ok
            record["response_detail"] = summarize_payload(response)
            http_status_counts[str(response.status_code)] += 1

        except EPCDecodeError as exc:
            record["decode_error"] = str(exc)
        except requests.RequestException as exc:
            record["http_status"] = "request_error"
            record["response_detail"] = str(exc)
            http_status_counts["request_error"] += 1

        results.append(record)

    summary = {
        "input_count": len(epc_items),
        "decode_success_count": sum(1 for item in results if item["decode_ok"]),
        "decode_failure_count": sum(1 for item in results if not item["decode_ok"]),
        "http_success_count": sum(1 for item in results if item["http_ok"]),
        "http_status_counts": dict(sorted(http_status_counts.items())),
    }

    payload = {"summary": summary, "results": results}
    args.output_json.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8"
    )
    args.output_txt.write_text(build_text_report(summary, results), encoding="utf-8")

    print(json.dumps(summary, indent=2, ensure_ascii=True))
    print(f"JSON report written to: {args.output_json}")
    print(f"Text report written to: {args.output_txt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


