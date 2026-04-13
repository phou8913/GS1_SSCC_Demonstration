from SSCC_interpretor import TDS23SSCCDecoder

if __name__ == "__main__":
    decoder = TDS23SSCCDecoder()

    epc_hex = "F90095201234567891235" ##EF00061414112345678901871FA5A30C92A2A4C0 
    ## SSCC+: F90095201234567891235
    ## invalid: E280689800008000FF8FA879

    decoded = decoder.decode(
        epc_hex,
        hostname_override="ID.GHWPC.COM"
    )

    print(decoded.scheme)            # SSCC++
    print(decoded.sscc)              # expected SSCC value
    print(decoded.hostname)          # ID.GHWPC.COM for current demo mode
    print(decoded.gs1_digital_link)  # https://ID.GHWPC.COM/00/<sscc>

    observe_url = decoder.build_observe_url(
        decoded,
        location_gln="0614141012350"
    )

    print(observe_url) 