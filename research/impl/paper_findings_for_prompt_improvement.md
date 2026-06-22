# Paper Findings → Agent Prompt Improvements

This document extracts key findings from ALL 27+ papers in the project knowledge base, organized by which agent prompt they should improve. Findings marked **[CZ-SPECIFIC]** are particularly important since the Czech market is primary.

---

## 1. Weather & Forecast Analyst (`fundamentals_analyst.py`)

### From Ber17 (Czech market study) **[CZ-SPECIFIC]**
- **Solar is the dominant variable RES in CZ**, not wind. Solar + load forecast errors are the *most statistically significant* determinants of CZ intraday price deviation from DA. Wind's individual effect is larger per MW but statistically weaker due to negligible installed capacity (~280 MW wind vs ~2,075 MW solar in CZ).
- **Wind forecast data is NOT published by the Czech TSO (ČEPS)**. Ber17 had to construct an AR(2) model to estimate wind forecasts. The agent should be aware that CZ wind data from ENTSO-E may be poor/unavailable and should not rely on it.
- Unlike solar (only daytime), **wind intermittency is present at night**, causing higher nighttime price fluctuations. For night delivery hours, any wind signal matters more than usual.
- **ČEPS load forecasts systematically underestimate actual load** — positive load forecast error occurs in >91% of observations. The agent should know this bias exists.

**Suggested prompt addition for CZ context:**
```
CZECH MARKET SPECIFICS (from Ber17):
- Solar + load forecast errors are the most significant CZ intraday price drivers
- Wind capacity is negligible (~280 MW) but wind effects are still statistically detectable
- Czech TSO (ČEPS) does not publish wind generation forecasts — use ENTSO-E data with caution
- ČEPS load forecasts systematically underestimate actual load (positive bias >91% of the time)
- Unlike solar, wind intermittency persists at night — any night-hour wind signal has outsized impact
```

### From Kie17 (German quarter-hourly, threshold model)
- Forecast error impact is **regime-dependent**: in high demand-quote regime (>1.2), the same forecast error moves prices much more than in normal regime
- **PV forecast errors matter most during solar ramping hours**: positive PV errors decrease prices in Q4 of hour 7 (sun ramping up), negative PV errors increase prices in Q1 of hour 18 (sun ramping down)
- The **"jigsaw pattern"** of 15-minute prices within each hour is systematic and caused by solar ramping — agents should not confuse this with noise

### From Kup22 (forecast-based speculative strategy)
- Already well-integrated into the prompt. Key addition: the strategy works **better with patient limit order logic** than aggressive market taking, because bid-ask spreads are large.

### From Hir22 (distribution forecasting)
- Merit-order slope affects not just price *level* but the *tail heaviness* of the distribution. Steep merit → heavier tails → more spike risk. This matters for confidence levels.
- As time-to-delivery decreases, tail heaviness *decreases* (not increases) — the distribution narrows closer to delivery.

---

## 2. System State Analyst (`social_media_analyst.py`)

### From Ber17 **[CZ-SPECIFIC]**
- Czech power sector is dominated by **thermal (mostly lignite: 43.5%) and nuclear (32%)** — combined 84% of generation and 69% of installed capacity. This is the merit order backbone.
- Gas is only 4% of generation but sits at the **right end of the merit order** — it's the price-setting source during peak hours.
- The CZ DA market is **coupled with SK, HU, and RO** since 2009-2014. But the CZ intraday market is NOT coupled (notice-board style, not continuous clearing like Germany).
- **70% of DA trades are OTC** (over the counter), only 30% go through OTE exchange.

**Suggested prompt addition for CZ generation mix:**
```
CZECH GENERATION MIX AND MERIT ORDER:
- Lignite: ~43.5% of generation — cheap baseload, NOT a tradable commodity (no reference price)
- Nuclear: ~32% of generation (Dukovany + Temelín) — 4,290 MW, inflexible baseload
- Combined lignite+nuclear = ~84% of production, 69% of capacity — this IS the Czech merit order floor
- Gas: only ~4% of generation but sits at the RIGHT END of the merit order — price-setting during peaks
- Solar: ~2,075 MW installed, ~2.5% of generation — the dominant variable RES
- Wind: ~280 MW installed, ~0.6% of generation — negligible but detectable at night
- Hydro+pumped: ~2,260 MW — provides flexibility, pumped storage acts as price smoother
- Czech generation is LONG (net exporter) — regularly exports surplus to neighbors
```

### From Ber17 **[CZ-SPECIFIC]** — Cross-border flows
- **50 Hertz (North/East Germany) is the key border for CZ** — highest ratio of RES generation and highest electricity import to CZ
- 50 Hertz "repeatedly imports more electricity than planned" and is "assumed to occasionally use Czech transmission border for transferring excess electricity from North to South Germany"
- Persistently greater import from Germany than planned can **subtly increase** CZ intraday prices (counter-intuitive — the German surplus flowing through CZ transmission creates congestion costs)

**Suggested prompt addition:**
```
CROSS-BORDER DYNAMICS FOR CZ:
- The 50 Hertz border (North/East Germany) is the most important for CZ price formation
- Germany frequently exports more than planned through CZ (loop flows from North to South DE)
- This excess import can paradoxically INCREASE CZ intraday prices due to congestion costs
- Czech intraday market is NOT coupled like EPEX — it uses a notice-board system where bids
  must be manually accepted, NOT continuously matched. This means lower liquidity and wider spreads
  than German EPEX continuous market.
```

### From Time_Evolution_of_Hurst_Exponent **[CZ-SPECIFIC]**
- Czech intraday prices are **weakly mean-reverting** on short time scales (H ≈ 0.42-0.45 for 10-24h), and **strongly mean-reverting** on longer scales (H ≈ 0.19-0.20 for 25-240h)
- This is KEY for the regime classification: prices will revert to fundamentals, but the speed depends on time scale. Short-term (same day) = weak reversion, multi-day = strong reversion.

### From Kie17 — Demand-quote threshold
- The demand-quote threshold separating regimes was empirically found at **1.178 and 1.415** for different case studies
- Below 1.178: flat merit order, forecast errors have moderate impact
- Above 1.415: steep merit order, forecast errors have amplified, asymmetric impact

### From Kri20 — FBMC (Flow-Based Market Coupling)
- Under FBMC, congestion on ONE border causes price differentials in ALL countries — it's not bilateral
- Germany is typically a net exporter due to renewables
- The most congested borders are DE-NL and BE-NL — not directly CZ-relevant but affects overall European price convergence

---

## 3. Price & Technical Analyst (`market_analyst.py`)

### From Ber17 **[CZ-SPECIFIC]**
- **Intraday prices from the previous day's session influence the NEXT day's DA price** — R² of 0.145 for intraday prices alone explaining DA prices. This is a feedback loop: today's intraday deviations feed into tomorrow's DA price formation.
- Day-ahead prices exhibit **mean-reverting symmetry in lagged coefficients** — a strong move in one direction at t-1 is partially reversed at t (confirmed for CZ by Kristoufek & Lunackova 2013)
- **Negative CZ intraday prices are NOT connected to negative DA prices** — they result from unforeseen RES surplus or negative demand shocks, independent of DA. The agent should not assume DA spikes propagate to intraday.
- Czech intraday prices were reported in **CZK/MWh until August 2016**, then EUR/MWh — the data layer must handle this conversion correctly (see Phase 1 known bug #1)

**Suggested prompt addition:**
```
CZECH INTRADAY PRICE DYNAMICS (from Ber17, Čurpek):
- CZ intraday prices are WEAKLY mean-reverting within a day (Hurst ≈ 0.42-0.45),
  STRONGLY mean-reverting over multiple days (Hurst ≈ 0.19-0.20)
- Mean reversion takes time — don't expect same-hour reversion, expect multi-day
- Today's intraday deviations feed back into TOMORROW's DA price (R² ≈ 0.15)
- Negative intraday prices are caused by unforeseen RES surplus, NOT by negative DA prices
- The CZ intraday market has LOW liquidity (544 GWh/year in 2016 vs 36.3 TWh in DE) —
  spreads are wider and market impact is proportionally larger per MW traded
```

### From Balardy22 (German bid-ask spread analysis)
- Average bid-ask spread is **3.5 EUR/MWh** (~10% of VWAP) in German continuous market
- Spread follows an **L-shape** over the trading session: high at start, decreasing as delivery approaches, small spike at the very end
- **80% of volume** is traded in the last 3 hours of the trading session
- Forecast errors *decrease* the bid-ask spread (counter-intuitive): they create a need to trade → more volume → tighter spreads
- Supply-side concentration has 3x the impact on spreads vs demand-side (3 cents/MWh per 100 HHI points vs 1 cent)

### From Hir23 (neighboring contracts)
- Adjacent delivery period prices have strong **gravitational pull** on each other — cross-product signals are real
- The SIDC/XBID coupling (started June 2018) changed the distribution parameters significantly

### From Féron, Tankov & Tinsi (2020)
- Optimal execution in power intraday is a genuine **stochastic control problem** — not just "buy low sell high"
- Market impact is transient, not permanent — prices recover after large trades

### From Martin & Otterson (2018)
- Order book imbalance (ratio of bid to ask volume) has predictive power for short-term price direction
- The order book is thinner at the start and very end of the trading session

---

## 4. Energy News & Regulatory Analyst (`news_analyst.py`)

### From Hie20 (REMIT framework)
- Already well-integrated. No additional findings needed beyond what's in the prompt.

### From Ber17 **[CZ-SPECIFIC]**
- Czech power sector experienced a **solar boom in 2010-2011** after feed-in tariff incentives, followed by a **solar tax of 26%** (2011-2013) and cancellation of solar support after 2013. Solar capacity is now stable (~2,075 MW). No major new RES boom expected.
- This historical context matters: CZ is not DE. The RES growth narrative that drives German intraday volatility does not apply to CZ in the same way.

---

## 5. Trader (`trader.py`)

### From Kat20 (Optimal execution)
- **The predominant strategy in sparse order books is to trade as little as possible per step** to reduce impact, and only deviate from this for risk aversion or regime knowledge
- TWAP and VWAP are **more profitable in high-volume, low-lead-time scenarios**; optimization approaches are better with **more time to trade**
- Even mathematically optimized execution **barely deviates from TWAP** in intraday markets — because market impact is exponential, not linear
- **Instant order book execution (IOBE)** — clicking to buy/sell the full volume at once — is only cost-effective for very small volumes. For anything >5 MW, slicing is essential.
- The assumption of trading at index prices (ID1, ID3) is **unrealistic** — even complex algorithms trade far from index prices

**Suggested prompt addition:**
```
EXECUTION REALITY (from Kat20):
- In power intraday, market impact grows EXPONENTIALLY with order size — not linearly
- The optimal strategy in sparse order books is to trade AS LITTLE AS POSSIBLE per time step
- TWAP barely differs from mathematically optimal execution — keep it simple
- Never execute >5 MW in a single order book sweep — the market impact will destroy the edge
- Index prices (ID1, ID3) are NOT achievable reference prices — real execution is always worse
- For CZ specifically: the notice-board market has even LESS liquidity than EPEX continuous.
  Expect wider spreads and more difficulty closing positions.
```

### From Bun18 (profitability of intraday trading)
- **NoTrade is a feature, not a failure** — selective trading (only trading when edge > costs) dramatically improves net P&L
- The paper finds meaningful profitability only in specific market regimes and for specific strategies

### From Kup21 (auction vs continuous costs)
- IDA auctions have **lower execution costs** than continuous trading for large volumes — uniform clearing eliminates market impact

---

## 6. Risk Analysts (`aggressive/conservative/neutral_debator.py`)

### From Nar21 (market impact in auctions)
- Already referenced. Key point: for large volumes in auctions, minimizing impact matters more than maximizing apparent arbitrage.

### From Nar22 (imbalance costs)
- Imbalance settlement is the **ultimate risk** — any residual position at gate closure settles at potentially punitive prices
- The imbalance price can swing wildly — it's determined by the most expensive activated reserve

### From Bro22 
- Balancing market dynamics feed back into intraday prices — system imbalance signals have predictive power for late-session price moves

---

## 7. Research Manager (`research_manager.py`)

### Key meta-finding across all papers:
- **For CZ**: Solar forecast errors + load forecast errors are the dominant signals. Wind is noise.
- **For DE-LU**: Wind forecast errors are the dominant signal, with solar secondary.
- The Research Manager should **weight the Weather & Forecast Analyst's report most heavily for renewable-intensive hours** and the **System State Analyst most heavily for peak demand hours** where the merit order is steep.

### From Ber17 **[CZ-SPECIFIC]**
- The intraday price deviation ARX(1) model explains **R² = 0.61** of price deviation — mostly from the autoregressive term (lagged deviation). When you remove the AR term, R² drops to **0.097**. This means: **most of the CZ intraday price deviation is persistence from previous deviations, not new fundamental information.**
- Practical implication: if the CZ intraday price has been trending away from DA for the last few hours, the trend is likely to continue in the near term (persistence), but will revert over days.

---

## 8. Portfolio Manager (`portfolio_manager.py`)

### From Time_Evolution_of_Hurst_Exponent **[CZ-SPECIFIC]**
- The Hurst exponent analysis provides a scientific basis for the mean-reversion time horizon:
  - Within 24 hours: H ≈ 0.42 → weak mean reversion, borderline random
  - Over 25-240 hours: H ≈ 0.19 → strong mean reversion
- This means: **for same-day positions, don't count on reversion.** For multi-day trends, reversion is reliable.

### From Ber17 **[CZ-SPECIFIC]**
- CZ intraday market volume is **tiny** — 544.7 GWh annually (2016) vs ~36 TWh for German continuous. Position sizes must be proportionally smaller for CZ. A 10 MW order in CZ has proportionally 60x the market impact of a 10 MW order in DE.

---

## Summary: Top 5 Prompt Improvements by Priority

1. **Weather & Forecast Analyst**: Add CZ-specific solar/wind hierarchy (solar >> wind for CZ), ČEPS load bias, wind nighttime effect. Currently the prompt gives DE-scale benchmarks (5 GW wind errors) that are meaningless for CZ.

2. **System State Analyst**: Add Czech generation mix (lignite+nuclear dominance, gas as peak price-setter), CZ notice-board market design (not continuous clearing), 50 Hertz cross-border dynamics, imbalance volume interpretation.

3. **Price & Technical Analyst**: Add CZ-specific mean-reversion dynamics (Hurst exponents), CZ market liquidity context (60x less liquid than DE), intraday→DA feedback loop, negative price disconnection from DA.

4. **Trader**: Add CZ liquidity warning (position sizing must be much smaller than DE), exponential market impact reality, TWAP-as-optimal finding, IDA auction advantage for large positions.

5. **Research Manager**: Add signal weighting guidance — for CZ, solar+load errors dominate, most price persistence is autoregressive (not new information), weight accordingly.
