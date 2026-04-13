# SSCC Resource Validator

This directory validates raw EPC inputs by using only the logic in
`2_codes/SSCC_sample_interpretor/SSCC_interpretor.py`.

Workflow:

1. Load raw EPC values from a file.
2. Decode each EPC with `TDS23SSCCDecoder`.
3. Build the observe URL with a fixed GLN.
4. Request the URL and record the response.

By default the script reads:

- `2_codes/SSCC_resource_validator/input.txt`

Usage:

```powershell
python 2_codes/SSCC_resource_validator/validate_epc_resources.py
```

Optional arguments:

```powershell
python 2_codes/SSCC_resource_validator/validate_epc_resources.py `
  --input 2_codes/SSCC_resource_validator/input.txt `
  --hostname-override ID.GHWPC.COM `
  --location-gln 0614141012350 `
  --output-json 2_codes/SSCC_resource_validator/results.json `
  --output-txt 2_codes/SSCC_resource_validator/results.txt
```

