"""
Inline SVG illustrations for each of the 5 evaluation criteria.
Each criterion has a side-by-side "Good" vs "Bad" example so evaluators
can see what the criterion means at a glance.
"""

# Common SVG settings
NODE_GOOD = "#10b981"     # emerald
NODE_BAD = "#ef4444"      # red
NODE_NEUTRAL = "#3b82f6"  # blue
NODE_GHOST = "#cbd5e1"    # slate-300
EDGE = "#64748b"          # slate-500
BG_GOOD = "#ecfdf5"
BG_BAD = "#fef2f2"


def _frame(title, w=300, h=210, bg="#fff"):
    return f"""
    <rect width="{w}" height="{h}" fill="{bg}" rx="8"/>
    <text x="{w//2}" y="20" text-anchor="middle" font-family="system-ui,sans-serif"
          font-size="13" font-weight="700" fill="#0f172a">{title}</text>
    """


def _node(cx, cy, label, color=NODE_NEUTRAL, r=22, font_size=10):
    return f"""
    <circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}" stroke="#0f172a" stroke-width="1"/>
    <text x="{cx}" y="{cy+3}" text-anchor="middle" font-family="system-ui,sans-serif"
          font-size="{font_size}" fill="white" font-weight="600">{label}</text>
    """


def _edge(x1, y1, x2, y2, color=EDGE, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ''
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="1.5"{d}/>'


# ============================================================================
# 1. Structural Coherence (SC)
# ============================================================================
SC_SVG = f"""
<svg width="640" height="220" viewBox="0 0 640 220" xmlns="http://www.w3.org/2000/svg">
  <g transform="translate(0,0)">
    {_frame("✓ GOOD — clean hierarchy", 310, 220, BG_GOOD)}
    <!-- Good: balanced 3-level tree -->
    {_edge(155, 70, 80, 130)}
    {_edge(155, 70, 155, 130)}
    {_edge(155, 70, 230, 130)}
    {_edge(80, 130, 50, 180)}
    {_edge(80, 130, 110, 180)}
    {_edge(155, 130, 155, 180)}
    {_edge(230, 130, 200, 180)}
    {_edge(230, 130, 260, 180)}
    {_node(155, 70, "Topic", NODE_GOOD, 24, 11)}
    {_node(80, 130, "A", NODE_NEUTRAL, 16, 10)}
    {_node(155, 130, "B", NODE_NEUTRAL, 16, 10)}
    {_node(230, 130, "C", NODE_NEUTRAL, 16, 10)}
    {_node(50, 180, "a1", NODE_GHOST, 12, 9)}
    {_node(110, 180, "a2", NODE_GHOST, 12, 9)}
    {_node(155, 180, "b1", NODE_GHOST, 12, 9)}
    {_node(200, 180, "c1", NODE_GHOST, 12, 9)}
    {_node(260, 180, "c2", NODE_GHOST, 12, 9)}
  </g>
  <g transform="translate(330,0)">
    {_frame("✗ BAD — tangled / cyclic", 310, 220, BG_BAD)}
    <!-- Bad: messy crossings, child connecting back to root -->
    {_edge(155, 70, 80, 130)}
    {_edge(155, 70, 230, 130)}
    {_edge(80, 130, 230, 180)}
    {_edge(230, 130, 50, 180)}
    {_edge(50, 180, 230, 70, NODE_BAD, "3,3")}
    {_edge(155, 130, 80, 130)}
    {_node(155, 70, "Topic", NODE_BAD, 24, 11)}
    {_node(80, 130, "A", NODE_NEUTRAL, 16, 10)}
    {_node(155, 130, "?", NODE_BAD, 14, 11)}
    {_node(230, 130, "B", NODE_NEUTRAL, 16, 10)}
    {_node(50, 180, "a", NODE_GHOST, 12, 9)}
    {_node(230, 180, "b", NODE_GHOST, 12, 9)}
  </g>
</svg>
"""

# ============================================================================
# 2. Semantic Accuracy (SA)
# ============================================================================
SA_SVG = f"""
<svg width="640" height="220" viewBox="0 0 640 220" xmlns="http://www.w3.org/2000/svg">
  <g transform="translate(0,0)">
    {_frame("✓ GOOD — node says what text says", 310, 220, BG_GOOD)}
    <text x="155" y="50" text-anchor="middle" font-family="system-ui,sans-serif"
          font-size="9" fill="#475569" font-style="italic">Source: "Paris is the capital of France"</text>
    {_edge(155, 95, 90, 155)}
    {_edge(155, 95, 220, 155)}
    {_node(155, 90, "France", NODE_GOOD, 26, 10)}
    {_node(90, 155, "Paris", NODE_NEUTRAL, 24, 10)}
    {_node(220, 155, "capital", NODE_NEUTRAL, 22, 9)}
    <text x="155" y="200" text-anchor="middle" font-family="system-ui,sans-serif"
          font-size="9" fill="#065f46">→ relation faithful to text</text>
  </g>
  <g transform="translate(330,0)">
    {_frame("✗ BAD — wrong / invented relation", 310, 220, BG_BAD)}
    <text x="155" y="50" text-anchor="middle" font-family="system-ui,sans-serif"
          font-size="9" fill="#475569" font-style="italic">Source: "Paris is the capital of France"</text>
    {_edge(155, 95, 90, 155, NODE_BAD)}
    {_edge(155, 95, 220, 155, NODE_BAD)}
    {_node(155, 90, "Paris", NODE_BAD, 26, 10)}
    {_node(90, 155, "France", NODE_NEUTRAL, 26, 10)}
    {_node(220, 155, "London", NODE_BAD, 24, 10)}
    <text x="155" y="200" text-anchor="middle" font-family="system-ui,sans-serif"
          font-size="9" fill="#7f1d1d">→ wrong root + hallucinated node</text>
  </g>
</svg>
"""

# ============================================================================
# 3. Concept Centrality (CC)
# ============================================================================
CC_SVG = f"""
<svg width="640" height="220" viewBox="0 0 640 220" xmlns="http://www.w3.org/2000/svg">
  <g transform="translate(0,0)">
    {_frame("✓ GOOD — root = main subject", 310, 220, BG_GOOD)}
    <text x="155" y="55" text-anchor="middle" font-family="system-ui,sans-serif"
          font-size="9" fill="#475569" font-style="italic">Article about: Mount Everest</text>
    {_edge(155, 100, 75, 165)}
    {_edge(155, 100, 155, 165)}
    {_edge(155, 100, 235, 165)}
    {_node(155, 100, "Everest", NODE_GOOD, 32, 10)}
    {_node(75, 165, "height", NODE_NEUTRAL, 20, 9)}
    {_node(155, 165, "location", NODE_NEUTRAL, 20, 9)}
    {_node(235, 165, "climbers", NODE_NEUTRAL, 20, 9)}
  </g>
  <g transform="translate(330,0)">
    {_frame("✗ BAD — minor detail picked as root", 310, 220, BG_BAD)}
    <text x="155" y="55" text-anchor="middle" font-family="system-ui,sans-serif"
          font-size="9" fill="#475569" font-style="italic">Article about: Mount Everest</text>
    {_edge(155, 100, 75, 165)}
    {_edge(155, 100, 155, 165)}
    {_edge(155, 100, 235, 165)}
    {_node(155, 100, "1953", NODE_BAD, 32, 11)}
    {_node(75, 165, "Everest", NODE_NEUTRAL, 22, 9)}
    {_node(155, 165, "Hillary", NODE_NEUTRAL, 22, 9)}
    {_node(235, 165, "ascent", NODE_NEUTRAL, 22, 9)}
    <text x="155" y="200" text-anchor="middle" font-family="system-ui,sans-serif"
          font-size="9" fill="#7f1d1d">→ a date is not the main concept</text>
  </g>
</svg>
"""

# ============================================================================
# 4. Branch Completeness (BC)
# ============================================================================
BC_SVG = f"""
<svg width="640" height="220" viewBox="0 0 640 220" xmlns="http://www.w3.org/2000/svg">
  <g transform="translate(0,0)">
    {_frame("✓ GOOD — covers all key sections", 310, 220, BG_GOOD)}
    <text x="155" y="55" text-anchor="middle" font-family="system-ui,sans-serif"
          font-size="9" fill="#475569" font-style="italic">Text has 4 sections: Bio · Career · Awards · Death</text>
    {_edge(155, 100, 50, 170)}
    {_edge(155, 100, 110, 170)}
    {_edge(155, 100, 200, 170)}
    {_edge(155, 100, 260, 170)}
    {_node(155, 100, "Person", NODE_GOOD, 26, 10)}
    {_node(50, 170, "Bio", NODE_NEUTRAL, 18, 10)}
    {_node(110, 170, "Career", NODE_NEUTRAL, 22, 9)}
    {_node(200, 170, "Awards", NODE_NEUTRAL, 22, 9)}
    {_node(260, 170, "Death", NODE_NEUTRAL, 20, 9)}
  </g>
  <g transform="translate(330,0)">
    {_frame("✗ BAD — only 1 of 4 sections covered", 310, 220, BG_BAD)}
    <text x="155" y="55" text-anchor="middle" font-family="system-ui,sans-serif"
          font-size="9" fill="#475569" font-style="italic">Text has 4 sections: Bio · Career · Awards · Death</text>
    {_edge(155, 100, 105, 170)}
    {_edge(155, 100, 205, 170)}
    {_node(155, 100, "Person", NODE_BAD, 26, 10)}
    {_node(105, 170, "Career", NODE_NEUTRAL, 22, 9)}
    {_node(205, 170, "club", NODE_NEUTRAL, 20, 9)}
    <text x="50" y="175" font-family="system-ui,sans-serif" font-size="11" fill="#94a3b8">…</text>
    <text x="240" y="175" font-family="system-ui,sans-serif" font-size="11" fill="#94a3b8">…</text>
    <text x="155" y="200" text-anchor="middle" font-family="system-ui,sans-serif"
          font-size="9" fill="#7f1d1d">→ Bio, Awards, Death missing</text>
  </g>
</svg>
"""

# ============================================================================
# 5. Graph Clarity (GC)
# ============================================================================
GC_SVG = f"""
<svg width="640" height="220" viewBox="0 0 640 220" xmlns="http://www.w3.org/2000/svg">
  <g transform="translate(0,0)">
    {_frame("✓ GOOD — readable density", 310, 220, BG_GOOD)}
    {_edge(155, 75, 80, 130)}
    {_edge(155, 75, 155, 130)}
    {_edge(155, 75, 230, 130)}
    {_edge(80, 130, 60, 180)}
    {_edge(80, 130, 110, 180)}
    {_edge(230, 130, 210, 180)}
    {_edge(230, 130, 260, 180)}
    {_node(155, 75, "Root", NODE_GOOD, 22, 10)}
    {_node(80, 130, "A", NODE_NEUTRAL, 16, 10)}
    {_node(155, 130, "B", NODE_NEUTRAL, 16, 10)}
    {_node(230, 130, "C", NODE_NEUTRAL, 16, 10)}
    {_node(60, 180, "a1", NODE_GHOST, 12, 9)}
    {_node(110, 180, "a2", NODE_GHOST, 12, 9)}
    {_node(210, 180, "c1", NODE_GHOST, 12, 9)}
    {_node(260, 180, "c2", NODE_GHOST, 12, 9)}
  </g>
  <g transform="translate(330,0)">
    {_frame("✗ BAD — too dense (or too sparse)", 310, 220, BG_BAD)}
    <!-- Heavy fan-out -->
    <g stroke="{EDGE}" stroke-width="1">
      <line x1="155" y1="75" x2="35"  y2="160"/>
      <line x1="155" y1="75" x2="65"  y2="170"/>
      <line x1="155" y1="75" x2="95"  y2="180"/>
      <line x1="155" y1="75" x2="125" y2="185"/>
      <line x1="155" y1="75" x2="155" y2="190"/>
      <line x1="155" y1="75" x2="185" y2="185"/>
      <line x1="155" y1="75" x2="215" y2="180"/>
      <line x1="155" y1="75" x2="245" y2="170"/>
      <line x1="155" y1="75" x2="275" y2="160"/>
    </g>
    {_node(155, 75, "Root", NODE_BAD, 22, 10)}
    {_node(35, 160, "•", NODE_GHOST, 8, 9)}
    {_node(65, 170, "•", NODE_GHOST, 8, 9)}
    {_node(95, 180, "•", NODE_GHOST, 8, 9)}
    {_node(125, 185, "•", NODE_GHOST, 8, 9)}
    {_node(155, 190, "•", NODE_GHOST, 8, 9)}
    {_node(185, 185, "•", NODE_GHOST, 8, 9)}
    {_node(215, 180, "•", NODE_GHOST, 8, 9)}
    {_node(245, 170, "•", NODE_GHOST, 8, 9)}
    {_node(275, 160, "•", NODE_GHOST, 8, 9)}
    <text x="155" y="210" text-anchor="middle" font-family="system-ui,sans-serif"
          font-size="9" fill="#7f1d1d">→ 9 children at one level — overwhelming</text>
  </g>
</svg>
"""

CRITERION_SVG = {
    "SC": SC_SVG, "SA": SA_SVG, "CC": CC_SVG, "BC": BC_SVG, "GC": GC_SVG,
}
