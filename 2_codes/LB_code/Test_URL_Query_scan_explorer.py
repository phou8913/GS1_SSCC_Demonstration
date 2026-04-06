import argparse
from dataclasses import asdict
from pathlib import Path

import requests

from SSCC_interpretor_scan_explorer import EPCDecodeError, RFIDScanExplorer, TDS23SSCCDecoder


def probe_url(url: str, timeout: int):
    try:
        response = requests.get(url, timeout=timeout)
        content_type = response.headers.get("Content-Type", "")
        return {
            "ok": response.ok,
            "status_code": response.status_code,
            "content_type": content_type,
            "text_preview": response.text[:240],
        }
    except requests.exceptions.RequestException as exc:
        return {
            "ok": False,
            "status_code": None,
            "content_type": "",
            "text_preview": str(exc),
        }


def build_success_record(candidate, decoded, observe_url, probe_result):
    record = asdict(candidate)
    record.update(
        {
            "scheme": decoded.scheme,
            "sscc": decoded.sscc,
            "hostname": decoded.hostname,
            "observe_url": observe_url,
            "probe": probe_result,
        }
    )
    return record


def main():
    parser = argparse.ArgumentParser(
        description="Try RFID scan values as SSCC candidates and report URLs that respond."
    )
    parser.add_argument(
        "--scan-file",
        default=str(Path(__file__).with_name("RFID_scans.txt")),
        help="Path to the RFID scan dump.",
    )
    parser.add_argument("--hostname", default="ID.GHWPC.COM", help="Hostname override for URL generation.")
    parser.add_argument("--location-gln", default="0614141012350", help="Location GLN used in observe URLs.")
    parser.add_argument("--timeout", type=int, default=5, help="HTTP timeout in seconds.")
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=0,
        help="Optional cap after deduping URLs. Use 0 to test all generated candidates.",
    )
    args = parser.parse_args()

    decoder = TDS23SSCCDecoder()
    explorer = RFIDScanExplorer(decoder)

    successes = []
    deduped = []
    seen_urls = set()

    for candidate in explorer.iter_candidates(args.scan_file):
        try:
            decoded = decoder.decode(candidate.candidate_bits, hostname_override=args.hostname)
            observe_url = decoder.build_observe_url(
                decoded,
                location_gln=args.location_gln,
                hostname_override=args.hostname,
            )
        except EPCDecodeError:
            continue

        if observe_url in seen_urls:
            continue

        seen_urls.add(observe_url)
        deduped.append((candidate, decoded, observe_url))

    if args.max_candidates > 0:
        deduped = deduped[:args.max_candidates]

    print(f"Loaded scan file: {args.scan_file}")
    print(f"Generated unique observe URLs: {len(deduped)}")

    for index, (candidate, decoded, observe_url) in enumerate(deduped, start=1):
        probe_result = probe_url(observe_url, timeout=args.timeout)
        if probe_result["ok"]:
            successes.append(build_success_record(candidate, decoded, observe_url, probe_result))
            print(f"[{index}] OK {probe_result['status_code']} {observe_url}")
            print(f"    source={candidate.source_hex} strategy={candidate.strategy} offset={candidate.bit_offset}")
            print(f"    sscc={decoded.sscc} content_type={probe_result['content_type']}")
        else:
            print(f"[{index}] FAIL {probe_result['status_code']} {observe_url}")
            print(f"    source={candidate.source_hex} strategy={candidate.strategy} offset={candidate.bit_offset}")
            if probe_result["text_preview"]:
                print(f"    detail={probe_result['text_preview']}")

    print()
    print(f"Successful URLs: {len(successes)}")
    for result in successes:
        print("-" * 80)
        print(f"source_hex: {result['source_hex']}")
        print(f"seen_count: {result['seen_count']}")
        print(f"strategy: {result['strategy']}")
        print(f"bit_offset: {result['bit_offset']}")
        print(f"scheme: {result['scheme']}")
        print(f"sscc: {result['sscc']}")
        print(f"url: {result['observe_url']}")
        print(f"status: {result['probe']['status_code']}")
        print(f"content_type: {result['probe']['content_type']}")
        print(f"preview: {result['probe']['text_preview']}")


if __name__ == "__main__":
    main()
