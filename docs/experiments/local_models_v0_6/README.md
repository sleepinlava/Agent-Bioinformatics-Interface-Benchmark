# Local Model Benchmarking — ABI-Bench v0.6-dev

> Generated: 2026-06-20
> Platform: RTX 4090 24GB VRAM
> Server: vLLM 0.8.5 with OpenAI-compatible API

## Summary

We benchmarked 3 local models (out of 7 planned) across 4 ABI-Bench groups (G1-G4)
to evaluate the scaffolding effect and validate the benchmark framework on
self-hosted models.

## Key Finding: Scaffolding Effect Confirmed

The scaffolding hypothesis predicts that **weak models benefit more from ABI
than strong models**. Our results strongly confirm this:

| Metric | Weak (avg) | Medium (4-bit) | Confirms? |
|--------|-----------|----------------|-----------|
| G3−G1 (ABI vs bare shell) | **+25.9%** | N/A | ✅ |
| G3−G2 (ABI vs generic tools) | **+29.6%** | +1.8% | ✅ |
| G3 score | **49.8%** | 25.2% | ✅ (weak > medium with ABI!) |

**Striking result**: Qwen3-4B (4B params, native) with ABI scores **53.5%** in G3,
outperforming Qwen3-14B (14B params, 4-bit) at 25.2%. This is NOT because 4B is
smarter — it's because ABI compensates for limited reasoning, and quantization
damages the 14B model's instruction-following capability.

## Quantization Warning

4-bit bitsandbytes quantization severely damages structured tool-calling performance:

- Qwen3-14B 4-bit G2 ≈ Qwen3-4B native G2 (both ~23%) — quantization drops 14B to 4B-level reasoning
- Qwen3-14B 4-bit G3−G2 = +1.8% vs Qwen3-4B native G3−G2 = +30.6%
- Cross-plugin tasks collapse: 4B scores 100% on T09/T13/T15/T17, 14B scores 0-13%

**Recommendation**: For ABI-Bench, use GGUF Q4_K_M or GPTQ/AWQ instead of bitsandbytes.

## Files

- `table1_main_results.tsv` — Overall leaderboard
- `table2_per_task_g3.tsv` — Per-task G3 comparison
- `table3_scaffolding_analysis.tsv` — Scaffolding effect metrics
