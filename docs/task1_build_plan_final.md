# Task 1 Build Plan: AI-Powered Out-of-Stock Intelligence Tool
# Schneider Saddlery Technical Assessment
# Hand this entire document to Claude Code as the implementation spec
# Time budget: 4-5 hours total

---

## Project Overview

Build a Python script that generates a self-contained HTML dashboard for out-of-stock intelligence. The dashboard accepts CSV upload, analyzes inventory data using seasonally-projected consumption, calls Claude API for AI-generated insights, and displays everything in a clean, interactive report suitable for a non-technical operations manager.

Color scheme and visual style should match the Schneider Saddlery website (sstack.com). Dark navy/charcoal tones, clean typography, professional e-commerce feel.

---

## Architecture

```
schneider-assessment/
  task1/
    oos_tool.py              # Main script: loads CSV, runs analysis, calls Claude, generates HTML
    generate_data.py         # Generates realistic synthetic equestrian inventory dataset
    requirements.txt         # Python dependencies (anthropic only)
    sample_data/
      inventory.csv          # Generated synthetic dataset (committed to repo)
    output/
      oos_report.html        # Generated dashboard (committed as sample output)
    README.md                # Architecture, Fulfil.io plan, guardrails, business impact, roadmap
```

---

## Step 1: Synthetic Data (generate_data.py)

The sample dataset is pre-generated and included as sample_data/inventory.csv. The generate_data.py script is included in the repo so reviewers can see how the data was built.

168 SKUs across 10 categories. Real equestrian product names from Schneider's catalog. Realistic velocity distributions, pricing, and stock scenarios.

### CSV Columns:
- `sku` (SCH-XXXXX format)
- `product_name`
- `category` (Blankets & Sheets, Fly & Insect Control, Tack & Saddles, Riding Apparel, Barn & Stable, Grooming, Supplements & Health, Boots & Wraps, Horse Tack Accessories, Rider Accessories)
- `current_stock` (0-2000+)
- `reorder_point` (per-product, 94% have one set, 6% are zero for new products)
- `supplier_lead_time` (fixed per supplier: domestic 14-21d, overseas 45-75d)
- `shipping_time` (fixed per supplier: domestic 3-5d, overseas 7-16d)
- `receiving_buffer` (flat 5 days across all products)
- `base_velocity` (annual average daily velocity BEFORE seasonality)
- `avg_daily_velocity` (base_velocity * current month coefficient = what's happening now)
- `last_restock_date`
- `unit_cost`
- `unit_price` (cost/price ratio 30-50%, margins 50-70%)
- `supplier` (8 suppliers: Dover Wholesale, Weatherbeeta Direct, Farnam Direct, Pacific Rim Imports, Blue Ridge Equine Supply, Mountain Horse EU, Horsemens Pride, Local Craftworks)

### Supplier Lead Times (consistent per supplier):
| Supplier | Lead | Ship | Buffer | Total |
|----------|------|------|--------|-------|
| Dover Wholesale | 18d | 5d | 5d | 28d |
| Farnam Direct | 16d | 5d | 5d | 26d |
| Blue Ridge Equine Supply | 20d | 4d | 5d | 29d |
| Horsemens Pride | 21d | 5d | 5d | 31d |
| Local Craftworks | 14d | 3d | 5d | 22d |
| Weatherbeeta Direct | 55d | 10d | 5d | 70d |
| Mountain Horse EU | 60d | 12d | 5d | 77d |
| Pacific Rim Imports | 75d | 16d | 5d | 96d |

### Data Distribution:
- Flags: Purple 10%, Red 18%, Yellow 6%, Blue 5%, Green 60%
- Risk Tiers: Critical 15%, High 35%, Medium 27%, Watch 23%
- Velocity: power law (5% high 10-20/day, 15% medium-high 4-10, 30% medium 1-4, 50% slow 0.1-1)

---

## Step 2: Seasonality Projection Engine

This is a KEY DIFFERENTIATOR of the tool. Most inventory tools use flat velocity (current rate projected forward). This tool projects consumption month by month using seasonal coefficients, giving operators an accurate picture of when stock will actually run out and how much to order.

### Seasonality Coefficient Table (embedded in oos_tool.py):

```python
SEASONALITY = {
    "Blankets & Sheets": [0.90, 0.75, 0.60, 0.40, 0.25, 0.20, 0.20, 0.35, 0.70, 1.10, 1.50, 1.70],
    "Fly & Insect Control": [0.30, 0.40, 0.70, 1.00, 1.40, 1.60, 1.70, 1.50, 1.00, 0.50, 0.25, 0.20],
    "General": [0.75, 0.80, 0.85, 0.90, 0.90, 0.85, 0.85, 0.80, 0.90, 1.00, 1.30, 1.70],
}
# All categories not in SEASONALITY use "General"
# Index 0 = January, Index 11 = December
```

### Projected Days Until OOS (REPLACES flat stock / velocity):

Walk forward day by day through the calendar, consuming stock at the seasonally-adjusted rate for each month:

```python
def projected_days_until_oos(current_stock, base_velocity, category, start_month, start_day_of_month):
    remaining = current_stock
    days = 0
    month = start_month
    day_in_month = start_day_of_month
    days_per_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    coefficients = SEASONALITY.get(category, SEASONALITY["General"])
    
    while remaining > 0 and days < 365:
        daily_velocity = base_velocity * coefficients[month - 1]
        remaining -= daily_velocity
        days += 1
        day_in_month += 1
        if day_in_month > days_per_month[month - 1]:
            day_in_month = 1
            month = (month % 12) + 1
    
    return days
```

### Projected Recommended Order Qty (REPLACES velocity * target_days):

Sum projected consumption over the full coverage window (lead_time + buffer + target_stock_days), accounting for seasonal velocity changes each month:

```python
def projected_order_qty(current_stock, base_velocity, category, start_month, start_day_of_month, total_lead_time, buffer_days, target_stock_days):
    total_window = total_lead_time + buffer_days + target_stock_days
    total_consumption = 0
    month = start_month
    day_in_month = start_day_of_month
    days_per_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    coefficients = SEASONALITY.get(category, SEASONALITY["General"])
    
    for day in range(total_window):
        daily_velocity = base_velocity * coefficients[month - 1]
        total_consumption += daily_velocity
        day_in_month += 1
        if day_in_month > days_per_month[month - 1]:
            day_in_month = 1
            month = (month % 12) + 1
    
    recommended = max(0, total_consumption - current_stock)
    return int(recommended + 0.5)
```

### Flat vs Projected Comparison:

Calculate BOTH values. Display projected as the primary number. When they differ by more than 15%, show a seasonal indicator badge:
- Red arrow up + "Demand increasing" = projected OOS is SOONER than flat (more urgent)
- Green arrow down + "Demand decreasing" = projected OOS is LATER than flat (less urgent)

Example insight: "Flat math says 85 days of stock, but accounting for seasonal demand increase, actual coverage is only 52 days."

---

## Step 3: OOS Detection & Scoring Engine

### Two-Layer Scoring System

**Layer 1: OOS Flags** answer "When do I need to act?"
**Layer 2: Risk Tiers** answer "How bad is it financially if I don't act?"

### Layer 1: OOS Detection Flags (urgency-based, uses PROJECTED days)

```python
total_lead_time = supplier_lead_time + shipping_time + receiving_buffer
projected_days = projected_days_until_oos(stock, base_velocity, category, current_month, current_day)
urgency_score = projected_days - (total_lead_time + buffer_days)
```

| Flag | Color | Criteria |
|------|-------|----------|
| OOS | Purple (#7B2D8E) | stock = 0 |
| Restock Now | Red (#DC3545) | urgency_score < 0 |
| Restock Soon | Yellow/Amber (#FFC107) | urgency_score 0-14 |
| Monitor | Blue (#0D6EFD) | urgency_score 14-30 |
| Healthy | Green (#28A745) | urgency_score 30+ |

All thresholds configurable in settings panel.

Special case: If base_velocity < 0.01 and stock > 0, flag as "No Velocity" (gray).

### Layer 2: Risk Tiers (financial impact-based)

```python
daily_profit = avg_daily_velocity * (unit_price - unit_cost)
monthly_profit_at_risk = daily_profit * 30
```

| Tier | Monthly Profit at Risk |
|------|----------------------|
| Critical | > $5,000/month |
| High | $1,000-$5,000/month |
| Medium | $250-$1,000/month |
| Watch | < $250/month |

All thresholds configurable in settings panel. Calibrated for ~$50M/year business.

### Reorder Point Logic

Each product can have a per-product `reorder_point`. Settings panel has a system-wide default (default: 0 = use calculated urgency only). If stock <= reorder_point, show "Below Reorder Point" indicator alongside the urgency flag.

### Missed Profit (for OOS items)

```python
days_since_restock = (today - last_restock_date).days
estimated_days_oos = max(days_since_restock - 30, 0)
missed_profit = estimated_days_oos * daily_profit
```

### Sort Priority

```python
sort_score = flag_weight + monthly_profit_at_risk
```
Purple = 2,000,000 | Red = 1,000,000 | Yellow = 500,000 | Blue = 100,000 | Green = 0

### Recommended Order Quantity

Uses the seasonal projection function:
```python
target_stock_days = 60  # configurable
recommended_qty = projected_order_qty(stock, base_velocity, category, month, day, total_lead, buffer, target_stock_days)
```

---

## Step 4: AI-Generated Insight Layer (Claude API)

Claude Sonnet, temperature=0.3.

### 1. Executive Summary
Pass aggregated stats + seasonality data. Request 3-4 paragraph summary for Monday morning ops meeting. Include:
- OOS count and estimated daily revenue lost
- At-risk counts by flag
- Risk tier breakdown with total monthly profit at risk
- Top 5 most urgent items
- Seasonal callouts (e.g. "Fly products entering peak season, blankets in low season but order now for fall")
- Any "Needs Investigation" items (OOS 60+ days)

Seasonal prompt examples for AI:
- "Fly & Insect Control products are entering peak season (April 1.0x, rising to 1.7x by July). X products in this category are flagged Red/Purple. Order ahead of the demand curve."
- "Blankets & Sheets are in their low season (April 0.40x). Current stock appears healthy but overseas suppliers have 70-96 day lead times. Orders placed today arrive in July. Plan ahead for September (0.70x) through December (1.70x) demand."
- Per-SKU: "Contour Collar Turnout is OOS. Base velocity is 8.75/day. By November (1.50x) demand will reach 13.1/day. Recommend ordering now to rebuild stock before peak."

### 2. Per-SKU Recommendations (Critical/High + Red/Purple only)
1-2 sentence recommendation per SKU. Must reference specific data points (velocity, stock, lead time, profit, seasonal trend).

### 3. Category-Level Patterns
Which categories have the most issues, supplier concentration risks, seasonal observations.

### 4. Needs Investigation (separate callout)
Products OOS with last_restock_date 60+ days ago. AI generates brief note about possible discontinued/supplier issues.

### AI Guardrails:
- All recommendations based strictly on provided data
- Every claim traceable to specific data points
- Tool flags, does not auto-execute
- Claude handles NLG only, scoring math is deterministic Python
- Temperature 0.3
- Graceful fallback if API unavailable (dashboard renders with all quantitative data, AI sections show "AI insights unavailable")
- API key via ANTHROPIC_API_KEY env var, never hardcoded

---

## Step 5: HTML Dashboard Output

Single self-contained HTML file. Tailwind CSS from CDN. No server required.

### Color Scheme
Match sstack.com: dark navy/charcoal, clean white data areas, professional e-commerce feel.

### Layout:

**Top Bar:** Title, timestamp, settings gear, "Upload New Data" button

**Settings Panel (slide-out):**
- OOS Flag Thresholds: Red _7_ days, Yellow _14_ days, Blue _30_ days, Buffer _7_ days
- Risk Tier Thresholds: Critical >$_5,000_, High $_1,000_-$_5,000_, Medium $_250_-$_1,000_, Watch <$_250_
- Restock: Target stock days _60_, Default lead time _21_, Default reorder point _0_
- Changes apply immediately, persist in localStorage, Reset to Defaults button

**Key Stats Cards:**
Total SKUs | Currently OOS | At-Risk (Red+Yellow) | Est Daily Revenue Lost | Monthly Profit at Risk | Missed Profit to Date

**Executive Summary Panel:** AI-generated text

**Main Data Table (sortable, filterable):**
- Flag (color badge)
- Risk Tier (badge)
- SKU, Product Name, Category, Supplier
- Current Stock
- Base Velocity / Current Velocity
- Projected Days Until OOS (primary) + Flat Days (secondary, shown when they diverge)
- Seasonal Trend (arrow up/down/flat with tooltip showing next 3 months coefficients)
- Urgency Score
- Total Lead Time
- Reorder Point
- Monthly Profit at Risk
- Missed Profit (OOS items)
- Recommended Order Qty (seasonally projected)
- Est Order Cost

Features:
- Sort by any column
- Filter by flag, tier, category, supplier
- Search bar
- Click row to expand AI recommendation (Critical/High + Red/Purple items)
- Below Reorder Point indicator

**Category Health View:**
Cards per category: total SKUs, OOS count, at-risk count, profit at risk, seasonal trend arrow. AI category patterns.

**Needs Investigation Section:**
OOS 60+ days with stale restock dates. AI notes.

**Methodology Notes (collapsible):**
All formulas, thresholds, seasonality explanation.

### Design:
- Professional ops dashboard
- Print-friendly
- Mobile-responsive
- Subtle hover animations

---

## Step 6: README.md (budget 60-90 minutes)

### 1. Architecture Overview
- End-to-end flow (CSV -> Python analysis -> Claude API -> HTML)
- Two-layer scoring: urgency flags + financial risk tiers
- Why separate: "A simpler implementation would collapse flags and tiers into one dimension. I separated them because that's how real operators make decisions. The flags tell you WHEN to act (urgency). The risk tiers tell you WHERE to focus (impact)."
- Seasonal projection vs flat velocity
- Design decisions

### 2. How to Run
```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your-key-here
python generate_data.py          # Creates sample_data/inventory.csv
python oos_tool.py               # Generates output/oos_report.html
python oos_tool.py --input custom.csv
```

### 3. Fulfil.io Integration Plan
Reference actual API at developers.fulfil.io:
- **Auth:** Personal Access Tokens or OAuth2. HTTPS to https://{tenant}.fulfil.io/api/v2/
- **Models:** product.product (SKU, name, category, cost, price), stock.move (velocity from historical moves), stock.location (multi-warehouse), purchase.line (lead times from PO-to-receipt history, last restock dates), stock.inventory (current levels)
- **Data flow:** Scheduled Python job pulls snapshots every 4-6 hours. Stock moves daily for velocity. PostgreSQL for history. Dashboard regenerates each pull.
- **Sync:** Incremental via write_date filter. Full reconciliation weekly. Idempotent upserts.
- **BigQuery:** Fulfil offers managed BigQuery export for analytics. Use for velocity trends, REST API for real-time stock levels.
- **Shopify:** Fulfil has native Shopify Plus integration. Read from Fulfil as inventory source of truth.

### 4. AI Guardrails
Data-only recommendations, traceable claims, flags not auto-executes, deterministic scoring, temperature 0.3, graceful degradation, env var keys.

### 5. Business Impact Metrics
- Primary: Reduction in OOS events/month
- Revenue recovery: monthly_profit_at_risk trending down
- Missed profit reduction: catch items before OOS
- Restock timing: average urgency_score at order time trending toward Yellow/Blue
- Category health distribution improving
- Operational time savings
- Note: "Profit calculations use gross margin. Production would factor in Shopify fees (2.4-2.9% + $0.30), payment processing, warehouse labor/storage, shipping, and returns, which typically reduce gross margin by 15-25 percentage points. The settings panel would support a margin adjustment factor."

### 6. Seasonality Documentation
"The tool projects consumption forward using monthly coefficients per category rather than flat velocity. A blanket with 100 days of stock at April velocity (0.40x) has far less coverage accounting for September (0.70x) through December (1.70x). The projection walks forward day by day through the calendar. A production system would use per-product curves trained on 2+ years of history rather than category-level coefficients."

### 7. Reorder Quantity Note
"Default target is 60 days on hand after restock arrives. Production would configure per product/category. Overseas products would target 90-120 days."

### 8. Roadmap
1. Weighted velocity (7d/30d/90d windows with configurable weights)
2. Per-product seasonality curves from historical data
3. Supplier performance tracking (lead time accuracy, on-time rates)
4. Automated PO generation in Fulfil with approval workflow
5. Slack/email alerts (daily digest, escalation for 48hr+ Critical items)
6. Multi-warehouse support with transfer recommendations
7. OOS recovery velocity (75% of historical when 30-day drops to zero)
8. Historical trend dashboard (OOS rate, forecast accuracy over time)

### 9. AI Tools Used
Claude Code for development, Claude API (Sonnet) for insight generation. Describe specifically how each was used.

### 10. Time Spent
Track honestly per phase.

---

## Dependencies (requirements.txt)

```
anthropic>=0.42
```

CSV parsing and HTML generation are Python stdlib.

---

## Key Principles for Claude Code

- No em dashes anywhere
- Clean, readable Python
- Dashboard must look professional (CEO, CTO, VP Ops will see this)
- README is worth as much as the code
- Show e-commerce operations knowledge in data, scoring, and business impact
- Fulfil.io plan must reference actual API models
- Seasonal projection is the key technical differentiator
- Two-layer scoring (urgency + financial) is the key strategic differentiator
- Settings panel shows configurability thinking
- Missed profit shows cost-of-inaction thinking
