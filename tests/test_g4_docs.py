"""Tests for g4_docs.py — G4 information-matched documentation generator."""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "bench"))

from bench.harness.g4_docs import (
    generate_analysis_types_guide,
    generate_dry_run_guide,
    generate_execution_plan_guide,
    generate_inspection_guide,
    generate_reporting_guide,
    generate_provenance_guide,
    generate_standard_tables_guide,
    generate_diagnostic_guide,
    generate_g4_docs,
)

# All 7 plugin IDs
ALL_PLUGINS = [
    "metagenomic_plasmid",
    "metatranscriptomics",
    "rnaseq_expression",
    "amplicon_16s",
    "wgs_bacteria",
    "easymetagenome",
    "viral_viwrap",
]


class TestAnalysisTypesGuide:
    def test_mentions_all_seven_plugins(self):
        content = generate_analysis_types_guide()
        for plugin in ALL_PLUGINS:
            assert plugin in content, f"Missing plugin: {plugin}"

    def test_has_lifecycle_phases(self):
        content = generate_analysis_types_guide()
        assert "## Lifecycle Phases" in content
        assert "**Planning**" in content or "Planning" in content

    def test_non_empty(self):
        content = generate_analysis_types_guide()
        assert len(content) > 500


class TestDryRunGuide:
    def test_mentions_all_seven_plugins(self):
        content = generate_dry_run_guide()
        for plugin in ("metagenomic_plasmid", "metatranscriptomics", "rnaseq_expression",
                       "amplicon_16s", "wgs_bacteria", "easymetagenome", "viral_viwrap"):
            assert plugin in content, f"Missing plugin in dry-run guide: {plugin}"

    def test_has_artifact_sections(self):
        content = generate_dry_run_guide()
        assert "execution_plan.json" in content
        assert "provenance/" in content
        assert "tables/" in content


class TestStandardTablesGuide:
    def test_mentions_all_seven_plugins(self):
        content = generate_standard_tables_guide()
        for plugin in ALL_PLUGINS:
            assert plugin in content, f"Missing plugin tables: {plugin}"

    def test_has_easymetagenome_tables(self):
        content = generate_standard_tables_guide()
        assert "taxonomy_abundance.tsv" in content
        assert "functional_abundance.tsv" in content

    def test_has_viral_viwrap_tables(self):
        content = generate_standard_tables_guide()
        assert "virus_summary.tsv" in content
        assert "viral_abundance.tsv" in content


class TestAllGuides:
    def test_all_guides_non_empty(self):
        guides = [
            generate_analysis_types_guide,
            generate_dry_run_guide,
            generate_execution_plan_guide,
            generate_inspection_guide,
            generate_reporting_guide,
            generate_provenance_guide,
            generate_standard_tables_guide,
            generate_diagnostic_guide,
        ]
        for gen in guides:
            content = gen()
            assert len(content) > 100, f"{gen.__name__} is too short ({len(content)} chars)"


class TestGenerateG4Docs:
    def test_generates_eight_files(self, tmp_path):
        paths = generate_g4_docs(tmp_path)
        assert len(paths) == 8
        assert (tmp_path / "docs" / "analysis_types.md").exists()
        assert (tmp_path / "docs" / "diagnostic_guide.md").exists()
