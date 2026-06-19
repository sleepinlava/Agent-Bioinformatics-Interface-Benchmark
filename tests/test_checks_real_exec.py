"""Tests for v0.6 real-execution check functions."""
import json
import os
import sys
import tempfile

import pytest

# Import check functions from the checks module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bench", "scoring"))
from checks import (  # noqa: E402
    check_pipeline_outputs_match_assertions,
    check_per_category_breakdown,
    check_output_file_integrity,
)


def _make_fake_run_dir(base: str, assertions: dict, outputs: dict):
    """Create a minimal run directory with expected_assertions.yaml and output files."""
    import yaml

    # Write assertions
    with open(os.path.join(base, "expected_assertions.yaml"), "w") as f:
        yaml.dump(assertions, f)
    # Write output files
    results_dir = os.path.join(base, "results", "bench-test")
    prov_dir = os.path.join(results_dir, "provenance")
    os.makedirs(prov_dir, exist_ok=True)
    for relpath, content in outputs.items():
        full = os.path.join(results_dir, relpath)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        if isinstance(content, str):
            with open(full, "w") as f:
                f.write(content)
        elif isinstance(content, list):
            # TSV
            with open(full, "w") as f:
                for row in content:
                    f.write("\t".join(str(c) for c in row) + "\n")
        elif isinstance(content, dict):
            with open(full, "w") as f:
                json.dump(content, f)


class TestCheckPipelineOutputsMatchAssertions:
    def test_all_assertions_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            assertions = {
                "test_plugin": {
                    "qc": {"min_reads_retained": 10, "clean_fastq_exists": True},
                    "provenance": {"min_commands": 3, "run_summary_exists": True},
                }
            }
            outputs = {
                # Provenance files for min_commands + run_summary_exists
                "provenance/commands.tsv": [
                    ["step_id", "tool_id", "status", "exit_code"],
                    ["qc_fastp", "fastp", "success", "0"],
                    ["assembly", "megahit", "success", "0"],
                    ["prodigal", "prodigal", "success", "0"],
                ],
                "provenance/run_summary.json": {"total_steps": 3, "successful": 3},
                # fastp JSON for min_reads_retained (needs summary.after_filtering.total_reads)
                "qc/fastp/report/fastp.json": {
                    "summary": {
                        "before_filtering": {"total_reads": 100},
                        "after_filtering": {"total_reads": 85},
                    },
                },
                # fastq placeholder for clean_fastq_exists
                # The _check_existence glob for clean_fastq_exists is:
                #   */qc/*/clean/*.fastq*
                # which expects: <anything>/qc/<tool>/clean/<file>.fastq*
                "sample1/qc/fastp/clean/sample_1.clean.fastq": (
                    "@read1\nATCG\n+\nIIII\n"
                ),
            }
            _make_fake_run_dir(tmp, assertions, outputs)

            result = check_pipeline_outputs_match_assertions(tmp, {})

            assert result.passed is True
            assert result.score >= 6  # max assertion score

    def test_assertion_fails_on_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            assertions = {
                "test_plugin": {
                    "qc": {"clean_fastq_exists": True},
                }
            }
            outputs = {}  # no files at all
            _make_fake_run_dir(tmp, assertions, outputs)

            result = check_pipeline_outputs_match_assertions(tmp, {})

            assert result.passed is False
            assert result.score < 6

    def test_numeric_assertion_fails_below_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            assertions = {
                "test_plugin": {
                    "provenance": {"min_commands": 100},
                }
            }
            outputs = {
                "provenance/commands.tsv": [
                    ["step_id", "tool_id", "status"],
                    ["qc_fastp", "fastp", "success"],
                ],
            }
            _make_fake_run_dir(tmp, assertions, outputs)

            result = check_pipeline_outputs_match_assertions(tmp, {})

            assert result.passed is False


class TestCheckPerCategoryBreakdown:
    def test_reports_per_category_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            assertions = {
                "test_plugin": {
                    "qc": {"min_reads_retained": 1, "clean_fastq_exists": True},
                    "assembly": {"min_contigs": 1},
                    "provenance": {"min_commands": 1, "run_summary_exists": True},
                }
            }
            outputs = {
                # Provenance files
                "provenance/commands.tsv": [
                    ["step_id", "tool_id", "status"],
                    ["qc_fastp", "fastp", "success"],
                ],
                "provenance/run_summary.json": {"total_steps": 1},
                # fastp JSON for min_reads_retained
                "qc/fastp/report/fastp.json": {
                    "summary": {
                        "before_filtering": {"total_reads": 100},
                        "after_filtering": {"total_reads": 85},
                    },
                },
                # fastq placeholder for clean_fastq_exists
                # The _check_existence glob for clean_fastq_exists is:
                #   */qc/*/clean/*.fastq*
                "sample1/qc/fastp/clean/sample_1.clean.fastq": (
                    "@read1\nATCG\n+\nIIII\n"
                ),
                # FASTA for min_contigs: 2 contigs >= 1 expected
                "assembly/spades/contigs.fasta": (
                    ">contig_1\nATCGATCG\n>contig_2\nGGGGCCCC\n"
                ),
            }
            _make_fake_run_dir(tmp, assertions, outputs)

            result = check_per_category_breakdown(tmp, {})

            assert result.passed is True
            details = result.details
            assert "categories" in details
            assert "qc" in details["categories"]
            assert "passed" in details


class TestCheckOutputFileIntegrity:
    def test_all_required_files_present_and_nonempty(self):
        with tempfile.TemporaryDirectory() as tmp:
            results_dir = os.path.join(tmp, "results", "bench-test")
            prov_dir = os.path.join(results_dir, "provenance")
            tables_dir = os.path.join(results_dir, "tables")
            os.makedirs(prov_dir)
            os.makedirs(tables_dir)
            with open(os.path.join(prov_dir, "commands.tsv"), "w") as f:
                f.write("step_id\ttool_id\tstatus\n")
            with open(os.path.join(tables_dir, "test.tsv"), "w") as f:
                f.write("col1\tcol2\n")

            task = {
                "required_output_files": [
                    "results/*/provenance/commands.tsv",
                    "results/*/tables/*.tsv",
                ]
            }
            result = check_output_file_integrity(tmp, task)

            assert result.passed is True

    def test_fails_when_required_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = {
                "required_output_files": [
                    "results/*/provenance/commands.tsv",
                ]
            }
            result = check_output_file_integrity(tmp, task)

            assert result.passed is False
