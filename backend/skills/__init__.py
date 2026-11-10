"""Pre-evaluation skills: model calling conventions, document gating,
figure captioning and context-window chunking.

Everything that talks to the local model goes through `call_qwen`/`qwen_kwargs`
so the thinking mode, context size and thread count are the same for every
report. That is what makes CPU grading reproducible: two runs of the same PDF
on the same machine get the same budget.
"""
from skills.qwen_skills import (
    MALICIOUS_PATTERNS,
    ContextChunkSkill,
    PreEvalSkill,
    VisionAltTextSkill,
    call_qwen,
    document_char_budget,
    qwen_kwargs,
)

__all__ = [
    "MALICIOUS_PATTERNS",
    "ContextChunkSkill",
    "PreEvalSkill",
    "VisionAltTextSkill",
    "call_qwen",
    "document_char_budget",
    "qwen_kwargs",
]
