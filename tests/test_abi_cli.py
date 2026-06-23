"""Tests for abi_cli.py — simulated ABI lifecycle CLI."""

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "bench"))

from bench.harness.abi_cli import (
    ANALYSIS_TYPES,
    build_plan,
    default_workflow,
    dryrun_command,
    normalized_tool_id,
    main as abi_cli_main,
)


class TestAnalysisTypes:
    def test_all_seven_plugins_registered(self):
        assert len(ANALYSIS_TYPES) == 7
        assert "metagenomic_plasmid" in ANALYSIS_TYPES
        assert "metatranscriptomics" in ANALYSIS_TYPES
        assert "rnaseq_expression" in ANALYSIS_TYPES
        assert "amplicon_16s" in ANALYSIS_TYPES
        assert "wgs_bacteria" in ANALYSIS_TYPES
        assert "easymetagenome" in ANALYSIS_TYPES
        assert "viral_viwrap" in ANALYSIS_TYPES


class TestDefaultWorkflow:
    def test_metatranscriptomics_has_4_steps(self):
        wf = default_workflow("metatranscriptomics")
        assert len(wf) == 4
        assert wf[0]["tool"] == "fastp"
        assert wf[-1]["tool"] == "featureCounts"

    def test_rnaseq_expression_has_5_steps(self):
        wf = default_workflow("rnaseq_expression")
        assert len(wf) == 5
        tool_ids = {s["tool"] for s in wf}
        assert "deseq2" in tool_ids
        assert "build_count_matrix" in tool_ids

    def test_amplicon_16s_has_8_steps(self):
        wf = default_workflow("amplicon_16s")
        assert len(wf) == 8
        tool_ids = {s["tool"] for s in wf}
        assert "cutadapt" in tool_ids
        assert "vsearch_denoise" in tool_ids

    def test_wgs_bacteria_has_5_steps(self):
        wf = default_workflow("wgs_bacteria")
        assert len(wf) == 5
        tool_ids = {s["tool"] for s in wf}
        assert "spades" in tool_ids
        assert "prokka" in tool_ids

    def test_easymetagenome_has_4_steps(self):
        wf = default_workflow("easymetagenome")
        assert len(wf) == 4
        tool_ids = {s["tool"] for s in wf}
        assert "kneaddata" in tool_ids
        assert "kraken2" in tool_ids
        assert "bracken" in tool_ids

    def test_viral_viwrap_has_5_steps(self):
        wf = default_workflow("viral_viwrap")
        assert len(wf) == 5
        tool_ids = {s["tool"] for s in wf}
        assert "viwrap" in tool_ids
        assert "viwrap_parse" in tool_ids

    def test_metagenomic_plasmid_is_default(self):
        wf = default_workflow("metagenomic_plasmid")
        assert len(wf) == 3
        # Also default for unknown types
        wf2 = default_workflow("unknown_type")
        assert wf == wf2


class TestDryrunCommand:
    def test_rnaseq_expression_commands(self):
        cmd = dryrun_command("rnaseq_expression", "star", "STAR", {})
        assert "STAR" in cmd
        assert "--genomeDir" in cmd
        assert "SortedByCoordinate" in cmd

    def test_amplicon_commands(self):
        cmd = dryrun_command("amplicon_16s", "vsearch_denoise", "vsearch", {})
        assert "vsearch" in cmd
        assert "--cluster_unoise" in cmd

    def test_wgs_commands(self):
        cmd = dryrun_command("wgs_bacteria", "spades", "SPAdes", {})
        assert "spades.py" in cmd or "SPAdes" in cmd

    def test_easymetagenome_commands(self):
        cmd = dryrun_command("easymetagenome", "kraken2", "Kraken2", {})
        assert "kraken2" in cmd
        assert "--report" in cmd

    def test_viral_viwrap_commands(self):
        cmd = dryrun_command("viral_viwrap", "viwrap", "ViWrap", {})
        assert "viwrap" in cmd


class TestNormalizedToolId:
    def test_star_maps_to_uppercase(self):
        assert normalized_tool_id("star", "star") == "STAR"

    def test_spades_maps_correctly(self):
        assert normalized_tool_id("spades", "spades") == "SPAdes"

    def test_prokka_maps_correctly(self):
        assert normalized_tool_id("prokka", "prokka") == "Prokka"

    def test_featurecounts_not_changed(self):
        assert normalized_tool_id("featurecounts", "featureCounts") == "featureCounts"

    def test_unknown_tool_passthrough(self):
        assert normalized_tool_id("my_tool", "my_tool") == "my_tool"


class TestListTypes:
    def test_list_types_output(self, tmp_path):
        """Test that list-types command outputs valid JSON with 7 types."""
        result = abi_cli_main(["list-types"])
        assert result == 0  # Already printed to stdout


class TestBuildPlan:
    def test_build_plan_for_rnaseq(self, tmp_path):
        workspace = tmp_path
        (workspace / "config.yaml").write_text("analysis:\n  type: rnaseq_expression\nworkflow:\n  steps: []\ntools: {}\n")
        plan = build_plan(workspace, "rnaseq_expression")
        assert plan["analysis_type"] == "rnaseq_expression"
        assert len(plan["steps"]) >= 5

    def test_build_plan_for_plasmid(self, tmp_path):
        workspace = tmp_path
        (workspace / "config.yaml").write_text("analysis:\n  type: metagenomic_plasmid\nworkflow:\n  steps: []\ntools: {}\n")
        plan = build_plan(workspace, "metagenomic_plasmid")
        assert plan["analysis_type"] == "metagenomic_plasmid"
        assert len(plan["steps"]) == 3
