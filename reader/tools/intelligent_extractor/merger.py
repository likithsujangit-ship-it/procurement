"""
Structure-aware context merger module.
Combines email metadata, body, and attachments while preserving tabular and structured lines.
Implements 3-tier line classification (STRUCTURED, METADATA, NARRATIVE), dynamic context
budget scaling up to a hard ceiling (20,000 chars), and multi-chunk context splitting.
"""

import logging
import re
from typing import Dict, Any, List, Union

logger = logging.getLogger(__name__)

TABLE_HEADER_PATTERN = re.compile(
    r'\b(item|description|part\s*#|part_number|qty|quantity|price|unit|total|hsn|sac|amount)\b',
    re.IGNORECASE
)

HARD_CEILING_CHARS = 20000  # Hard ceiling for single LLM call context (~5,000 tokens)


def classify_line_tier(line: str) -> str:
    """
    Classifies a single text line into one of three priority tiers:
    - 'STRUCTURED': Table rows, line items, pipe/tab/space-delimited items.
    - 'METADATA': Section headers, key-value metadata, dates, PO/RFQ IDs, contact info.
    - 'NARRATIVE': Prose, boilerplate, intro/outro text, terms & conditions.
    """
    s = line.strip()
    if not s:
        return "NARRATIVE"

    # METADATA: Section dividers, email headers
    if s.startswith("===") or s.startswith("---") or s.startswith("###"):
        return "METADATA"

    # STRUCTURED: Delimited tables, pipe/tab/space columns, item listing patterns
    if "|" in s or "\t" in s:
        return "STRUCTURED"
    if re.search(r'\S+\s{2,}\S+\s{2,}\S+', s):
        return "STRUCTURED"
    if TABLE_HEADER_PATTERN.search(s):
        return "STRUCTURED"
    if re.search(r'\b(?:\d+|[A-Z0-9-]{3,15})\s+.*?\s+\d+(?:\.\d+)?\s+(?:pcs|nos|kg|mtr|sets|units|ea)?\s+(?:\d+(?:\.\d+)?|\$|₹|INR)', s, re.I):
        return "STRUCTURED"

    # METADATA: Key-value pairs (e.g. "Date: 2026-07-21", "PO Number: PO-101")
    if ":" in s:
        key_part = s.split(":", 1)[0].strip()
        if len(key_part.split()) <= 4:
            return "METADATA"

    # METADATA: Standalone dates, GSTINs, emails, phone numbers
    if re.search(r'\b(?:\d{4}[/-]\d{1,2}[/-]\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b', s) or \
       re.search(r'\b\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z0-9]{1}[Z]{1}[A-Z0-9]{1}\b', s) or \
       re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', s):
        return "METADATA"

    return "NARRATIVE"


def truncate_text(text: str, max_tokens: int = 1800) -> Union[str, List[str]]:
    """
    Structure-aware truncation ensuring context fits within budget using 3-tier priority.
    - Tier 1: STRUCTURED & Tier 2: METADATA are NEVER dropped when trimming NARRATIVE.
    - If STRUCTURED + METADATA > initial max_chars, dynamically scales max_chars up to HARD_CEILING (20,000 chars).
    - If STRUCTURED + METADATA > HARD_CEILING (20,000 chars), splits STRUCTURED items into multiple context chunks.
    """
    initial_max_chars = max_tokens * 4
    if len(text) <= initial_max_chars:
        return text

    lines = text.splitlines()
    structured_lines = []
    metadata_lines = []
    narrative_lines = []

    for idx, line in enumerate(lines):
        tier = classify_line_tier(line)
        if tier == "STRUCTURED":
            structured_lines.append((idx, line))
        elif tier == "METADATA":
            metadata_lines.append((idx, line))
        else:
            narrative_lines.append((idx, line))

    struct_len = sum(len(l) + 1 for _, l in structured_lines)
    meta_len = sum(len(l) + 1 for _, l in metadata_lines)
    required_len = struct_len + meta_len

    # Log exact line classification audit ranges
    struct_indices = [idx for idx, _ in structured_lines]
    meta_indices = [idx for idx, _ in metadata_lines]
    narr_indices = [idx for idx, _ in narrative_lines]
    logger.info(
        f"3-Tier Context Audit: {len(structured_lines)} STRUCTURED lines (range: {struct_indices[0] if struct_indices else 'N/A'}-{struct_indices[-1] if struct_indices else 'N/A'}), "
        f"{len(metadata_lines)} METADATA lines (range: {meta_indices[0] if meta_indices else 'N/A'}-{meta_indices[-1] if meta_indices else 'N/A'}), "
        f"{len(narrative_lines)} NARRATIVE lines (range: {narr_indices[0] if narr_indices else 'N/A'}-{narr_indices[-1] if narr_indices else 'N/A'})."
    )

    # Case 1: Required (STRUCTURED + METADATA) <= initial_max_chars
    if required_len <= initial_max_chars:
        remaining_budget = initial_max_chars - required_len
        kept_narrative = []
        curr_narr_len = 0
        for idx, line in narrative_lines:
            if curr_narr_len + len(line) + 1 <= remaining_budget:
                kept_narrative.append(idx)
                curr_narr_len += len(line) + 1
            else:
                break

        kept_indices = set(struct_indices + meta_indices + kept_narrative)
        final_lines = [line for idx, line in enumerate(lines) if idx in kept_indices]
        dropped_count = len(lines) - len(final_lines)
        logger.info(f"Structure-aware truncation: preserved all STRUCTURED & METADATA lines, trimmed {dropped_count} NARRATIVE lines to fit {initial_max_chars} chars.")
        return "\n".join(final_lines)

    # Case 2: Required (STRUCTURED + METADATA) > initial_max_chars BUT <= HARD_CEILING_CHARS (20,000)
    if required_len <= HARD_CEILING_CHARS:
        logger.warning(
            f"Document structured & metadata content ({required_len} chars) exceeds initial max_chars ({initial_max_chars}). "
            f"Dynamically expanding max_chars to {required_len} (hard ceiling: {HARD_CEILING_CHARS})."
        )
        kept_indices = set(struct_indices + meta_indices)
        final_lines = [line for idx, line in enumerate(lines) if idx in kept_indices]
        logger.info(f"Dynamically expanded context: preserved all {len(final_lines)} STRUCTURED & METADATA lines without middle truncation.")
        return "\n".join(final_lines)

    # Case 3: Required (STRUCTURED + METADATA) > HARD_CEILING_CHARS (20,000) -> Split into multi-chunk context
    logger.warning(
        f"Structured + Metadata content ({required_len} chars) exceeds HARD_CEILING ({HARD_CEILING_CHARS} chars). "
        "Splitting table rows into sequential context chunks to guarantee zero item row loss."
    )

    metadata_text = "\n".join([line for _, line in metadata_lines])
    meta_chunk_len = len(metadata_text) + 2
    available_struct_budget = max(2000, HARD_CEILING_CHARS - meta_chunk_len)

    chunks = []
    curr_struct_chunk = []
    curr_chunk_len = 0

    for idx, line in structured_lines:
        line_cost = len(line) + 1
        if curr_chunk_len + line_cost > available_struct_budget and curr_struct_chunk:
            chunk_content = metadata_text + "\n\n=== STRUCTURED CONTEXT (CHUNK) ===\n" + "\n".join(curr_struct_chunk)
            chunks.append(chunk_content)
            curr_struct_chunk = []
            curr_chunk_len = 0

        curr_struct_chunk.append(line)
        curr_chunk_len += line_cost

    if curr_struct_chunk:
        chunk_content = metadata_text + "\n\n=== STRUCTURED CONTEXT (CHUNK) ===\n" + "\n".join(curr_struct_chunk)
        chunks.append(chunk_content)

    logger.info(f"Created {len(chunks)} sequential context chunks for complete item extraction.")
    return chunks


def merge_context(email_metadata: Dict[str, Any], email_body: str, attachments: List[Dict[str, str]]) -> Union[str, List[str]]:
    """
    Combines email and attachments into a unified markdown string or list of chunk strings.
    """
    lines = []
    lines.append("=== EMAIL METADATA ===")
    for k, v in email_metadata.items():
        lines.append(f"{k}: {v}")
    
    lines.append("\n=== EMAIL BODY ===")
    lines.append(email_body)
    
    for att in attachments:
        lines.append(f"\n=== ATTACHMENT: {att.get('filename', 'Unknown')} ===")
        lines.append(att.get('raw_text', ''))
        
    unified_text = "\n".join(lines)
    return truncate_text(unified_text)
