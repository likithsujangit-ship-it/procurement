"""
Unit Tests for 3-Tier Structure Preservation, Dynamic Budget Scaling, and Multi-Chunk Context Splitting.
Verifies that table lines and metadata are never dropped in favor of prose, and context budget scales up to 20k chars.
"""

import pytest
from tools.intelligent_extractor.merger import classify_line_tier, truncate_text, HARD_CEILING_CHARS


def test_classify_line_tier():
    """Verify 3-tier line classification logic."""
    assert classify_line_tier("Item 1 | Fire Hose C-JET | 50 pcs | $120") == "STRUCTURED"
    assert classify_line_tier("1002\tRubber Hose\t10\t$50.00") == "STRUCTURED"
    assert classify_line_tier("=== EMAIL METADATA ===") == "METADATA"
    assert classify_line_tier("Date: 2026-07-21") == "METADATA"
    assert classify_line_tier("We are pleased to submit our quotation for your review.") == "NARRATIVE"


def test_narrative_lines_trimmed_first():
    """Verify prose paragraphs are trimmed first while preserving all table lines."""
    struct_lines = [f"Item {i} | Product {i} | Qty {i*10} | Price ${i*5}" for i in range(1, 20)]
    prose_lines = [f"This is prose narrative paragraph line {i} explaining terms and conditions in detail." for i in range(1, 100)]
    
    full_text = "=== EMAIL METADATA ===\nDate: 2026-07-21\n\n=== BODY ===\n" + "\n".join(prose_lines) + "\n\n=== TABLE ===\n" + "\n".join(struct_lines)
    
    result = truncate_text(full_text, max_tokens=1000)  # max_chars = 4000
    assert isinstance(result, str)
    
    # Assert all structured table lines are preserved
    for s_line in struct_lines:
        assert s_line in result


def test_dynamic_budget_scaling_up_to_20k():
    """Verify max_chars scales dynamically up to 20,000 when structured content is 10,752 chars."""
    # Create ~10,000 chars of structured table rows
    struct_lines = [f"Item {i:04d} | Heavy Duty Industrial Fire Hose Model FH-{i:04d} | Quantity {i*5} units | Unit Price ${i*12.50:.2f} | Total ${i*5*12.50:.2f}" for i in range(1, 100)]
    struct_text = "\n".join(struct_lines)
    
    full_text = "=== EMAIL METADATA ===\nPO Number: PO-998877\nDate: 2026-07-21\n\n=== ATTACHMENT ===\n" + struct_text
    
    # initial max_tokens=1800 -> max_chars = 7200, but structured text is ~10,500 chars
    result = truncate_text(full_text, max_tokens=1800)
    
    assert isinstance(result, str)
    # Verify no middle truncation occurred
    assert "...[TRUNCATED MIDDLE STRUCTURED CONTEXT]..." not in result
    for s_line in struct_lines[:10]:
        assert s_line in result
    for s_line in struct_lines[-10:]:
        assert s_line in result


def test_multi_chunk_splitting_over_20k():
    """Verify context splits into sequential chunks when structured text exceeds 20,000 chars."""
    struct_lines = [f"Item {i:04d} | High Pressure Stainless Steel Valve Assembly Type-V{i:04d} | Quantity {i*10} | Price ${i*25.00:.2f}" for i in range(1, 250)]
    struct_text = "\n".join(struct_lines)
    
    full_text = "=== EMAIL METADATA ===\nRFQ Number: RFQ-123456\nDate: 2026-07-21\n\n=== ATTACHMENT ===\n" + struct_text
    
    result = truncate_text(full_text, max_tokens=1800)
    
    assert isinstance(result, list)
    assert len(result) >= 2
    # Verify each chunk contains metadata header
    for chunk in result:
        assert "RFQ Number: RFQ-123456" in chunk
        assert "=== STRUCTURED CONTEXT (CHUNK) ===" in chunk
