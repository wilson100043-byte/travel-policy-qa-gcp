from datetime import date

import pytest

from app.documents import parse_document


POLICY = """---
title: 住宿費規定
effective_from: 2026-07-01
effective_to:
---
# 標題
## 住宿上限
每人每晚 2,500 元。
## 憑證
須附發票。
"""


def test_frontmatter_sections_and_effective_dates():
    chunks = parse_document(POLICY, "lodging.md")
    assert [item.section for item in chunks] == ["住宿上限", "憑證"]
    assert chunks[0].document == "住宿費規定"
    assert chunks[0].is_current(date(2026, 11, 22))
    assert not chunks[0].is_current(date(2026, 6, 30))


def test_expired_version_and_invalid_dates():
    old = POLICY.replace("effective_from: 2026-07-01", "effective_from: 2025-01-01").replace(
        "effective_to:", "effective_to: 2026-06-30"
    )
    assert not parse_document(old, "old.md")[0].is_current(date(2026, 7, 1))
    with pytest.raises(ValueError, match="invalid effective date"):
        parse_document(POLICY.replace("2026-07-01", "July 1"), "bad.md")
