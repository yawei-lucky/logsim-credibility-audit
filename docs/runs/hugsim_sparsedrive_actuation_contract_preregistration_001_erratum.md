# Actuation-contract preregistration 001: analysis erratum

Date: 2026-08-25

The preregistered analysis exited before reading any run result because the
script looked for `analysis_script_sha256` at the JSON root, while the frozen
preregistration stores it at `implementation.analysis_script_sha256`.

The executed correction changes that field lookup only and adds both hashes to
the output audit:

- preregistered script: `0077f2d8fb10d45c3db61baea0d3aa15a6ea684f5130d5ee4ae2959b1509c462`;
- initial schema-corrected script: `6dd1aaae928add1751112dc4f1fa54f6e53dc686a0217851c24531ba92d97278`;
- final reporting script: `32737d66afdb9af9803461aed436bfbbd3276cb55906530146c1c7b0c942e4cc`.

The final reporting script also completes preregistered plumbing that the
initial script omitted: source-input hash checks, cumulative projection
residual, world time, reset identity, termination flags, and run-output
hashes. These are provenance and descriptive fields; none enters or changes a
decision rule.

No run input, measurement, expected relation, threshold, decision rule,
strongest allowed claim, or forbidden claim changed. The failed analysis did
not create its output directory and made no evidence decision.
