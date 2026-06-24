from bench.harness.direct_agent import _build_tools, execute_tool


def _tool_names(group):
    return {tool["function"]["name"] for tool in _build_tools(group, {"run_shell": True})}


def test_g2_exposes_generic_command_tool_not_shell_label():
    assert "run_command" in _tool_names("G2")
    assert "bash" not in _tool_names("G2")
    assert "bash" in _tool_names("G1")


def test_non_abi_safety_block_does_not_leak_abi_cli(tmp_path):
    result = execute_tool(
        "run_command",
        {"command": "fastp -i reads.fastq -o clean.fastq"},
        tmp_path,
        group_id="G2",
    )

    assert "SAFETY BLOCK" in result
    assert "ABI" not in result
    assert "abi_cli" not in result


def test_abi_safety_block_can_recommend_lifecycle(tmp_path):
    result = execute_tool(
        "bash",
        {"command": "fastp -i reads.fastq -o clean.fastq"},
        tmp_path,
        group_id="G3",
    )

    assert "ABI CLI" in result
    assert "dry-run" in result
