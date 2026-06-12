# Diagnostic Report: Missing Input

## Issue Identified
There appears to be a problem with input files. Some samples cannot
be processed because input data is missing, but I cannot inspect
the provenance to determine which specific sample or field is affected.
Without provenance data (commands.tsv, resolved_inputs.tsv),
I am unable to identify the exact missing input.

## Recommendation
Check all sample entries in sample_sheet.tsv for valid file paths.