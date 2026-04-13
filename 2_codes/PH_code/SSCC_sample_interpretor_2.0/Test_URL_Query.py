import requests
import json
from SSCC_interpretor import TDS23SSCCDecoder

def send_request_pretty(url: str):
    print("=" * 60)
    print(f"REQUEST URL:\n{url}")
    print("=" * 60)

    try:
        response = requests.get(url, timeout=10)

        print(f"STATUS CODE: {response.status_code}")
        print("-" * 60)

        content_type = response.headers.get("Content-Type", "")

        if "application/json" in content_type:
            data = response.json()
            print("JSON RESPONSE:")
            print(json.dumps(data, indent=4))
            return data
        else:
            print("TEXT RESPONSE:")
            print(response.text[:1000])  # limit length
            return response.text

    except Exception as e:
        print("ERROR:", str(e))
        return None

def send_request(url: str):
    """
    Send a GET request and print the response.
    """
    try:
        print(f"\n[REQUEST] {url}\n")

        response = requests.get(url, timeout=10)

        print(f"[STATUS] {response.status_code}\n")

        # Try JSON first
        try:
            data = response.json()
            print("[RESPONSE JSON]")
            print(data)
            return data
        except ValueError:
            print("[RESPONSE TEXT]")
            print(response.text)
            return response.text

    except requests.exceptions.RequestException as e:
        print("[ERROR]", str(e))
        return None

def extract_epcis_endpoint(response_json):
    """
    Extract EPCIS URL from GS1 Digital Link response.
    """
    if not isinstance(response_json, dict):
        return None

    links = response_json.get("links", [])

    for link in links:
        if link.get("linkType") == "gs1:epcis_repository":
            return link.get("href")

    return None

if __name__ == "__main__":
        decoder = TDS23SSCCDecoder()

        epc_hex = "E280689800008000FF8FA879" ###EF00061414112345678901871FA5A30C92A2A4C0   E280689800008000FF8FA879

        decoded = decoder.decode(
            epc_hex,
            hostname_override="ID.GHWPC.COM"
        )

        print(decoded.scheme)  # SSCC++
        print(decoded.sscc)  # expected SSCC value
        print(decoded.hostname)  # ID.GHWPC.COM for current demo mode
        print(decoded.gs1_digital_link)  # https://ID.GHWPC.COM/00/<sscc>

        observe_url = decoder.build_observe_url(
            decoded,
            location_gln="0614141012350"
        )
        print(f"\n[observe_url] {observe_url}\n")
        result = send_request(observe_url)

        print(result)

        response = send_request_pretty(observe_url)

        epcis_url = extract_epcis_endpoint(response)

        if epcis_url:
            print("\n[EPCIS ENDPOINT FOUND]")
            print(epcis_url)