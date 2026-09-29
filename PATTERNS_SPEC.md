# Bullish Chart-Pattern Detection Spec

Source of truth for the pattern scanner. Every rule below is distilled from
**Bulkowski, _Encyclopedia of Chart Patterns_ (2nd ed.)** identification tables,
cross-checked against the Fidelity Technical Analysis slides. Bullish patterns
only (entry signals). A pattern is reported **TRIGGERED** only on a confirmed
breakout; otherwise **FORMING**. Every flag prints its measured numbers so a
human can verify against the candlestick chart.

Universe is pluggable (a symbol list); currently the genuine-IPO set.

---

## Engine layers

1. **Swing pivots (zigzag).** Alternating minor highs / minor lows, confirmed
   only when price reverses from the last pivot by more than an ATR-scaled
   threshold `thr = clip(k * median(ATR/close), 3%, 12%)` (k≈2). This is how the
   eye ignores noise and sees real turning points. All shape rules below are
   measured off these pivots. Bulkowski defines every pattern via minor
   highs/lows, touches, troughs, peaks, rims, necklines.
2. **Breakout confirmation.** Report TRIGGERED only when the latest close clears
   the relevant level (resistance line / rim / neckline / confirmation peak).
   Volume expansion and candle strength raise confidence.
3. **Shape classifiers** (below), one per pattern.
4. **Candlestick grading** of the breakout bar (marubozu / engulfing / hammer /
   piercing / harami / doji) — never standalone, only to grade a breakout.

Common tolerances: `LEVEL_TOL` = 4% (two prices "at the same level"),
`FLAT_SLOPE` = ≤0.3%/bar (a line counts as horizontal).

---

## 1. High Tight Flag (HTF)   — Bulkowski ch.22, rank 1/23 (best performer)
- **Pole:** price rises ≥ **90%** (target 100%) in ≤ **~45 trading days** (<2 months).
- **Flag:** a consolidation after the pole that drifts down no more than **~25%**
  from the pole high; can be a brief 1–2 day spike down. Volume recedes (better).
- **Breakout:** close above the flag high.
- **Measure:** pole height added above the flag high (move after ≈ half the pole).
- IPO-critical: this is *the* fresh-listing momentum pattern.

## 2. Channel / Rectangle Bottom (upward breakout)   — Bulkowski ch.37
- **Two horizontal lines:** resistance from ≥2 pivot highs at ~same level, support
  from ≥2 pivot lows at ~same level (each within LEVEL_TOL; slopes ~flat).
- **Touches:** ≥2 of each line (≥4 total).
- **Breakout:** close above the resistance line.
- Tall & wide patterns and **heavy breakout volume** perform better. A strong
  no-wick (marubozu) breakout candle = high confidence (user's Image 1).
- **Measure:** rectangle height added above resistance.

## 3. Cup with Handle   — Bulkowski ch.9 (O'Neil)
- **Rise into it:** ≥ **30%** advance before the cup.
- **Cup:** **U-shaped** (not V); left and right rims at ~same price level (LEVEL_TOL).
- **Handle:** after the right rim, a small pullback that stays in the **upper half**
  of the cup (drifts down no lower than halfway); duration ≥ **5 trading days**.
- **Breakout:** close above the rim level.
- **Measure:** cup depth (right rim to cup bottom) added above the breakout.
- (User's Image 3.)

## 4. Rounding Bottom   — Bulkowski ch.39
- **Bowl:** pivot lows trace a smooth saucer — fit a parabola to the closes over
  the base; require concave-up (a>0), good fit (R²≥~0.6), and gentle (not a V).
- **Breakout:** close above the left rim (old high). Handle optional.
- **Measure:** right-lip-to-bottom depth added above the breakout.
- (User's Image 2 — Engineers India.)

## 5. Double Bottom   — Bulkowski ch.13–16
- **Two pivot lows** at ~same level (bottom-to-bottom variation ≤ ~6%, allow ≤10%),
  separated by **2–7 weeks** (≥ ~10 trading days), price not dropping below the
  left low in between.
- **Peak between:** the intervening pivot high is ≥ **10%** above the lows.
- **Confirmation (breakout):** close above that middle peak. *Not valid until then*
  (pre-confirmation failure rate ~64%).
- **Measure:** peak-height-over-lows added above the confirmation.

## 6. Triple Bottom   — Bulkowski ch.50
- **Three pivot lows** at ~same level (LEVEL_TOL), well separated by two peaks.
- Center low **not significantly below** the other two (else it's an inverse H&S).
- **Confirmation (breakout):** close above the highest peak between the lows.

## 7. Inverse Head-and-Shoulders   — Bulkowski ch.24
- **Three troughs:** left shoulder, head (lowest), right shoulder; head below both
  shoulders by a clear margin.
- **Symmetry:** shoulders at ~same price and ~equidistant in time from the head.
- **Neckline:** line joining the two peaks between the troughs.
- **Breakout:** close above the neckline (for an up-sloping neckline use the
  highest high in the pattern), usually on high volume.

## 8. Ascending Triangle   — Bulkowski ch.47
- **Flat top:** ≥2 pivot highs at ~same level (horizontal resistance).
- **Rising bottom:** ≥2 pivot lows that ascend (up-sloping support).
- Prices cross the pattern several times (filled, not white space).
- **Breakout:** close above the flat top. Prone to premature breakouts — require a
  decisive close. Better with heavy breakout volume.

## 9. Flag (bullish continuation)   — Bulkowski ch.21
- **Pole:** a steep, quick advance leading in.
- **Flag:** ≤ **3 weeks**, bounded by two ~parallel lines, drifting down/sideways
  (against the up-trend); receding volume. Longer than 3 weeks → triangle/rectangle.
- **Breakout:** close above the flag high (trend direction).
- **Measure:** half-staff — pole height added at breakout.

## 10. Falling Wedge (bullish)   — Bulkowski ch.52
- **Two down-sloping converging lines** (both slopes < 0; top steeper; they narrow).
- **Touches:** ≥5 alternating (≈3 one side, 2 the other).
- **Duration:** ≥ **3 weeks** (shorter → pennant), rarely > 4 months.
- **Breakout:** close above the upper (top) down-sloping line.

---

## Candlestick grading (breakout bar) — Fidelity slides
- **Marubozu / strong body:** body ≥ ~85% of range, tiny wicks — "very strong"
  breakout (user's emphasis).
- **Bullish engulfing:** up bar whose body fully engulfs the prior down bar's body.
- **Hammer / lower-tail:** long lower shadow (≥1.5× body, ≥50% of range), close in
  top half — repeated buying off lows (kept from v1; the one detector that worked).
- **Piercing line:** up bar closing above the midpoint of the prior down bar's body.
- **Bullish harami / doji:** small-body indecision after a move — annotate only.

These do not fire on their own; they grade a breakout ("channel breakout on a
bullish marubozu, 2.3× volume").

---

# Remaining bullish patterns (the rest of the book)

Learned from Bulkowski chapters, bullish only. Same engine (pivots → shape →
confirmed breakout → candle grade). Status TRIGGERED only on the confirming close.

## 11. Pennant   — ch.34
- A **steep pole** in, then a **small pennant** (two *converging* trend lines, a
  tiny wedge) that usually slopes against the trend; ≤ **3 weeks** (longer →
  symmetric triangle/wedge); receding volume.
- Breakout: close above the pennant's upper line. Half-staff (move after ≈ before).

## 12. Symmetrical Triangle (upward breakout)   — ch.49
- Two converging lines: **down-sloping top** (lower highs) + **up-sloping bottom**
  (higher lows), meeting at an apex. ≥2 touches each (≥4 total). Price fills the
  pattern (little white space). Volume recedes, very low before breakout.
- Duration > **3 weeks** (≤3 weeks = pennant). Bullish = close above the top line.

## 13. Pipe Bottom   — ch.35   **(weekly)**
- On the **weekly** chart: **two adjacent** weeks that both spike down unusually far
  (deeper than most spikes in the past year), large overlap, the weeks either side
  sitting near the pipe highs. Volume usually high on one/both spikes.
- Confirmation: close above the highest high of the 2-week pattern.

## 14. Horn Bottom   — ch.28   **(weekly)**
- On the **weekly** chart: **two down-spikes separated by ONE week** (the center
  week stays well above the spike lows) — an inverted horn. Spikes abnormally long.
- Confirmation: close above the highest high of the 3-week pattern.

## 15. Three Rising Valleys   — ch.46
- In an uptrend, **three minor lows in a row, each higher** than the prior; the
  three valleys similar in shape (don't mix wide + narrow).
- Confirmation: close above the highest high in the pattern.

## 16. Bump-and-Run Reversal Bottom   — ch.7
- **Lead-in:** a modest down-sloping trend line (~0–45°) over ≥ ~1 month; lead-in
  height = widest trendline-to-low distance in the first quarter.
- **Bump:** the decline steepens (~60°+), drops rapidly, rounds, and turns up;
  bump depth ≥ **2× lead-in height**.
- **Uphill run / breakout:** price closes back **above the down-sloping lead-in
  line**. Volume high at start, bump, and breakout. (A frying-pan / cup-like turn.)

## 17. Measured Move Up   — ch.33
- **First leg** up (in a channel), a **corrective retrace of 40–60%** of that leg,
  then a **second leg** up roughly paralleling the first, making a higher high.
  Avoid retraces > 80%. Bullish continuation.

## 18. Ascending Scallop   — ch.41
- A **J shape**: a left peak, a **rounded recession**, then a **higher right peak**.
  The two peaks NOT at the same price (else cup/double-top). U-shaped volume.
- Confirmation: close above the highest high in the pattern.

## 19. Gaps — Breakaway / Continuation (up)   — ch.23
- **Up gap:** today's low > yesterday's high.
- **Breakaway:** up-gap out of a consolidation on **high volume**, doesn't fill —
  starts a trend. **Continuation/runaway:** up-gap mid-uptrend on high volume.
- Ignore **area** gaps (fill in ≤1 week) and **exhaustion** gaps (end of trend,
  fill fast). Signal = a decisive up-gap on volume that stays open.

## 20. Diamond Bottom   — ch.11
- Prior downtrend. Price first **broadens** (higher highs + lower lows), then
  **narrows** (lower highs + higher lows) → a diamond (may lean). Volume recedes,
  surges on breakout.
- Breakout: close above the diamond's upper boundary.

## 21. Broadening Bottom   — ch.1
- Prior downtrend. **Megaphone**: up-sloping top line + down-sloping bottom line
  (diverging), ≥2 minor highs and ≥2 minor lows.
- Breakout: close above the formation's **highest high** (upward).

## 22. Island Reversal (Bottom)   — ch.30   (gap-based)
- Prices **gap down** into a small consolidation, then **gap up** near the same
  price level, leaving an "island". Up-gap on high volume = the bullish reversal.
- Confirmation: the up-gap / close above the island.

## 23. Complex Inverse Head-and-Shoulders   — ch.25
- Inverse H&S with **multiple shoulders and/or multiple heads**, symmetric about
  the (lowest) head in price and time; near-horizontal neckline.
- Breakout: close above the neckline (up-sloping → highest high head→right shoulder).
- (Detected as an extension of the Inverse H&S detector.)

## Excluded (NOT bullish)
- **Rectangle Top** (upward breakout) is functionally identical to the Channel
  detector (flat band + upside break) — already covered, not a separate detector.
- **Right-Angled Ascending Broadening Formation** — despite "ascending", Bulkowski
  classifies it **bearish** (breaks down through its flat base). Excluded.

## Weekly note
Pipe Bottom and Horn Bottom are defined by Bulkowski **on the weekly chart** and
perform best there — they belong to the weekly scan especially. All other patterns
run on both daily and weekly bars.
