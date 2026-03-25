from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
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


class TDS23SSCCDecoder:
    """
    Generalized decoder for SSCC-96 / SSCC+ / SSCC++.

    Design goals:
    1. Preserve general standards-based decoding.
    2. Support immediate demo mode with configured hostname fallback.
    """

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

        # Demo-aligned fallback behavior:
        # If hostname is not decoded or not yet implemented, allow configured hostname.
        # if not decoded.hostname and hostname_override:
        #     decoded.hostname = hostname_override
        #     if decoded.sscc:
        #         decoded.gs1_digital_link = f"https://{decoded.hostname}/00/{decoded.sscc}"
        #     decoded.notes["hostname_source"] = "override"
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

        # TDS 2.3 SSCC-96 partition table
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

    # ----------------------------
    # Demo-oriented helper methods
    # ----------------------------

    def build_observe_url(
        self,
        decoded: DecodedEPC,
        location_gln: str,
        hostname_override: Optional[str] = None,
        link_type: str = "gs1:epcis_repository",
    ) -> str:
        """
        Build demo observe URL.

        Example note uses:
        https://ID.GHWPC.COM/00/<SSCC>/414/<location>&linkType=gs1:epcis_repository

        Operation Brilliance slide uses query style:
        https://senders_domain/00/<SSCC>?414=<reader_GLN>&linkType=gs1:epcis

        We support both styles below by defaulting to the example style.
        """
        if not decoded.sscc:
            raise EPCDecodeError("Decoded EPC does not contain SSCC.")

        host = hostname_override or decoded.hostname
        if not host:
            raise EPCDecodeError("No hostname available for observe URL.")

        # Align with the GS1 meeting note example first.
        return f"https://{host}/00/{decoded.sscc}/414/{location_gln}?linkType={quote(link_type)}"

    def build_packing_query_url(self, endpoint_base: str, parent_id_value: str) -> str:
        """
        Example:
        https://epics.example.com/events?MATCH_parentID=<sscc_value>&EQ_bizStep=packing
        """
        return f"{endpoint_base}?MATCH_parentID={quote(parent_id_value, safe=':/')}&EQ_bizStep=packing"

    def extract_expected_child_epcs(self, epcis_query_document: Dict[str, Any]) -> List[str]:
        """
        Parse EPCIS query result and return childEPCs.
        """
        try:
            events = (
                epcis_query_document["epcisBody"]["queryResults"]["resultsBody"]["eventList"]
            )
        except KeyError as exc:
            raise EPCDecodeError("Invalid EPCIS query document structure.") from exc

        child_epcs: List[str] = []
        for event in events:
            for epc in event.get("childEPCs", []):
                child_epcs.append(epc)

        return child_epcs

    # ----------------------------
    # Internal utilities
    # ----------------------------

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
        """
        Placeholder implementation.

        Keep isolated so it can be replaced later with stricter TDS/TDT-conformant logic.
        """
        return str(self._bits_to_int(bits)).zfill(digit_count)

    def _decode_custom_hostname(self, bits: str) -> Optional[str]:
        """
        Placeholder for TDS 2.3 §14.5.16 hostname decoding.

        For the immediate demo, the system may intentionally use hostname_override.
        """
        if len(bits) < 7:
            return None

        encoding_indicator = bits[0]
        length_indicator = self._bits_to_int(bits[1:7])

        # Placeholder only
        return f"<decoded-hostname-enc{encoding_indicator}-len{length_indicator}>"

    def _append_mod10_check_digit(self, body_17_digits: str) -> str:
        if len(body_17_digits) != 17 or not body_17_digits.isdigit():
            raise EPCDecodeError("SSCC body must be 17 digits.")

        total = 0
        reversed_digits = list(map(int, reversed(body_17_digits)))

        for i, d in enumerate(reversed_digits, start=1):
            weight = 3 if i % 2 == 1 else 1
            total += d * weight

        check_digit = (10 - (total % 10)) % 10
        return body_17_digits + str(check_digit)