"""Single source of truth for the seven box designs and their allowed captions.

Every person has exactly one caption; the visual category is determined by it.
The names in this module are display-only labels, not risk assessments.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    key: str
    name_zh: str
    captions: tuple[str, ...]
    edge: tuple[int, int, int]     # BGR
    accents: tuple[int, int, int]
    caption_bg: tuple[int, int, int]
    caption_fg: tuple[int, int, int]


WHITE = (245, 245, 245)
RED = (51, 57, 245)
YELLOW = (85, 230, 255)
BLUE = (255, 145, 40)
BLACK = (7, 7, 9)

CATEGORIES = (
    Category("IRRELEVANT", "无关人员", ("IRRELEVANT",), WHITE, WHITE, WHITE, BLACK),
    Category("THREAT", "威胁人员", ("THREAT",), RED, RED, RED, WHITE),
    Category("YELLOW", "特殊关注人员", ("ADMIN", "PRIMARY ASSET", "SECONDARY ASSET", "CONTINGENCY"), YELLOW, YELLOW, YELLOW, BLACK),
    Category("BLUE", "政府执行人员", ("ASSET CATALYST",), BLUE, BLUE, BLUE, BLACK),
    Category("ANALOG", "模拟接口", ("ANALOG INTERFACE", "ROOT"), BLACK, YELLOW, BLACK, YELLOW),
    Category("RELEVANT", "政府相关者", ("RELEVANT-ONE", "RELEVANT-TWO", "RELEVANT-THREE", "RELEVANT-OTHER"), BLUE, WHITE, BLUE, WHITE),
    Category("IRRELEVANT_THREAT", "无关威胁人员", ("IRRELEVANT THREAT",), WHITE, RED, WHITE, RED),
)
CATEGORY_BY_KEY = {category.key: category for category in CATEGORIES}
CAPTION_TO_CATEGORY = {caption: category for category in CATEGORIES for caption in category.captions}
LABELS = tuple(CAPTION_TO_CATEGORY)

# Automatic migration of original v1 labels, preserving a pre-migration backup.
LEGACY_LABEL_MAP = {
    "IRRELEVANT": "IRRELEVANT",
    "THREAT": "THREAT",
    "CONTINGENCY": "ADMIN",  # Former owner's yellow designation becomes the new default.
    "INDIGO": "ASSET CATALYST",  # Original blue designation.
    "ASSET": "ASSET CATALYST",   # Previous version split this one label.
    "CATALYST": "ASSET CATALYST",
}


def category_for(label: str) -> Category:
    return CAPTION_TO_CATEGORY.get(label, CATEGORY_BY_KEY["IRRELEVANT"])


def normalized_label(label: str) -> str:
    return LEGACY_LABEL_MAP.get(label, label)
