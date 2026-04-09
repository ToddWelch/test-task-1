# AI-Powered Out-of-Stock Intelligence Tool

A Python-based inventory analysis tool that generates a single-file HTML dashboard (Tailwind CSS via CDN requires internet) with seasonally-projected out-of-stock detection, two-layer risk scoring, and AI-generated insights via Claude API.

Built for the Schneider Saddlery technical assessment.

---

## Architecture Overview

### End-to-End Flow

```
inventory.csv  -->  Python Analysis Engine  -->  Claude API (optional)  -->  Single-file HTML Dashboard
                    (seasonal projection,       (executive summary,
                     urgency flags,              per-SKU recs,
                     risk tiers,                 category patterns)
                     financial scoring)
```

The tool separates concerns cleanly:

1. **Data loading** reads any CSV with the expected columns and converts types. Includes input validation: checks for required columns, non-negative stock and velocity values, date parsing, and duplicate SKU detection. Validation warnings are printed to console during processing
2. **Seasonal projection engine** walks forward day-by-day through the calendar consuming stock at seasonally-adjusted rates
3. **Scoring engine** applies deterministic, configurable rules for urgency flags and financial risk tiers
4. **AI layer** makes up to 18 API calls across four sections: one executive summary, one category analysis, one investigation summary, and up to 15 individual per-SKU recommendations (gracefully optional)
5. **HTML generator** produces a single-file HTML report with embedded data and interactive JavaScript (Tailwind CSS loaded via CDN requires internet access for styling)

### Two-Layer Scoring: Why Separate Urgency from Financial Impact

A simpler implementation would collapse flags and tiers into one dimension. I separated them because that is how real operators make decisions:

- **Urgency Flags** answer "When do I need to act?" A product can be Red (needs restock now) but only Low tier (low financial impact). The operator knows it is urgent but not a priority over bigger items.
- **Risk Tiers** answer "Where should I focus?" A product can be Healthy (plenty of stock) but Critical tier ($5K+/month in profit). The operator knows to keep an eye on it even though it is not urgent today.

The sort algorithm combines both: flag weight (urgency) plus monthly profit at risk (financial impact). This puts the worst combination (OOS + Critical) at the top and Healthy + Low at the bottom.

### Seasonal Projection vs. Flat Velocity

Most inventory tools divide current stock by current velocity to get "days of stock." This is misleading during seasonal transitions. A blanket with 100 days of stock at April velocity (0.40x base) has far less coverage when you account for September (0.70x) through December (1.70x).

The projection engine walks forward day by day through the calendar, applying the correct monthly coefficient for each day. When flat and projected values diverge by more than 15%, the dashboard shows a seasonal indicator badge so the operator understands why the numbers differ.

A production system would use per-product curves trained on 2+ years of historical data rather than category-level coefficients.

---

## How to Run

### Prerequisites

- Python 3.9+
- (Optional) Anthropic API key for AI insights

### Installation

```bash
pip install -r requirements.txt
```

### Generate Sample Data

The sample dataset is included at `sample_data/inventory.csv`. To regenerate it:

```bash
python generate_data.py
```

This creates 168 SKUs across 10 equestrian product categories with realistic velocity distributions, pricing, and stock scenarios.

### Run the Tool

```bash
# With AI insights (requires ANTHROPIC_API_KEY)
export ANTHROPIC_API_KEY=your-key-here
python oos_tool.py

# Without AI (dashboard renders with all quantitative data)
python oos_tool.py --no-ai

# Custom input/output paths
python oos_tool.py --input custom_inventory.csv --output reports/my_report.html

# JSON input
python oos_tool.py --input inventory.json
```

Accepts both CSV and JSON input files. JSON should contain a list of objects with the same field names as CSV columns.

### View the Report

Open `output/oos_report.html` in any modern browser. No server required.

### Lead Time Fields

The assessment brief specifies a lead_time_days field. This tool provides more granular data: supplier_lead_time, shipping_time, and receiving_buffer. Total lead time is derived as the sum of all three, enabling per-component analysis. The tool also accepts a single lead_time column as a fallback if the three-column breakdown is not available.

---

## Fulfil.io Integration Plan

Reference: [Fulfil.io Platform API](https://fulfil.io/platform/api/)

### Authentication

Fulfil supports Personal Access Tokens for server-to-server integrations and OAuth2 for user-facing apps. All API calls go to `https://{tenant}.fulfil.io/api/v2/` over HTTPS.

### Relevant Models

| Fulfil Model | Maps To | Data Pulled |
|---|---|---|
| `product.product` | SKU, name, category, cost, price | Product master data with cost and pricing fields |
| `stock.move` | Velocity calculation | Historical stock movements; aggregate by product over 7d/30d/90d windows to derive velocity |
| `stock.location` | Multi-warehouse support | Warehouse locations for per-location stock levels |
| `purchase.line` | Lead times, last restock dates | PO-to-receipt history gives actual lead time distributions; latest receipt date becomes last_restock_date |
| `stock.inventory` | Current stock levels | Real-time on-hand quantities per product per location |

Model names referenced from Fulfil's official open-source Python client (github.com/fulfilio/fulfil-python-api) and confirmed via public third-party integration documentation. Rate limits are 1000+ requests per minute per [fulfil.io/platform/api/](https://fulfil.io/platform/api/). The API uses standard REST with JSON payloads.

### Data Flow

A scheduled Python job pulls inventory snapshots every 4-6 hours via the REST API. Stock moves are pulled daily for velocity calculation (7-day, 30-day, 90-day weighted windows). Data is stored in PostgreSQL for historical trending. The dashboard regenerates on each pull.

### Sync Strategy

- **Incremental updates:** Filter by `write_date` on each model to pull only records changed since last sync
- **Full reconciliation:** Weekly full pull to catch any missed incremental updates
- **Idempotent upserts:** All sync operations use upsert logic keyed on Fulfil record IDs

### BigQuery and Shopify

Fulfil offers managed BigQuery export for analytics workloads per [fulfil.io](https://fulfil.io). This is ideal for long-term velocity trend analysis and historical reporting. The REST API handles real-time stock level queries.

Fulfil has native Shopify Plus integration. In a Schneider deployment, Fulfil would be the inventory source of truth, with Shopify reading from Fulfil for storefront availability. Fulfil is SOC 2 Type II compliant per [fulfil.io](https://fulfil.io), with data encrypted at rest on Google Cloud infrastructure.

---

## AI Guardrails

Claude does not analyze inventory. Python analyzes inventory. Claude converts validated metrics into business-readable language.

The guardrail system has five layers:

- **Layer 1: Deterministic computation.** All metrics (flags, tiers, urgency scores, projected days, profit at risk, recommended quantities) are computed in Python. The LLM receives pre-computed results only.
- **Layer 2: Narrow prompts.** Each AI section receives only the data it needs. Per-SKU recommendations receive one product at a time to prevent cross-item contamination. Month-to-coefficient mappings are pre-computed in Python so the LLM never interprets raw seasonal arrays.
- **Layer 3: Constrained output.** The system prompt bans causal speculation (phrases like "likely due to", "caused by", "driven by"), limits recommendations to seven allowed actions (reorder now, expedite review, monitor closely, investigate stale OOS, verify reorder point, find alternative supplier, formally discontinue), and forbids references to external entities not in the data (no market trends, competitor activity, or supplier details beyond what is provided).
- **Layer 4: Post-generation validation.** After each AI response, Python scans for unknown SKUs, banned causal phrases, unauthorized action recommendations, and external entity references. If validation fails, the text is regenerated once. If it fails again, the system falls back to deterministic templates.
- **Layer 5: Graceful fallback.** If the API key is not set, the API is unreachable, or validation fails, every section renders using Python-generated template text. The dashboard is fully functional without AI. Cost per full AI run is approximately $0.09 (based on Claude Sonnet with 168 SKUs, 15 per-SKU recommendation calls, and approximately 8,000 total output tokens across all sections).

---

## Business Impact Metrics

### Primary KPI: Reduction in OOS Events

The tool catches items before they go OOS by comparing projected coverage (accounting for seasonality and lead times) against restock windows. Success is measured by month-over-month reduction in items reaching the Purple (OOS) flag.

### Revenue Recovery

- **Monthly profit at risk:** The sum of daily profit times 30 for all Red and Purple items. This number should trend downward as operators restock earlier.
- **Missed profit reduction:** For items already OOS, the tool calculates estimated profit lost during the stockout. Catching items at Yellow instead of waiting until Purple directly reduces this number.

### Operational Efficiency

- **Restock timing improvement:** Track the average urgency score at the time an order is placed. The goal is to shift from reactive (Red, urgency < 0) to proactive (Yellow/Blue, urgency 0-30).
- **Category health distribution:** The percentage of SKUs in each flag should shift toward Green over time.
- **Time savings:** The dashboard consolidates analysis that would otherwise require spreadsheet work across multiple data sources.

### Margin Note

Profit calculations use gross margin (unit price minus unit cost). A production deployment would factor in Shopify fees (2.4-2.9% + $0.30), payment processing, warehouse labor and storage, shipping, and returns, which typically reduce gross margin by 15-25 percentage points. The settings panel would support a margin adjustment factor.

---

## Seasonality Documentation

The tool projects consumption forward using monthly coefficients per category rather than flat velocity. Each category has 12 coefficients (January through December) that multiply the base annual average velocity.

**Example:** A blanket product with base velocity 8.75 units/day:
- April (coefficient 0.40): actual daily demand = 3.5 units
- September (coefficient 0.70): actual daily demand = 6.1 units
- December (coefficient 1.70): actual daily demand = 14.9 units

The projection walks forward day by day, applying the correct coefficient for each month boundary crossed. This means an item with 200 units of stock in April is not simply 200 / 3.5 = 57 days of stock. Accounting for the increasing coefficients through spring and summer, actual coverage may be significantly different.

Categories with distinct seasonal patterns:
- **Blankets and Sheets:** Peak Oct-Dec (1.10x to 1.70x), trough Jun-Jul (0.20x)
- **Fly and Insect Control:** Peak May-Aug (1.40x to 1.70x), trough Dec-Jan (0.20x to 0.30x)
- **Supplements and Health:** Moderate seasonality, peak Nov-Dec (1.10x to 1.30x)
- **All other categories:** Follow a general retail pattern peaking in holiday season

A production system would replace these category-level coefficients with per-product curves trained on 2+ years of sales history, enabling much more precise projections for individual SKUs.

---

## Reorder Quantity Note

The recommended order quantity projects consumption over the full coverage window: total lead time (supplier lead + shipping + receiving buffer) plus configurable buffer days plus target stock days. Current stock is subtracted from total projected consumption.

Default target is 60 days on hand after restock arrives. This is configurable in the dashboard settings panel. A production system would configure per product or category. Overseas products with 70-96 day lead times would typically target 90-120 days of stock to provide adequate safety margin against supply chain variability.

---

## Limitations

- Synthetic data only; not connected to a live inventory system
- Seasonality uses category-level monthly coefficients, not per-SKU forecast curves trained on historical data
- No live purchase order or warehouse capacity constraints
- Profit at risk uses gross margin (unit price minus unit cost); does not factor in Shopify fees, payment processing, warehouse labor, shipping, or returns
- Missed profit estimate uses a heuristic approximation (last restock date + 30 days), not actual stock-zero dates from inventory movement history
- Single-warehouse model; does not account for multi-location inventory or in-transit stock
- AI insights are generated at build time, not live/interactive in the browser
- Dashboard styling requires internet access for Tailwind CSS via CDN

---

## Roadmap

1. **Weighted velocity windows:** Use 7-day, 30-day, and 90-day sales windows with configurable weights (e.g., 50% / 30% / 20%) for more responsive velocity detection
2. **Per-product seasonality curves:** Train on 2+ years of historical sales data per SKU, replacing category-level coefficients
3. **Supplier performance tracking:** Track actual vs. quoted lead times, on-time delivery rates, and fill rates per supplier
4. **Automated PO generation:** Generate purchase orders in Fulfil with manager approval workflow, using recommended quantities from the tool
5. **Alerts and notifications:** Slack and email alerts with daily digest and escalation for items in Critical tier for 48+ hours
6. **Multi-warehouse support:** Per-location stock analysis with transfer recommendations between warehouses
7. **OOS recovery velocity:** When a product returns from OOS, model demand recovery at 75% of historical rate for the first 30 days
8. **Historical trend dashboard:** Track OOS rate, forecast accuracy, and category health distribution over time to measure tool effectiveness

---

## AI Tools Used

### Claude Code (Development)

Claude Code served as the development assistant for building the entire tool. Specifically:

- Designed the architecture (seasonal projection engine, two-layer scoring, HTML dashboard structure)
- Wrote all Python code (data loading, analysis pipeline, AI integration, HTML generation, CLI)
- Wrote all JavaScript for the interactive dashboard (sorting, filtering, search, settings persistence, live recalculation)
- Generated the synthetic dataset with realistic equestrian product distributions
- Built the Tailwind CSS dashboard with light theme styled to match the Schneider Saddlery website, responsive layout, and print styles

### Claude API (Sonnet, Runtime Insights)

The deployed tool calls Claude Sonnet (temperature 0.3) at runtime for up to 18 API calls across four sections:

1. **Executive Summary (1 call):** Receives aggregated stats, flag/tier distributions, top urgent items, category breakdowns with seasonal data, and investigation items. Returns a 3-4 paragraph briefing suitable for a Monday morning operations meeting.
2. **Category Patterns (1 call):** Receives category aggregations with supplier distributions and seasonal coefficients. Returns category-level analysis identifying concentration risks, seasonal observations, and investigation notes for long-OOS items.
3. **Investigation Summary (1 call):** Receives data on long-OOS and stale inventory items. Returns analysis of items requiring manual review.
4. **Per-SKU Recommendations (up to 15 calls):** Each Critical/High tier item with a Red/Purple flag gets its own individual API call. Receives detailed data for one product at a time to prevent cross-item contamination. Returns 1-2 sentence actionable recommendations referencing specific velocity, lead time, seasonal trend, and profit data.

All AI outputs are clearly labeled in the dashboard and are optional. The tool functions fully without them.

---

## Time Spent

| Phase | Time |
|---|---|
| Data generation and synthetic dataset | 0.5 hours |
| Build plan and architecture design | 1.0 hours |
| Seasonal projection engine and scoring | 1.0 hours |
| AI integration layer | 0.5 hours |
| HTML dashboard (layout, interactivity, JS) | 2.0 hours |
| README and documentation | 1.0 hours |
| Testing and refinement | 0.5 hours |
| **Total** | **6.5 hours** |
