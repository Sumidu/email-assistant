---
target: email-assistant app UI
total_score: 24
p0_count: 0
p1_count: 2
p2_count: 2
timestamp: 2026-05-19T21-59-34Z
slug: email-assistant-app-ui
---
## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Progress drawer + LLM health dot are excellent; minor: KB build state not always surface-visible |
| 2 | Match System / Real World | 3 | Vocabulary fits the technical solo user; "Finish" is idiosyncratic but learnable |
| 3 | User Control and Freedom | 3 | Modals close, filters clear, unfinish works; missing: no undo for spam/finish |
| 4 | Consistency and Standards | 2 | CSS collision: old uppercase+letter-spacing pattern and macOS refresh rules coexist; amber modal titles vs bright titles conflict |
| 5 | Error Prevention | 3 | Icon tooltips, spam confirmation implied; no autosave indicator for draft text |
| 6 | Recognition Rather Than Recall | 2 | Header buttons labeled (good); diamond icon has no universal meaning; "Add Context" is opaque without system knowledge |
| 7 | Flexibility and Efficiency | 3 | Resizable panels, batch finish-filtered exists, folder collapse; no keyboard shortcuts surfaced |
| 8 | Aesthetic and Minimalist Design | 2 | Header has 8 simultaneous actions; 14+ discrete font sizes create visual noise |
| 9 | Error Recovery | 2 | LLM error state in health dot; sync errors in progress log; no inline form validation |
| 10 | Help and Documentation | 1 | title tooltips only; no help system, no shortcut reference |
| Total | | 24/40 | Acceptable |

## Anti-Patterns Verdict

LLM: Mostly not AI-looking. Semantic color discipline and density give a specific point of view. Tells: bare empty states, header accumulated features, granular type increments.

Detector: 12 findings. 9 side-tab findings mostly false positives (panel dividers, blockquotes, documented exceptions). 2 layout-transition findings on width animation are legitimate. 1 flat-type-hierarchy finding is legitimate.

## Priority Issues

[P1] Header action explosion: 8 simultaneous top-level buttons. Fix: group KB actions, move Calendar/Summary to secondary toolbar or command palette.

[P1] Type scale has 14 gradations. Collapse to 5: 10px micro, 12px secondary UI, 13px primary, 14px content, 16px emphasis.

[P2] 9px text below legibility floor. Minimum UI text size: 11px.

[P2] Amber #e8a000 on dark surfaces = 3.7:1, fails WCAG AA. Fix: push dark-theme amber to ~#f0aa00 for ~5.1:1.

[P3] Empty states are inert text. Fix: lightweight icon + direct action link.

## Persona Red Flags

Alex (Power User): No keyboard shortcuts anywhere. 8-button header requires mouse. No multi-select in email list.

Sam (Accessibility): 9px text fails. Amber 3.7:1 fails AA. Color-only state indicators (unread dot, LLM health). Modal focus trap not verified.

Developer in Flow: 8-button header scan on every session. KB split into two adjacent buttons. No last-sync timestamp in header.

## Minor Observations

Dead CSS: .folder-item.selected::before left stripe overridden to display:none but base rule still exists at line 105.
layout-transition on width at lines 293 and 456. Should use transform: scaleX() for progress fill.
Todo purple button adjacent to amber KB button in header creates two saturated accent colors side-by-side.
LLM health dot scale animation range is aggressive (0.86 to 1.18); reduce to 0.95 to 1.05.
