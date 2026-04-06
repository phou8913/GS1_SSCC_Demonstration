from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote


class EPCDecodeError(ValueError):
    pass


@dataclass
class DecodedEPC:
    scheme: str
    header_bits: str
    filter_value: Optional[int] = None
    sscc: Optional[str] = None
    hostname: Optional[str] = None
    gs1_digital_link: Optional[str] = None
    raw_bits: Optional[str] = None
    notes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RFIDCandidate:
    source_hex: str
    seen_count: float
    strategy: str
    bit_offset: int
    source_bits: str
    candidate_bits: str
    notes: Dict[str, Any] = field(default_factory=dict)


class TDS23SSCCDecoder:
    HEADER_SSCC_96 = "00110001"
    HEADER_SSCC_PLUS = "11111001"
    HEADER_SSCC_PP = "11101111"

    def decode(self, epc: str, hostname_override: Optional[str] = None) -> DecodedEPC:
        bits = self._normalize_to_bits(epc)
        if len(bits) < 8:
            raise EPCDecodeError("EPC too short.")

        header = bits[:8]

        if header == self.HEADER_SSCC_96:
            decoded = self._decode_sscc_96(bits)
        elif header == self.HEADER_SSCC_PLUS:
            decoded = self._decode_sscc_plus(bits)
        elif header == self.HEADER_SSCC_PP:
            decoded = self._decode_sscc_pp(bits)
        else:
            raise EPCDecodeError(f"Unsupported header: {header}")

        if hostname_override:
            decoded.hostname = hostname_override
            if decoded.sscc:
                decoded.gs1_digital_link = f"https://{decoded.hostname}/00/{decoded.sscc}"
            decoded.notes["hostname_source"] = "override"

        return decoded

    def _decode_sscc_96(self, bits: str) -> DecodedEPC:
        if len(bits) < 96:
            raise EPCDecodeError("SSCC-96 must be 96 bits.")

        filter_bits = bits[8:11]
        partition_bits = bits[11:14]
        payload_bits = bits[14:75]

        partition_value = self._bits_to_int(partition_bits)
        partition_table = {
            0: (40, 12, 18, 5),
            1: (37, 11, 21, 6),
            2: (34, 10, 24, 7),
            3: (30, 9, 28, 8),
            4: (27, 8, 31, 9),
            5: (24, 7, 34, 10),
            6: (20, 6, 38, 11),
        }

        if partition_value not in partition_table:
            raise EPCDecodeError(f"Invalid partition value {partition_value} for SSCC-96.")

        cp_bits_len, cp_digits, sr_bits_len, sr_digits = partition_table[partition_value]
        cp_bits = payload_bits[:cp_bits_len]
        sr_bits = payload_bits[cp_bits_len:cp_bits_len + sr_bits_len]

        company_prefix = str(self._bits_to_int(cp_bits)).zfill(cp_digits)
        ext_serial = str(self._bits_to_int(sr_bits)).zfill(sr_digits)
        sscc_body_17 = company_prefix + ext_serial
        sscc_18 = self._append_mod10_check_digit(sscc_body_17)

        return DecodedEPC(
            scheme="SSCC-96",
            header_bits=bits[:8],
            filter_value=self._bits_to_int(filter_bits),
            sscc=sscc_18,
            hostname="id.gs1.org",
            gs1_digital_link=f"https://id.gs1.org/00/{sscc_18}",
            raw_bits=bits[:96],
            notes={
                "partition": partition_value,
                "hostname_source": "standard_default",
            },
        )

    def _decode_sscc_plus(self, bits: str) -> DecodedEPC:
        required_len = 8 + 1 + 3 + 72
        if len(bits) < required_len:
            raise EPCDecodeError("SSCC+ EPC too short.")

        toggle_bit = bits[8]
        filter_bits = bits[9:12]
        sscc_bits = bits[12:84]
        sscc = self._decode_fixed_length_numeric(sscc_bits, 18)

        return DecodedEPC(
            scheme="SSCC+",
            header_bits=bits[:8],
            filter_value=self._bits_to_int(filter_bits),
            sscc=sscc,
            hostname="id.gs1.org",
            gs1_digital_link=f"https://id.gs1.org/00/{sscc}",
            raw_bits=bits[:84],
            notes={
                "toggle_bit": int(toggle_bit),
                "hostname_source": "standard_default",
            },
        )

    def _decode_sscc_pp(self, bits: str) -> DecodedEPC:
        required_len = 8 + 1 + 3 + 72
        if len(bits) < required_len:
            raise EPCDecodeError("SSCC++ EPC too short.")

        toggle_bit = bits[8]
        filter_bits = bits[9:12]
        sscc_bits = bits[12:84]
        hostname_bits = bits[84:]

        sscc = self._decode_fixed_length_numeric(sscc_bits, 18)
        hostname = self._decode_custom_hostname(hostname_bits)
        gs1_digital_link = None
        if hostname:
            gs1_digital_link = f"https://{hostname}/00/{sscc}"

        return DecodedEPC(
            scheme="SSCC++",
            header_bits=bits[:8],
            filter_value=self._bits_to_int(filter_bits),
            sscc=sscc,
            hostname=hostname,
            gs1_digital_link=gs1_digital_link,
            raw_bits=bits,
            notes={
                "toggle_bit": int(toggle_bit),
                "hostname_bits_length": len(hostname_bits),
                "hostname_source": "decoded" if hostname else "not_decoded",
            },
        )

    def build_observe_url(
        self,
        decoded: DecodedEPC,
        location_gln: str,
        hostname_override: Optional[str] = None,
        link_type: str = "gs1:epcis_repository",
    ) -> str:
        if not decoded.sscc:
            raise EPCDecodeError("Decoded EPC does not contain SSCC.")

        host = hostname_override or decoded.hostname
        if not host:
            raise EPCDecodeError("No hostname available for observe URL.")

        return f"https://{host}/00/{decoded.sscc}/414/{location_gln}?linkType={quote(link_type)}"

    def _normalize_to_bits(self, epc: str) -> str:
        epc = epc.strip().replace(" ", "").replace("_", "")
        if not epc:
            raise EPCDecodeError("Empty EPC input.")

        if set(epc) <= {"0", "1"}:
            return epc

        try:
            value = int(epc, 16)
        except ValueError as exc:
            raise EPCDecodeError("Input must be binary or hex.") from exc

        return format(value, f"0{len(epc) * 4}b")

    def _bits_to_int(self, bits: str) -> int:
        return int(bits, 2) if bits else 0

    def _decode_fixed_length_numeric(self, bits: str, digit_count: int) -> str:
        return str(self._bits_to_int(bits)).zfill(digit_count)

    def _decode_custom_hostname(self, bits: str) -> Optional[str]:
        if len(bits) < 7:
            return None

        encoding_indicator = bits[0]
        length_indicator = self._bits_to_int(bits[1:7])
        return f"<decoded-hostname-enc{encoding_indicator}-len{length_indicator}>"

    def _append_mod10_check_digit(self, body_17_digits: str) -> str:
        if len(body_17_digits) != 17 or not body_17_digits.isdigit():
            raise EPCDecodeError("SSCC body must be 17 digits.")

        total = 0
        reversed_digits = list(map(int, reversed(body_17_digits)))
        for i, digit in enumerate(reversed_digits, start=1):
            weight = 3 if i % 2 == 1 else 1
            total += digit * weight

        check_digit = (10 - (total % 10)) % 10
        return body_17_digits + str(check_digit)


class RFIDScanExplorer:
    def __init__(self, decoder: Optional[TDS23SSCCDecoder] = None) -> None:
        self.decoder = decoder or TDS23SSCCDecoder()

    def load_scan_file(self, scan_file: str | Path) -> Dict[str, float]:
        scan_path = Path(scan_file)
        payload = ast.literal_eval(scan_path.read_text())
        if "get_rfid_tag_set" not in payload:
            raise EPCDecodeError("RFID scan file does not contain 'get_rfid_tag_set'.")
        return payload["get_rfid_tag_set"]

    def iter_candidates(self, scan_file: str | Path) -> Iterable[RFIDCandidate]:
        tags = self.load_scan_file(scan_file)
        sorted_tags = sorted(tags.items(), key=lambda item: (-float(item[1]), item[0]))
        for tag_hex, seen_count in sorted_tags:
            try:
                source_bits = self.decoder._normalize_to_bits(tag_hex)
            except EPCDecodeError:
                continue

            if len(source_bits) < 72:
                continue

            yield from self._iter_source_candidates(tag_hex, float(seen_count), source_bits)

    def _iter_source_candidates(
        self,
        tag_hex: str,
        seen_count: float,
        source_bits: str,
    ) -> Iterable[RFIDCandidate]:
        if len(source_bits) in (84, 96, 132, 160):
            yield RFIDCandidate(
                source_hex=tag_hex,
                seen_count=seen_count,
                strategy="raw_tag",
                bit_offset=0,
                source_bits=source_bits,
                candidate_bits=source_bits,
                notes={"candidate_length": len(source_bits)},
            )

        max_offset = len(source_bits) - 72
        for offset in range(0, max_offset + 1, 4):
            sscc_bits = source_bits[offset:offset + 72]
            remainder = source_bits[:offset] + source_bits[offset + 72:]
            hostname_bits = (remainder + ("0" * 48))[:48]

            yield RFIDCandidate(
                source_hex=tag_hex,
                seen_count=seen_count,
                strategy="synthetic_sscc_plus_window",
                bit_offset=offset,
                source_bits=source_bits,
                candidate_bits=self.decoder.HEADER_SSCC_PLUS + "0" + "000" + sscc_bits,
                notes={
                    "candidate_length": 84,
                    "sscc_window_start": offset,
                    "sscc_window_end": offset + 72,
                },
            )

            yield RFIDCandidate(
                source_hex=tag_hex,
                seen_count=seen_count,
                strategy="synthetic_sscc_pp_window_132",
                bit_offset=offset,
                source_bits=source_bits,
                candidate_bits=self.decoder.HEADER_SSCC_PP + "0" + "000" + sscc_bits + hostname_bits,
                notes={
                    "candidate_length": 132,
                    "sscc_window_start": offset,
                    "sscc_window_end": offset + 72,
                    "hostname_bits_source_length": len(remainder),
                    "hostname_bits_padded_to": 48,
                },
            )
