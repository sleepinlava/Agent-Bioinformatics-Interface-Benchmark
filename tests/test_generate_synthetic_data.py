import os
import tempfile
import gzip
import pytest
from bench.fixtures.generate_synthetic_data import (
    generate_plasmid_data,
    generate_rnaseq_data,
    generate_amplicon_data,
    generate_wgs_data,
    generate_metatranscriptomics_data,
    generate_all,
)


def _count_fastq_records(path: str) -> int:
    """Count sequences in a FASTQ file (gzipped or not)."""
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt") as f:
        return sum(1 for line in f if line.startswith("@") and len(line) > 1)


class TestGeneratePlasmidData:
    def test_generates_two_paired_fastq_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            generate_plasmid_data(tmp)
            r1 = os.path.join(tmp, "data", "sample1_R1.fastq.gz")
            r2 = os.path.join(tmp, "data", "sample1_R2.fastq.gz")
            assert os.path.exists(r1), f"Missing {r1}"
            assert os.path.exists(r2), f"Missing {r2}"

    def test_reads_are_paired_equal_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            generate_plasmid_data(tmp)
            r1 = os.path.join(tmp, "data", "sample1_R1.fastq.gz")
            r2 = os.path.join(tmp, "data", "sample1_R2.fastq.gz")
            n1 = _count_fastq_records(r1)
            n2 = _count_fastq_records(r2)
            assert n1 == n2
            assert n1 >= 100, f"Expected >= 100 reads, got {n1}"

    def test_reads_have_valid_quality_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            generate_plasmid_data(tmp)
            r1 = os.path.join(tmp, "data", "sample1_R1.fastq.gz")
            with gzip.open(r1, "rt") as f:
                lines = f.readlines()
            # Quality line (4th line of each record) should be non-empty
            quality_lines = [lines[i] for i in range(3, len(lines), 4)]
            assert all(len(q.strip()) > 0 for q in quality_lines)


class TestGenerateRnaseqData:
    def test_generates_two_sample_fastq_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            generate_rnaseq_data(tmp)
            for sample in ["control", "treatment"]:
                r1 = os.path.join(tmp, "data", f"{sample}_R1.fastq.gz")
                r2 = os.path.join(tmp, "data", f"{sample}_R2.fastq.gz")
                assert os.path.exists(r1)
                assert os.path.exists(r2)

    def test_both_samples_have_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            generate_rnaseq_data(tmp)
            for sample in ["control", "treatment"]:
                r1 = os.path.join(tmp, "data", f"{sample}_R1.fastq.gz")
                assert _count_fastq_records(r1) >= 50


class TestGenerateAll:
    def test_generates_all_five_plugins(self):
        with tempfile.TemporaryDirectory() as tmp:
            generate_all(tmp)
            expected_dirs = [
                "plasmid_benchmark", "rnaseq_benchmark", "amplicon_benchmark",
                "wgs_benchmark", "metatranscriptomics_benchmark",
            ]
            for d in expected_dirs:
                assert os.path.isdir(os.path.join(tmp, d, "data")), f"Missing data/ in {d}"
