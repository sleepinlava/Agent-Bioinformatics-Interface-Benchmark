"""Generate minimal synthetic FASTQ data for ABI-Bench real-execution fixtures.

Each generator creates just enough synthetic reads to run the pipeline
and verify assertions — typically paired-end reads from known reference
sequences with realistic quality scores.

Usage:
    python generate_synthetic_data.py --all --outdir bench/fixtures/
    python generate_synthetic_data.py --plugin plasmid --outdir bench/fixtures/plasmid_benchmark/
"""

import argparse
import gzip
import os
import random
import sys

# ── Constants ──────────────────────────────────────────────────────────
SEED = 42
READ_LENGTH = 150
DEFAULT_N_READS = 200
PHRED_OFFSET = 33

# Known reference snippets for each plugin's synthetic reads
# These are real biological sequences used as templates.
ECOLI_LACZ = (
    "ATGACCATGATTACGGATTCACTGGCCGTCGTTTTACAACGTCGTGACTGGGAAAACCCT"
    "GGCGTTACCCAACTTAATCGCCTTGCAGCACATCCCCCTTTCGCCAGCTGGCGTAATAGC"
    "GAAGAGGCCCGCACCGATCGCCCTTCCCAACAGTTGCGCAGCCTGAATGGCGAATGGCGC"
)

REFSEQ_PLASMIDS = {
    "NC_002127.1": "ATGAAGCTCTTCGTAGGCGGCGGTGTTCATTCTGTTGGCAA" * 50,
    "NC_002483.1": "ATGCGTACCGTTCTTCGTGGCGGTCGTCGTGGTGGTGGTTCT" * 50,
    "NC_011977.1": "ATGGCTGACGCTTTCTTCCGTGACGGTGGTCCAGCTGGTTCT" * 50,
}

BACTERIA_16S = {
    "Escherichia": "AGAGTTTGATCCTGGCTCAGATTGAACGCTGGCGGCAGGCCTAA" * 40,
    "Bacillus": "AGAGTTTGATCCTGGCTCAGGACGAACGCTGGCGGCGTGCCTAA" * 40,
    "Pseudomonas": "AGAGTTTGATCCTGGCTCAGATTGAACGCTGGCGGCAGGCCTAA" * 40,
}

BACTERIAL_GENOME = "ATGAACGAAGCGCGTATTGCTCAACGTGGCAGCGATAAAAAAGCG" * 60


def _random_qual(n: int) -> str:
    """Generate a random phred-quality string of length n."""
    return "".join(chr(PHRED_OFFSET + random.randint(20, 40)) for _ in range(n))


def _write_fastq_paired(path_r1: str, path_r2: str, template: str,
                        n_reads: int = DEFAULT_N_READS):
    """Write paired-end FASTQ files from a template sequence."""
    os.makedirs(os.path.dirname(path_r1), exist_ok=True)
    tlen = len(template)
    with gzip.open(path_r1, "wt") as f1, gzip.open(path_r2, "wt") as f2:
        for i in range(n_reads):
            start = random.randint(0, tlen - READ_LENGTH - 1)
            seq = template[start:start + READ_LENGTH]
            # Read 2: reverse complement (simple approximation)
            rc = seq.translate(str.maketrans("ATCG", "TAGC"))[::-1]
            qual = _random_qual(READ_LENGTH)
            f1.write(f"@read_{i}_R1\n{seq}\n+\n{qual}\n")
            f2.write(f"@read_{i}_R2\n{rc}\n+\n{qual}\n")


def _write_fastq_single(path_r1: str, template: str,
                        n_reads: int = DEFAULT_N_READS):
    """Write a single-end FASTQ file from a template sequence."""
    os.makedirs(os.path.dirname(path_r1), exist_ok=True)
    tlen = len(template)
    with gzip.open(path_r1, "wt") as f:
        for i in range(n_reads):
            start = random.randint(0, tlen - READ_LENGTH - 1)
            seq = template[start:start + READ_LENGTH]
            qual = _random_qual(READ_LENGTH)
            f.write(f"@read_{i}\n{seq}\n+\n{qual}\n")


def generate_plasmid_data(outdir: str):
    """Generate paired-end reads from 3 RefSeq plasmid templates."""
    random.seed(SEED)
    # Pool all plasmid templates
    templates = list(REFSEQ_PLASMIDS.values())
    combined = templates[0] + templates[1] + templates[2]
    _write_fastq_paired(
        os.path.join(outdir, "data", "sample1_R1.fastq.gz"),
        os.path.join(outdir, "data", "sample1_R2.fastq.gz"),
        combined, n_reads=400,
    )


def generate_rnaseq_data(outdir: str):
    """Generate paired-end RNA-seq reads from E. coli lacZ for 2 conditions."""
    random.seed(SEED)
    for sample in ["control", "treatment"]:
        _write_fastq_paired(
            os.path.join(outdir, "data", f"{sample}_R1.fastq.gz"),
            os.path.join(outdir, "data", f"{sample}_R2.fastq.gz"),
            ECOLI_LACZ * 20, n_reads=200,
        )


def generate_amplicon_data(outdir: str):
    """Generate single-end 16S V4 amplicon reads from 3 bacterial references."""
    random.seed(SEED)
    for i, (name, template) in enumerate(BACTERIA_16S.items()):
        _write_fastq_single(
            os.path.join(outdir, "data", f"sample{i + 1}_R1.fastq.gz"),
            template, n_reads=200,
        )


def generate_wgs_data(outdir: str):
    """Generate paired-end WGS reads from a synthetic bacterial genome."""
    random.seed(SEED)
    _write_fastq_paired(
        os.path.join(outdir, "data", "sample1_R1.fastq.gz"),
        os.path.join(outdir, "data", "sample1_R2.fastq.gz"),
        BACTERIAL_GENOME, n_reads=300,
    )


def generate_metatranscriptomics_data(outdir: str):
    """Generate paired-end transcriptomic reads from E. coli lacZ template."""
    random.seed(SEED)
    for sample in ["community1", "community2"]:
        _write_fastq_paired(
            os.path.join(outdir, "data", f"{sample}_R1.fastq.gz"),
            os.path.join(outdir, "data", f"{sample}_R2.fastq.gz"),
            ECOLI_LACZ * 20, n_reads=200,
        )


def generate_all(outdir_base: str):
    """Generate synthetic data for all 5 plugin benchmarks."""
    plugins = {
        "plasmid_benchmark": generate_plasmid_data,
        "rnaseq_benchmark": generate_rnaseq_data,
        "amplicon_benchmark": generate_amplicon_data,
        "wgs_benchmark": generate_wgs_data,
        "metatranscriptomics_benchmark": generate_metatranscriptomics_data,
    }
    for name, fn in plugins.items():
        outdir = os.path.join(outdir_base, name)
        print(f"Generating {name} data...")
        fn(outdir)
        print(f"  Done: {outdir}/data/")


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic benchmark data")
    parser.add_argument("--all", action="store_true", help="Generate all 5 plugins")
    parser.add_argument("--plugin", choices=[
        "plasmid", "rnaseq", "amplicon", "wgs", "metatranscriptomics"
    ], help="Generate a specific plugin's data")
    parser.add_argument("--outdir", default="bench/fixtures/",
                        help="Base output directory (default: bench/fixtures/)")
    args = parser.parse_args()

    if args.all:
        generate_all(args.outdir)
    elif args.plugin:
        mapping = {
            "plasmid": generate_plasmid_data,
            "rnaseq": generate_rnaseq_data,
            "amplicon": generate_amplicon_data,
            "wgs": generate_wgs_data,
            "metatranscriptomics": generate_metatranscriptomics_data,
        }
        outdir = os.path.join(args.outdir, f"{args.plugin}_benchmark")
        mapping[args.plugin](outdir)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
