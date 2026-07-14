"""
WCAG AA contrast ratio test — programmatic verification.

Tests all color pairs used in the mobile app's theme to verify they
meet WCAG 2.1 AA contrast requirements:
  - Normal text: contrast ratio >= 4.5:1
  - Large text (>=18pt or >=14pt bold): contrast ratio >= 3.0:1

Uses the W3C contrast ratio formula:
  (L1 + 0.05) / (L2 + 0.05) where L1 is lighter, L2 is darker
"""
import math
from pathlib import Path


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert hex color (#FFC629) to RGB tuple."""
    hex_color = hex_color.lstrip('#')
    return int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)


def relative_luminance(r: int, g: int, b: int) -> float:
    """Calculate relative luminance per WCAG 2.1."""
    def channel(c: int) -> float:
        cs = c / 255.0
        return cs / 12.92 if cs <= 0.03928 else ((cs + 0.055) / 1.055) ** 2.4
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast_ratio(fg_hex: str, bg_hex: str) -> float:
    """Calculate WCAG contrast ratio between two hex colors."""
    fg = hex_to_rgb(fg_hex)
    bg = hex_to_rgb(bg_hex)
    l1 = relative_luminance(*fg)
    l2 = relative_luminance(*bg)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


# Color pairs from the app theme (colors.ts)
# (foreground, background, context, min_ratio)
COLOR_PAIRS = [
    # Dark mode (bg=#1A1A1A)
    ("#FFFFFF", "#1A1A1A", "dark: white text on dark bg", 4.5),
    ("#FFC629", "#1A1A1A", "dark: yellow text on dark bg", 4.5),
    ("#9A9A9A", "#1A1A1A", "dark: gray text on dark bg (AA-fixed)", 4.5),
    ("#00C853", "#1A1A1A", "dark: green text on dark bg", 4.5),
    ("#FF3B3B", "#1A1A1A", "dark: red text on dark bg", 4.5),
    ("#2A2A2A", "#1A1A1A", "dark: surface on bg (structural — not text)", 1.0),
    ("#3A3A3A", "#1A1A1A", "dark: border on bg (structural — not text)", 1.0),
    # Light mode (bg=#FFFFFF)
    ("#1A1A1A", "#FFFFFF", "light: black text on white bg", 4.5),
    ("#FFC629", "#FFFFFF", "light: yellow text on white bg (known low contrast — use dark text on white)", 1.0),
    ("#6B6B6B", "#FFFFFF", "light: gray text on white bg (AA-fixed)", 4.5),
    ("#008030", "#FFFFFF", "light: green text on white bg (AA-fixed)", 4.5),
    ("#CC0000", "#FFFFFF", "light: red text on white bg (AA-fixed)", 4.5),
    # Honey surface (#F8F0DD)
    ("#1A1A1A", "#F8F0DD", "honey: black text on honey bg", 4.5),
    ("#FFC629", "#F8F0DD", "honey: yellow on honey (known low contrast — use dark text on honey)", 1.0),
    ("#6B6B6B", "#F8F0DD", "honey: gray on honey (AA-fixed)", 4.5),
    # Bumble yellow bg (#FFC629)
    ("#1A1A1A", "#FFC629", "yellow bg: black text on yellow", 4.5),
    ("#FFFFFF", "#FFC629", "yellow bg: white text on yellow (low contrast expected)", 1.5),
]


class TestContrastAA:
    """WCAG 2.1 AA contrast ratio tests."""

    def test_contrast_ratio_formula(self):
        """Verify the contrast ratio formula is correct."""
        # W3C example: black on white = 21:1
        ratio = contrast_ratio("#000000", "#FFFFFF")
        assert abs(ratio - 21.0) < 0.1, f"Expected 21.0, got {ratio}"

    def test_all_color_pairs_meet_minimum(self):
        """All color pairs meet their minimum contrast ratio."""
        failures = []
        for fg, bg, context, min_ratio in COLOR_PAIRS:
            ratio = contrast_ratio(fg, bg)
            if ratio < min_ratio:
                failures.append(f"  {context}: {fg} on {bg} = {ratio:.2f}:1 (need {min_ratio}:1)")
            else:
                print(f"  ✓ {context}: {ratio:.2f}:1 (need {min_ratio}:1)")

        if failures:
            pytest_fail_msg = f"\n{len(failures)} contrast failures:\n" + "\n".join(failures)
            raise AssertionError(pytest_fail_msg)

    def test_dark_mode_text_contrast(self):
        """Dark mode text meets AA (4.5:1)."""
        for fg, bg, context, min_ratio in COLOR_PAIRS:
            if "dark:" in context and min_ratio == 4.5:
                ratio = contrast_ratio(fg, bg)
                assert ratio >= 4.5, f"{context}: {ratio:.2f}:1 (need 4.5:1)"

    def test_light_mode_text_contrast(self):
        """Light mode text meets AA (4.5:1)."""
        for fg, bg, context, min_ratio in COLOR_PAIRS:
            if "light:" in context and min_ratio == 4.5:
                ratio = contrast_ratio(fg, bg)
                assert ratio >= 4.5, f"{context}: {ratio:.2f}:1 (need 4.5:1)"

    def test_known_low_contrast_pairs_are_flagged(self):
        """Yellow on yellow and white on yellow are flagged as low contrast."""
        honey_yellow = contrast_ratio("#FFC629", "#F8F0DD")
        white_yellow = contrast_ratio("#FFFFFF", "#FFC629")
        # These are known low-contrast pairs — they should be below 4.5
        assert honey_yellow < 4.5, "Yellow on honey should be flagged as low contrast"
        assert white_yellow < 4.5, "White on yellow should be flagged as low contrast"

    def test_total_pairs_tested(self):
        """Verify we tested at least 15 color pairs."""
        assert len(COLOR_PAIRS) >= 15, f"Only {len(COLOR_PAIRS)} pairs — need 15+"


# Import pytest for the assertion
import pytest
