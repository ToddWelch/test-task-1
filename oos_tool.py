#!/usr/bin/env python3
"""
AI-Powered Out-of-Stock Intelligence Tool
Schneider Saddlery Technical Assessment

Generates a self-contained HTML dashboard with seasonally-projected
inventory analysis and AI-generated insights via Claude API.
"""

import argparse
import csv
import html
import json
import os
import sys
from datetime import datetime, date

# ---------------------------------------------------------------------------
# Section A: Constants
# ---------------------------------------------------------------------------

SEASONALITY = {
    "Blankets & Sheets":      [0.90, 0.75, 0.60, 0.40, 0.25, 0.20, 0.20, 0.35, 0.70, 1.10, 1.50, 1.70],
    "Fly & Insect Control":   [0.30, 0.40, 0.70, 1.00, 1.40, 1.60, 1.70, 1.50, 1.00, 0.50, 0.25, 0.20],
    "Tack & Saddles":         [0.75, 0.80, 0.85, 0.90, 0.90, 0.85, 0.85, 0.80, 0.90, 1.00, 1.30, 1.70],
    "Riding Apparel":         [0.75, 0.80, 0.85, 0.90, 0.90, 0.85, 0.85, 0.80, 0.90, 1.00, 1.30, 1.70],
    "Barn & Stable":          [0.75, 0.80, 0.85, 0.90, 0.90, 0.85, 0.85, 0.80, 0.90, 1.00, 1.30, 1.70],
    "Grooming":               [0.75, 0.80, 0.85, 0.90, 0.90, 0.85, 0.85, 0.80, 0.90, 1.00, 1.30, 1.70],
    "Supplements & Health":   [0.80, 0.85, 0.90, 0.95, 0.95, 0.90, 0.90, 0.85, 0.90, 0.95, 1.10, 1.30],
    "Boots & Wraps":          [0.75, 0.80, 0.85, 0.90, 0.90, 0.85, 0.85, 0.80, 0.90, 1.00, 1.30, 1.70],
    "Horse Tack Accessories": [0.75, 0.80, 0.85, 0.90, 0.90, 0.85, 0.85, 0.80, 0.90, 1.00, 1.30, 1.70],
    "Rider Accessories":      [0.75, 0.80, 0.85, 0.90, 0.90, 0.85, 0.85, 0.80, 0.90, 1.00, 1.30, 1.70],
    "General":                [0.75, 0.80, 0.85, 0.90, 0.90, 0.85, 0.85, 0.80, 0.90, 1.00, 1.30, 1.70],
}

DAYS_PER_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

FLAG_WEIGHTS = {
    "OOS": 2_000_000,
    "Restock Now": 1_000_000,
    "Restock Soon": 500_000,
    "Monitor": 100_000,
    "Healthy": 0,
    "No Velocity": 0,
}

FLAG_COLORS = {
    "OOS": "#7C3AED",
    "Restock Now": "#CC0000",
    "Restock Soon": "#D97706",
    "Monitor": "#2563EB",
    "Healthy": "#059669",
    "No Velocity": "#6B7280",
}

DEFAULT_CONFIG = {
    "red_days": 0,
    "yellow_days": 14,
    "blue_days": 30,
    "buffer_days": 7,
    "critical_threshold": 5000,
    "high_threshold": 1000,
    "medium_threshold": 250,
    "target_stock_days": 60,
    "default_lead_time": 21,
    "default_reorder_point": 0,
}

# ---------------------------------------------------------------------------
# Section B: Seasonal Projection Functions
# ---------------------------------------------------------------------------

def projected_days_until_oos(current_stock, base_velocity, category, start_month, start_day_of_month):
    """Walk forward day-by-day through the calendar consuming stock
    at the seasonally-adjusted rate. Returns number of days until OOS,
    capped at 365."""
    if base_velocity < 0.01:
        return 365
    remaining = float(current_stock)
    days = 0
    month = start_month
    day_in_month = start_day_of_month
    coefficients = SEASONALITY.get(category, SEASONALITY["General"])

    while remaining > 0 and days < 365:
        daily_velocity = base_velocity * coefficients[month - 1]
        remaining -= daily_velocity
        days += 1
        day_in_month += 1
        if day_in_month > DAYS_PER_MONTH[month - 1]:
            day_in_month = 1
            month = (month % 12) + 1

    return days


def flat_days_until_oos(current_stock, avg_daily_velocity):
    """Simple stock / velocity calculation (no seasonality)."""
    if avg_daily_velocity < 0.01:
        return 9999
    return current_stock / avg_daily_velocity


def projected_order_qty(current_stock, base_velocity, category,
                        start_month, start_day_of_month,
                        total_lead_time, buffer_days, target_stock_days):
    """Sum projected consumption over the full coverage window
    (lead_time + buffer + target_stock_days) using seasonal coefficients."""
    if base_velocity < 0.01:
        return 0
    total_window = total_lead_time + buffer_days + target_stock_days
    total_consumption = 0.0
    month = start_month
    day_in_month = start_day_of_month
    coefficients = SEASONALITY.get(category, SEASONALITY["General"])

    for _ in range(total_window):
        daily_velocity = base_velocity * coefficients[month - 1]
        total_consumption += daily_velocity
        day_in_month += 1
        if day_in_month > DAYS_PER_MONTH[month - 1]:
            day_in_month = 1
            month = (month % 12) + 1

    recommended = max(0, total_consumption - current_stock)
    return int(recommended + 0.5)


def get_seasonal_trend(base_velocity, category, current_month):
    """Returns trend direction and next 3 months coefficients."""
    coefficients = SEASONALITY.get(category, SEASONALITY["General"])
    current_coeff = coefficients[current_month - 1]
    next_3 = []
    for i in range(1, 4):
        m = ((current_month - 1 + i) % 12)
        next_3.append({"month": MONTH_NAMES[m], "coeff": coefficients[m]})

    avg_next = sum(n["coeff"] for n in next_3) / 3
    if avg_next > current_coeff * 1.15:
        direction = "increasing"
    elif avg_next < current_coeff * 0.85:
        direction = "decreasing"
    else:
        direction = "stable"

    return {
        "direction": direction,
        "current_coeff": current_coeff,
        "next_3": next_3,
        "current_velocity": round(base_velocity * current_coeff, 2),
    }


# ---------------------------------------------------------------------------
# Section C: Scoring Engine
# ---------------------------------------------------------------------------

def calculate_flag(current_stock, projected_days, total_lead_time, buffer_days,
                   base_velocity, config=None):
    """Determine urgency flag for a product."""
    cfg = config or DEFAULT_CONFIG
    if base_velocity < 0.01 and current_stock > 0:
        return "No Velocity"
    if current_stock == 0:
        return "OOS"
    urgency_score = projected_days - (total_lead_time + cfg["buffer_days"])
    if urgency_score < cfg["red_days"]:
        return "Restock Now"
    elif urgency_score < cfg["yellow_days"]:
        return "Restock Soon"
    elif urgency_score < cfg["blue_days"]:
        return "Monitor"
    else:
        return "Healthy"


def calculate_risk_tier(monthly_profit_at_risk, config=None):
    """Determine financial risk tier."""
    cfg = config or DEFAULT_CONFIG
    if monthly_profit_at_risk > cfg["critical_threshold"]:
        return "Critical"
    elif monthly_profit_at_risk > cfg["high_threshold"]:
        return "High"
    elif monthly_profit_at_risk > cfg["medium_threshold"]:
        return "Medium"
    else:
        return "Watch"


def calculate_missed_profit(current_stock, last_restock_date, avg_daily_velocity,
                            unit_price, unit_cost, today=None):
    """For OOS items, estimate profit lost while out of stock."""
    if current_stock > 0:
        return 0.0
    if today is None:
        today = date.today()
    if isinstance(last_restock_date, str):
        last_restock_date = datetime.strptime(last_restock_date, "%Y-%m-%d").date()
    days_since = (today - last_restock_date).days
    estimated_days_oos = max(days_since - 30, 0)
    daily_profit = avg_daily_velocity * (unit_price - unit_cost)
    return round(estimated_days_oos * daily_profit, 2)


def calculate_sort_score(flag, monthly_profit_at_risk):
    """Higher score = higher priority in the table."""
    return FLAG_WEIGHTS.get(flag, 0) + monthly_profit_at_risk


# ---------------------------------------------------------------------------
# Section D: Data Loading & Analysis
# ---------------------------------------------------------------------------

def load_csv(filepath):
    """Read inventory CSV and convert numeric fields."""
    products = []
    with open(filepath, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row["current_stock"] = int(row["current_stock"])
            row["reorder_point"] = int(row["reorder_point"])
            row["supplier_lead_time"] = int(row["supplier_lead_time"])
            row["shipping_time"] = int(row["shipping_time"])
            row["receiving_buffer"] = int(row["receiving_buffer"])
            row["base_velocity"] = float(row["base_velocity"])
            row["avg_daily_velocity"] = float(row["avg_daily_velocity"])
            row["unit_cost"] = float(row["unit_cost"])
            row["unit_price"] = float(row["unit_price"])
            products.append(row)
    return products


def analyze_inventory(products, config=None, today=None):
    """Main analysis pipeline. Returns dict with products, summary,
    categories, and needs_investigation."""
    cfg = config or DEFAULT_CONFIG
    if today is None:
        today = date.today()
    current_month = today.month
    current_day = today.day

    analyzed = []
    summary = {
        "total_skus": len(products),
        "oos_count": 0,
        "at_risk_count": 0,
        "daily_revenue_lost": 0.0,
        "monthly_profit_at_risk": 0.0,
        "missed_profit_total": 0.0,
        "flags": {"OOS": 0, "Restock Now": 0, "Restock Soon": 0,
                  "Monitor": 0, "Healthy": 0, "No Velocity": 0},
        "tiers": {"Critical": 0, "High": 0, "Medium": 0, "Watch": 0},
    }
    categories = {}
    needs_investigation = []

    for p in products:
        total_lead = p["supplier_lead_time"] + p["shipping_time"] + p["receiving_buffer"]
        proj_days = projected_days_until_oos(
            p["current_stock"], p["base_velocity"], p["category"],
            current_month, current_day
        )
        flat_days = flat_days_until_oos(p["current_stock"], p["avg_daily_velocity"])
        daily_profit = p["avg_daily_velocity"] * (p["unit_price"] - p["unit_cost"])
        monthly_profit = round(daily_profit * 30, 2)

        flag = calculate_flag(
            p["current_stock"], proj_days, total_lead,
            cfg["buffer_days"], p["base_velocity"], cfg
        )
        tier = calculate_risk_tier(monthly_profit, cfg)
        missed = calculate_missed_profit(
            p["current_stock"], p["last_restock_date"],
            p["avg_daily_velocity"], p["unit_price"], p["unit_cost"], today
        )
        sort_score = calculate_sort_score(flag, monthly_profit)
        urgency_score = proj_days - (total_lead + cfg["buffer_days"])
        trend = get_seasonal_trend(p["base_velocity"], p["category"], current_month)

        rec_qty = projected_order_qty(
            p["current_stock"], p["base_velocity"], p["category"],
            current_month, current_day, total_lead,
            cfg["buffer_days"], cfg["target_stock_days"]
        )
        est_order_cost = round(rec_qty * p["unit_cost"], 2)

        below_reorder = (p["current_stock"] <= p["reorder_point"]) and p["reorder_point"] > 0

        item = {
            "sku": p["sku"],
            "product_name": p["product_name"],
            "category": p["category"],
            "supplier": p["supplier"],
            "current_stock": p["current_stock"],
            "reorder_point": p["reorder_point"],
            "base_velocity": p["base_velocity"],
            "avg_daily_velocity": p["avg_daily_velocity"],
            "unit_cost": p["unit_cost"],
            "unit_price": p["unit_price"],
            "last_restock_date": p["last_restock_date"],
            "supplier_lead_time": p["supplier_lead_time"],
            "shipping_time": p["shipping_time"],
            "receiving_buffer": p["receiving_buffer"],
            "total_lead_time": total_lead,
            "projected_days": proj_days,
            "flat_days": round(flat_days, 1),
            "flag": flag,
            "risk_tier": tier,
            "urgency_score": round(urgency_score, 1),
            "daily_profit": round(daily_profit, 2),
            "monthly_profit_at_risk": monthly_profit,
            "missed_profit": missed,
            "sort_score": sort_score,
            "trend": trend,
            "recommended_qty": rec_qty,
            "est_order_cost": est_order_cost,
            "below_reorder": below_reorder,
        }
        analyzed.append(item)

        # Update summary
        summary["flags"][flag] = summary["flags"].get(flag, 0) + 1
        summary["tiers"][tier] = summary["tiers"].get(tier, 0) + 1
        if flag == "OOS":
            summary["oos_count"] += 1
            summary["daily_revenue_lost"] += p["avg_daily_velocity"] * p["unit_price"]
            summary["missed_profit_total"] += missed
        if flag in ("OOS", "Restock Now", "Restock Soon"):
            summary["at_risk_count"] += 1
        summary["monthly_profit_at_risk"] += monthly_profit if flag in ("OOS", "Restock Now") else 0

        # Category aggregation
        cat = p["category"]
        if cat not in categories:
            categories[cat] = {
                "name": cat,
                "total": 0, "oos": 0, "at_risk": 0,
                "profit_at_risk": 0.0,
                "trend": trend["direction"],
                "skus": [],
            }
        categories[cat]["total"] += 1
        if flag == "OOS":
            categories[cat]["oos"] += 1
        if flag in ("OOS", "Restock Now", "Restock Soon"):
            categories[cat]["at_risk"] += 1
        if flag in ("OOS", "Restock Now"):
            categories[cat]["profit_at_risk"] += monthly_profit
        categories[cat]["skus"].append(item)

        # Needs investigation: OOS with last_restock 60+ days ago
        if p["current_stock"] == 0:
            last_dt = datetime.strptime(p["last_restock_date"], "%Y-%m-%d").date()
            days_since = (today - last_dt).days
            if days_since >= 60:
                item["days_since_restock"] = days_since
                needs_investigation.append(item)

    # Sort by sort_score descending
    analyzed.sort(key=lambda x: x["sort_score"], reverse=True)
    needs_investigation.sort(key=lambda x: x.get("days_since_restock", 0), reverse=True)

    summary["daily_revenue_lost"] = round(summary["daily_revenue_lost"], 2)
    summary["monthly_profit_at_risk"] = round(summary["monthly_profit_at_risk"], 2)
    summary["missed_profit_total"] = round(summary["missed_profit_total"], 2)

    return {
        "products": analyzed,
        "summary": summary,
        "categories": categories,
        "needs_investigation": needs_investigation,
    }


# ---------------------------------------------------------------------------
# Section E: AI Layer
# ---------------------------------------------------------------------------

def call_claude(prompt, system_prompt="You are an inventory analytics expert for a large equestrian supply retailer."):
    """Make a single Claude API call. Returns response text or None on failure."""
    try:
        import anthropic
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            temperature=0.3,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
    except Exception as e:
        print(f"  AI call failed: {e}")
        return None


def generate_executive_summary(data):
    """Call Claude for executive summary."""
    s = data["summary"]
    cats = data["categories"]
    top5 = data["products"][:5]

    top5_text = ""
    for p in top5:
        top5_text += (
            f"  - {html.escape(p['sku'])} {html.escape(p['product_name'])}: "
            f"Flag={p['flag']}, Tier={p['risk_tier']}, "
            f"Stock={p['current_stock']}, Velocity={p['base_velocity']}/day base, "
            f"Projected {p['projected_days']} days until OOS, "
            f"Monthly profit at risk=${p['monthly_profit_at_risk']:,.2f}\n"
        )

    cat_text = ""
    for name, c in cats.items():
        trend = get_seasonal_trend(0, name, datetime.now().month)
        coeff = trend["current_coeff"]
        next_months = ", ".join(
            f"{n['month']} {n['coeff']}x" for n in trend["next_3"]
        )
        cat_text += (
            f"  - {html.escape(name)}: {c['total']} SKUs, {c['oos']} OOS, "
            f"{c['at_risk']} at-risk, ${c['profit_at_risk']:,.2f}/mo at risk, "
            f"current season {coeff}x, upcoming: {next_months}\n"
        )

    inv_text = ""
    for p in data["needs_investigation"]:
        inv_text += (
            f"  - {html.escape(p['sku'])} {html.escape(p['product_name'])}: "
            f"OOS for ~{p.get('days_since_restock', 'N/A')} days, "
            f"last restock {p['last_restock_date']}\n"
        )

    prompt = f"""Analyze this inventory snapshot and write an executive summary for a Monday morning operations meeting.

INVENTORY SUMMARY:
- Total SKUs: {s['total_skus']}
- Currently OOS: {s['oos_count']}
- At-Risk (Red + Yellow flags): {s['at_risk_count']}
- Estimated daily revenue lost from OOS items: ${s['daily_revenue_lost']:,.2f}
- Monthly profit at risk (OOS + Restock Now): ${s['monthly_profit_at_risk']:,.2f}
- Missed profit to date from OOS items: ${s['missed_profit_total']:,.2f}

FLAG DISTRIBUTION:
- Purple (OOS): {s['flags']['OOS']}
- Red (Restock Now): {s['flags']['Restock Now']}
- Yellow (Restock Soon): {s['flags']['Restock Soon']}
- Blue (Monitor): {s['flags']['Monitor']}
- Green (Healthy): {s['flags']['Healthy']}

RISK TIER DISTRIBUTION:
- Critical (>$5K/mo): {s['tiers']['Critical']}
- High ($1K-5K/mo): {s['tiers']['High']}
- Medium ($250-1K/mo): {s['tiers']['Medium']}
- Watch (<$250/mo): {s['tiers']['Watch']}

TOP 5 MOST URGENT ITEMS:
{top5_text}

CATEGORY BREAKDOWN (with seasonal data):
{cat_text}

NEEDS INVESTIGATION (OOS 60+ days):
{inv_text if inv_text else "  None"}

Today's date: {datetime.now().strftime('%B %d, %Y')}

Write 3-4 paragraphs. Be specific with data points. Include seasonal callouts (which categories are entering peak vs. low season). Mention the most urgent items by name. Note any items needing investigation. Do not use em dashes. Use commas, semicolons, or parentheses instead."""

    return call_claude(prompt)


def generate_sku_recommendations(data):
    """Call Claude for per-SKU recommendations on Critical/High + Red/Purple items."""
    items = [
        p for p in data["products"]
        if p["flag"] in ("OOS", "Restock Now")
        and p["risk_tier"] in ("Critical", "High")
    ]
    if not items:
        return {}

    items_text = ""
    for p in items:
        next_months = ", ".join(
            n["month"] + " " + str(n["coeff"]) + "x" for n in p["trend"]["next_3"]
        )
        trend_info = f"Trend: {p['trend']['direction']}, next 3 months: {next_months}"
        items_text += (
            f"- {html.escape(p['sku'])} | {html.escape(p['product_name'])} | "
            f"Category: {html.escape(p['category'])} | Supplier: {html.escape(p['supplier'])}\n"
            f"  Stock: {p['current_stock']} | Base velocity: {p['base_velocity']}/day | "
            f"Current velocity: {p['avg_daily_velocity']}/day\n"
            f"  Projected days to OOS: {p['projected_days']} | "
            f"Total lead time: {p['total_lead_time']}d | "
            f"Monthly profit at risk: ${p['monthly_profit_at_risk']:,.2f}\n"
            f"  Flag: {p['flag']} | Tier: {p['risk_tier']} | "
            f"Recommended order qty: {p['recommended_qty']} | "
            f"Est order cost: ${p['est_order_cost']:,.2f}\n"
            f"  {trend_info}\n\n"
        )

    prompt = f"""For each SKU below, write a 1-2 sentence actionable recommendation. Reference specific data points (velocity, stock level, lead time, seasonal trend, profit impact). Format as a JSON object where keys are SKU codes and values are recommendation strings.

ITEMS REQUIRING RECOMMENDATIONS:
{items_text}

Today's date: {datetime.now().strftime('%B %d, %Y')}

Return ONLY valid JSON. No markdown formatting, no code blocks. Do not use em dashes in any recommendation. Use commas, semicolons, or parentheses instead."""

    result = call_claude(prompt)
    if result:
        try:
            # Strip potential markdown code fences
            cleaned = result.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()
            return json.loads(cleaned)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"  Failed to parse SKU recommendations JSON: {e}")
            return {}
    return {}


def generate_category_patterns(data):
    """Call Claude for category-level patterns and investigation notes."""
    cats = data["categories"]
    inv = data["needs_investigation"]

    cat_text = ""
    for name, c in cats.items():
        suppliers = {}
        for s in c["skus"]:
            suppliers[s["supplier"]] = suppliers.get(s["supplier"], 0) + 1
        supplier_str = ", ".join(f"{k}: {v}" for k, v in sorted(suppliers.items(), key=lambda x: -x[1]))
        trend = get_seasonal_trend(0, name, datetime.now().month)
        next_months = ", ".join(
            n["month"] + " " + str(n["coeff"]) + "x" for n in trend["next_3"]
        )
        cat_text += (
            f"- {html.escape(name)}: {c['total']} SKUs, {c['oos']} OOS, "
            f"{c['at_risk']} at-risk, ${c['profit_at_risk']:,.2f}/mo at risk\n"
            f"  Suppliers: {supplier_str}\n"
            f"  Season: current {trend['current_coeff']}x, "
            f"next 3 months: {next_months}\n\n"
        )

    inv_text = ""
    for p in inv:
        inv_text += (
            f"- {html.escape(p['sku'])} {html.escape(p['product_name'])} ({html.escape(p['category'])}): "
            f"OOS ~{p.get('days_since_restock', 'N/A')} days, "
            f"supplier: {html.escape(p['supplier'])}, "
            f"base velocity: {p['base_velocity']}/day\n"
        )

    prompt = f"""Analyze category-level patterns and investigation items for an equestrian supply retailer.

CATEGORIES:
{cat_text}

NEEDS INVESTIGATION (OOS 60+ days, possibly discontinued or supplier issues):
{inv_text if inv_text else "None"}

Provide:
1. Category patterns: which categories have the most issues, supplier concentration risks, seasonal observations
2. Investigation notes: for each long-OOS item, a brief note about possible causes (discontinued, supplier problem, seasonal phase-out, etc.)

Format as JSON with two keys:
- "category_patterns": a string with your category analysis (2-3 paragraphs)
- "investigation_notes": an object where keys are SKU codes and values are brief investigation notes

Return ONLY valid JSON. No markdown formatting, no code blocks. Do not use em dashes. Use commas, semicolons, or parentheses instead."""

    result = call_claude(prompt)
    if result:
        try:
            cleaned = result.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()
            return json.loads(cleaned)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"  Failed to parse category patterns JSON: {e}")
            return {}
    return {}


# ---------------------------------------------------------------------------
# Section F: HTML Dashboard Generator
# ---------------------------------------------------------------------------

def generate_html(data, ai_results, config=None):
    """Generate self-contained HTML dashboard."""
    cfg = config or DEFAULT_CONFIG
    products_json = json.dumps(data["products"], default=str)
    summary = data["summary"]
    categories = data["categories"]
    investigation = data["needs_investigation"]

    exec_summary = ai_results.get("executive_summary")
    sku_recs = ai_results.get("sku_recommendations", {})
    cat_patterns = ai_results.get("category_patterns", {})
    cat_analysis = cat_patterns.get("category_patterns", "") if isinstance(cat_patterns, dict) else ""
    inv_notes = cat_patterns.get("investigation_notes", {}) if isinstance(cat_patterns, dict) else {}

    ai_available = exec_summary is not None

    # Escape all string fields for HTML embedding
    def esc(s):
        return html.escape(str(s)) if s else ""

    timestamp = datetime.now().strftime("%B %d, %Y at %I:%M %p")

    # Build category cards HTML
    cat_cards_html = ""
    for name, c in sorted(categories.items()):
        trend = get_seasonal_trend(0, name, datetime.now().month)
        trend_arrow = {"increasing": "&#9650;", "decreasing": "&#9660;", "stable": "&#9654;"}
        trend_color = {"increasing": "#CC0000", "decreasing": "#059669", "stable": "#2563EB"}
        next_months_str = ", ".join(
            f"{n['month']} {n['coeff']}x" for n in trend["next_3"]
        )
        cat_cards_html += f"""
        <div class="bg-white rounded-lg p-5 border border-[#E5E7EB]">
            <div class="flex justify-between items-start mb-3">
                <h3 class="text-[#333333] font-semibold text-sm">{esc(name)}</h3>
                <span class="text-xs" style="color: {trend_color[trend['direction']]}"
                    title="Next 3 months: {next_months_str}">
                    {trend_arrow[trend['direction']]} {trend['direction'].title()}
                </span>
            </div>
            <div class="grid grid-cols-2 gap-2 text-xs">
                <div><span class="text-[#6B7280]">Total SKUs:</span> <span class="text-[#333333]">{c['total']}</span></div>
                <div><span class="text-[#6B7280]">OOS:</span> <span class="text-[#333333]" style="color: {FLAG_COLORS['OOS'] if c['oos'] > 0 else '#333333'}">{c['oos']}</span></div>
                <div><span class="text-[#6B7280]">At Risk:</span> <span class="text-[#333333]" style="color: {'#CC0000' if c['at_risk'] > 0 else '#333333'}">{c['at_risk']}</span></div>
                <div><span class="text-[#6B7280]">Profit/Mo:</span> <span class="text-[#333333]">${c['profit_at_risk']:,.0f}</span></div>
            </div>
            <div class="mt-2 text-xs text-[#6B7280]">Season: {trend['current_coeff']}x now</div>
        </div>"""

    # Build investigation rows HTML
    inv_rows_html = ""
    if investigation:
        for p in investigation:
            note = inv_notes.get(p["sku"], "")
            note_display = esc(note) if note else ("AI insights unavailable for this item." if not ai_available else "No investigation notes generated.")
            inv_rows_html += f"""
            <div class="bg-white rounded-lg p-4 border border-[#E5E7EB] mb-3">
                <div class="flex justify-between items-start">
                    <div>
                        <span class="text-[#333333] font-semibold">{esc(p['sku'])}</span>
                        <span class="text-[#6B7280] ml-2">{esc(p['product_name'])}</span>
                    </div>
                    <span class="text-xs px-2 py-1 rounded" style="background: #CC000015; color: #CC0000">
                        OOS ~{p.get('days_since_restock', 'N/A')} days
                    </span>
                </div>
                <div class="mt-2 text-xs text-[#6B7280]">
                    Category: {esc(p['category'])} | Supplier: {esc(p['supplier'])} |
                    Base velocity: {p['base_velocity']}/day | Last restock: {p['last_restock_date']}
                </div>
                <div class="mt-2 text-sm text-[#333333]">{note_display}</div>
            </div>"""
    else:
        inv_rows_html = '<p class="text-[#6B7280] text-sm">No items currently require investigation.</p>'

    # AI section content
    if ai_available:
        exec_html = f'<div class="text-[#333333] text-sm leading-relaxed whitespace-pre-line">{esc(exec_summary)}</div>'
        cat_analysis_html = f'<div class="text-[#333333] text-sm leading-relaxed whitespace-pre-line">{esc(cat_analysis)}</div>' if cat_analysis else '<p class="text-[#6B7280] text-sm italic">No category analysis generated.</p>'
    else:
        exec_html = """<div class="bg-[#F5F5F5] rounded-lg p-6 text-center">
            <svg class="mx-auto mb-3 w-10 h-10 text-[#6B7280]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0112 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5"/>
            </svg>
            <p class="text-[#6B7280] font-medium">AI insights unavailable</p>
            <p class="text-[#9CA3AF] text-sm mt-1">Run with ANTHROPIC_API_KEY set to enable AI-powered analysis. All quantitative data and scoring remains fully functional.</p>
        </div>"""
        cat_analysis_html = """<div class="bg-[#F5F5F5] rounded-lg p-4 text-center">
            <p class="text-[#6B7280] text-sm">AI category analysis unavailable. Run with ANTHROPIC_API_KEY set to enable.</p>
        </div>"""

    # Build the SKU recs JSON for embedding
    sku_recs_json = json.dumps(sku_recs)

    # Seasonality JSON for JS recalculation
    seasonality_json = json.dumps(SEASONALITY)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Out-of-Stock Intelligence Report | Schneider Saddlery</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body {{ background: #FFFFFF; color: #333333; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
        .settings-panel {{ transform: translateX(100%); transition: transform 0.3s ease; }}
        .settings-panel.open {{ transform: translateX(0); }}
        .settings-overlay {{ opacity: 0; pointer-events: none; transition: opacity 0.3s ease; }}
        .settings-overlay.open {{ opacity: 1; pointer-events: auto; }}
        .sort-arrow {{ opacity: 0.3; cursor: pointer; }}
        .sort-arrow.active {{ opacity: 1; }}
        .expand-row {{ display: none; }}
        .expand-row.visible {{ display: table-row; }}
        .table-row:hover {{ background: #F5F5F5; }}
        input[type="number"] {{ background: #FFFFFF; border: 1px solid #E5E7EB; color: #333333; padding: 4px 8px; border-radius: 4px; width: 100%; }}
        input[type="number"]:focus {{ outline: none; border-color: #2D2D2D; }}
        input[type="text"] {{ background: #FFFFFF; border: 1px solid #E5E7EB; color: #333333; padding: 8px 12px; border-radius: 6px; }}
        input[type="text"]:focus {{ outline: none; border-color: #2D2D2D; }}
        select {{ background: #FFFFFF; border: 1px solid #E5E7EB; color: #333333; padding: 6px 10px; border-radius: 6px; }}
        select:focus {{ outline: none; border-color: #2D2D2D; }}
        .methodology-content {{ max-height: 0; overflow: hidden; transition: max-height 0.3s ease; }}
        .methodology-content.open {{ max-height: 2000px; }}
        .section-heading {{ color: #333333; font-size: 1.125rem; font-weight: 700; padding-bottom: 0.75rem; border-bottom: 2px solid #E5E7EB; margin-bottom: 1rem; }}
        ::-webkit-scrollbar {{ width: 8px; height: 8px; }}
        ::-webkit-scrollbar-track {{ background: #F5F5F5; }}
        ::-webkit-scrollbar-thumb {{ background: #D1D5DB; border-radius: 4px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: #9CA3AF; }}
        @media print {{
            body {{ background: white; color: black; font-size: 10px; }}
            .no-print {{ display: none !important; }}
            .settings-panel, .settings-overlay {{ display: none !important; }}
            table {{ font-size: 9px; }}
            .stat-card {{ break-inside: avoid; }}
        }}
    </style>
</head>
<body class="min-h-screen">
    <!-- Settings Overlay -->
    <div id="settingsOverlay" class="settings-overlay fixed inset-0 bg-black/50 z-40 no-print" onclick="toggleSettings()"></div>

    <!-- Settings Panel -->
    <div id="settingsPanel" class="settings-panel fixed top-0 right-0 h-full w-80 bg-white z-50 overflow-y-auto shadow-2xl no-print">
        <div class="p-6">
            <div class="flex justify-between items-center mb-6">
                <h2 class="text-lg font-bold text-[#333333]">Settings</h2>
                <button onclick="toggleSettings()" class="text-[#6B7280] hover:text-[#333333]">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
                </button>
            </div>

            <div class="space-y-6">
                <div>
                    <h3 class="text-sm font-semibold text-[#6B7280] uppercase tracking-wider mb-3">OOS Flag Thresholds</h3>
                    <div class="space-y-2">
                        <div class="flex items-center justify-between">
                            <label class="text-sm text-[#333333]">Red (Restock Now) days</label>
                            <input type="number" id="cfg_red_days" value="{cfg['red_days']}" min="0" max="90" class="w-20 text-right" onchange="recalculate()">
                        </div>
                        <div class="flex items-center justify-between">
                            <label class="text-sm text-[#333333]">Yellow (Restock Soon) days</label>
                            <input type="number" id="cfg_yellow_days" value="{cfg['yellow_days']}" min="0" max="90" class="w-20 text-right" onchange="recalculate()">
                        </div>
                        <div class="flex items-center justify-between">
                            <label class="text-sm text-[#333333]">Blue (Monitor) days</label>
                            <input type="number" id="cfg_blue_days" value="{cfg['blue_days']}" min="0" max="180" class="w-20 text-right" onchange="recalculate()">
                        </div>
                        <div class="flex items-center justify-between">
                            <label class="text-sm text-[#333333]">Buffer days</label>
                            <input type="number" id="cfg_buffer_days" value="{cfg['buffer_days']}" min="0" max="60" class="w-20 text-right" onchange="recalculate()">
                        </div>
                    </div>
                </div>

                <div>
                    <h3 class="text-sm font-semibold text-[#6B7280] uppercase tracking-wider mb-3">Risk Tier Thresholds</h3>
                    <div class="space-y-2">
                        <div class="flex items-center justify-between">
                            <label class="text-sm text-[#333333]">Critical (&gt;$/mo)</label>
                            <input type="number" id="cfg_critical" value="{cfg['critical_threshold']}" min="0" step="100" class="w-24 text-right" onchange="recalculate()">
                        </div>
                        <div class="flex items-center justify-between">
                            <label class="text-sm text-[#333333]">High (&gt;$/mo)</label>
                            <input type="number" id="cfg_high" value="{cfg['high_threshold']}" min="0" step="100" class="w-24 text-right" onchange="recalculate()">
                        </div>
                        <div class="flex items-center justify-between">
                            <label class="text-sm text-[#333333]">Medium (&gt;$/mo)</label>
                            <input type="number" id="cfg_medium" value="{cfg['medium_threshold']}" min="0" step="50" class="w-24 text-right" onchange="recalculate()">
                        </div>
                    </div>
                </div>

                <div>
                    <h3 class="text-sm font-semibold text-[#6B7280] uppercase tracking-wider mb-3">Restock Settings</h3>
                    <div class="space-y-2">
                        <div class="flex items-center justify-between">
                            <label class="text-sm text-[#333333]">Target stock days</label>
                            <input type="number" id="cfg_target_days" value="{cfg['target_stock_days']}" min="0" max="365" class="w-20 text-right" onchange="recalculate()">
                        </div>
                        <div class="flex items-center justify-between">
                            <label class="text-sm text-[#333333]">Default lead time</label>
                            <input type="number" id="cfg_lead_time" value="{cfg['default_lead_time']}" min="0" max="180" class="w-20 text-right" onchange="recalculate()">
                        </div>
                        <div class="flex items-center justify-between">
                            <label class="text-sm text-[#333333]">Default reorder point</label>
                            <input type="number" id="cfg_reorder_pt" value="{cfg['default_reorder_point']}" min="0" class="w-20 text-right" onchange="recalculate()">
                        </div>
                    </div>
                </div>

                <button onclick="resetDefaults()" class="w-full py-2 px-4 bg-[#F5F5F5] text-[#6B7280] rounded-lg hover:bg-[#E5E7EB] hover:text-[#333333] transition text-sm">
                    Reset to Defaults
                </button>
            </div>
        </div>
    </div>

    <!-- Top Bar -->
    <header class="bg-[#2D2D2D] border-b border-[#2D2D2D] sticky top-0 z-30">
        <div class="max-w-[1600px] mx-auto px-4 py-3 flex items-center justify-between">
            <div>
                <h1 class="text-xl font-bold text-white">Out-of-Stock Intelligence Report</h1>
                <p class="text-xs text-gray-300">Generated {timestamp}</p>
            </div>
            <div class="flex items-center gap-3 no-print">
                <button onclick="window.print()" class="px-3 py-1.5 text-xs bg-[#2D2D2D] text-white rounded-lg hover:bg-[#404040] border border-[#555555] transition">
                    Print
                </button>
                <button onclick="alert('To upload new data, re-run the tool with: python oos_tool.py --input your_file.csv')" class="px-3 py-1.5 text-xs bg-[#2D2D2D] text-white rounded-lg hover:bg-[#404040] border border-[#555555] transition">
                    Upload New Data
                </button>
                <button onclick="toggleSettings()" class="p-1.5 text-gray-300 hover:text-white transition" title="Settings">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
                </button>
            </div>
        </div>
    </header>

    <main class="max-w-[1600px] mx-auto px-4 py-6 space-y-6">
        <!-- Stats Cards -->
        <div id="statsCards" class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
            <div class="stat-card bg-white rounded-lg p-4 border border-[#E5E7EB]">
                <p class="text-xs text-[#6B7280] uppercase tracking-wider">Total SKUs</p>
                <p class="text-2xl font-bold text-[#333333] mt-1" id="stat_total">{summary['total_skus']}</p>
            </div>
            <div class="stat-card bg-white rounded-lg p-4 border border-[#E5E7EB]">
                <p class="text-xs text-[#6B7280] uppercase tracking-wider">Currently OOS</p>
                <p class="text-2xl font-bold mt-1" style="color: #CC0000" id="stat_oos">{summary['oos_count']}</p>
            </div>
            <div class="stat-card bg-white rounded-lg p-4 border border-[#E5E7EB]">
                <p class="text-xs text-[#6B7280] uppercase tracking-wider">At Risk</p>
                <p class="text-2xl font-bold mt-1" style="color: #CC0000" id="stat_atrisk">{summary['at_risk_count']}</p>
            </div>
            <div class="stat-card bg-white rounded-lg p-4 border border-[#E5E7EB]">
                <p class="text-xs text-[#6B7280] uppercase tracking-wider">Daily Revenue Lost</p>
                <p class="text-2xl font-bold text-[#333333] mt-1" id="stat_daily_rev">${summary['daily_revenue_lost']:,.0f}</p>
            </div>
            <div class="stat-card bg-white rounded-lg p-4 border border-[#E5E7EB]">
                <p class="text-xs text-[#6B7280] uppercase tracking-wider">Monthly Profit at Risk</p>
                <p class="text-2xl font-bold text-[#333333] mt-1" id="stat_monthly">${summary['monthly_profit_at_risk']:,.0f}</p>
            </div>
            <div class="stat-card bg-white rounded-lg p-4 border border-[#E5E7EB]">
                <p class="text-xs text-[#6B7280] uppercase tracking-wider">Missed Profit</p>
                <p class="text-2xl font-bold text-[#333333] mt-1" id="stat_missed">${summary['missed_profit_total']:,.0f}</p>
            </div>
        </div>

        <!-- Executive Summary -->
        <div class="bg-white rounded-lg p-6 border border-[#E5E7EB]">
            <h2 class="section-heading">Executive Summary</h2>
            <div id="execSummary">{exec_html}</div>
        </div>

        <!-- Filters and Search -->
        <div class="bg-[#F5F5F5] rounded-lg p-4 border border-[#E5E7EB] no-print">
            <div class="flex flex-wrap gap-3 items-center">
                <input type="text" id="searchInput" placeholder="Search SKU, product, supplier..." class="flex-1 min-w-[200px]" onkeyup="filterTable()">
                <select id="filterFlag" onchange="filterTable()" class="text-sm">
                    <option value="">All Flags</option>
                    <option value="OOS">OOS (Purple)</option>
                    <option value="Restock Now">Restock Now (Red)</option>
                    <option value="Restock Soon">Restock Soon (Yellow)</option>
                    <option value="Monitor">Monitor (Blue)</option>
                    <option value="Healthy">Healthy (Green)</option>
                    <option value="No Velocity">No Velocity (Gray)</option>
                </select>
                <select id="filterTier" onchange="filterTable()" class="text-sm">
                    <option value="">All Tiers</option>
                    <option value="Critical">Critical</option>
                    <option value="High">High</option>
                    <option value="Medium">Medium</option>
                    <option value="Watch">Watch</option>
                </select>
                <select id="filterCategory" onchange="filterTable()" class="text-sm">
                    <option value="">All Categories</option>
                </select>
                <select id="filterSupplier" onchange="filterTable()" class="text-sm">
                    <option value="">All Suppliers</option>
                </select>
            </div>
        </div>

        <!-- Main Data Table -->
        <div class="bg-white rounded-lg border border-[#E5E7EB] overflow-x-auto">
            <table class="w-full text-xs" id="mainTable">
                <thead>
                    <tr class="bg-[#1B2A4A] text-white uppercase tracking-wider">
                        <th class="p-3 text-left cursor-pointer hover:text-gray-200" onclick="sortTable('flag')">Flag <span class="sort-arrow" data-col="flag">&#9650;&#9660;</span></th>
                        <th class="p-3 text-left cursor-pointer hover:text-gray-200" onclick="sortTable('risk_tier')">Tier <span class="sort-arrow" data-col="risk_tier">&#9650;&#9660;</span></th>
                        <th class="p-3 text-left cursor-pointer hover:text-gray-200" onclick="sortTable('sku')">SKU <span class="sort-arrow" data-col="sku">&#9650;&#9660;</span></th>
                        <th class="p-3 text-left cursor-pointer hover:text-gray-200" onclick="sortTable('product_name')">Product <span class="sort-arrow" data-col="product_name">&#9650;&#9660;</span></th>
                        <th class="p-3 text-left cursor-pointer hover:text-gray-200" onclick="sortTable('category')">Category <span class="sort-arrow" data-col="category">&#9650;&#9660;</span></th>
                        <th class="p-3 text-left cursor-pointer hover:text-gray-200" onclick="sortTable('supplier')">Supplier <span class="sort-arrow" data-col="supplier">&#9650;&#9660;</span></th>
                        <th class="p-3 text-right cursor-pointer hover:text-gray-200" onclick="sortTable('current_stock')">Stock <span class="sort-arrow" data-col="current_stock">&#9650;&#9660;</span></th>
                        <th class="p-3 text-right cursor-pointer hover:text-gray-200" onclick="sortTable('reorder_point')">Reorder Pt <span class="sort-arrow" data-col="reorder_point">&#9650;&#9660;</span></th>
                        <th class="p-3 text-right cursor-pointer hover:text-gray-200" onclick="sortTable('base_velocity')">Base Vel <span class="sort-arrow" data-col="base_velocity">&#9650;&#9660;</span></th>
                        <th class="p-3 text-right cursor-pointer hover:text-gray-200" onclick="sortTable('avg_daily_velocity')">Cur Vel <span class="sort-arrow" data-col="avg_daily_velocity">&#9650;&#9660;</span></th>
                        <th class="p-3 text-right cursor-pointer hover:text-gray-200" onclick="sortTable('projected_days')">Proj Days <span class="sort-arrow" data-col="projected_days">&#9650;&#9660;</span></th>
                        <th class="p-3 text-center">Trend</th>
                        <th class="p-3 text-right cursor-pointer hover:text-gray-200" onclick="sortTable('urgency_score')">Urgency <span class="sort-arrow" data-col="urgency_score">&#9650;&#9660;</span></th>
                        <th class="p-3 text-right cursor-pointer hover:text-gray-200" onclick="sortTable('total_lead_time')">Lead Time <span class="sort-arrow" data-col="total_lead_time">&#9650;&#9660;</span></th>
                        <th class="p-3 text-right cursor-pointer hover:text-gray-200" onclick="sortTable('monthly_profit_at_risk')">Profit/Mo <span class="sort-arrow" data-col="monthly_profit_at_risk">&#9650;&#9660;</span></th>
                        <th class="p-3 text-right cursor-pointer hover:text-gray-200" onclick="sortTable('missed_profit')">Missed $ <span class="sort-arrow" data-col="missed_profit">&#9650;&#9660;</span></th>
                        <th class="p-3 text-right cursor-pointer hover:text-gray-200" onclick="sortTable('recommended_qty')">Rec Qty <span class="sort-arrow" data-col="recommended_qty">&#9650;&#9660;</span></th>
                        <th class="p-3 text-right cursor-pointer hover:text-gray-200" onclick="sortTable('est_order_cost')">Est Cost <span class="sort-arrow" data-col="est_order_cost">&#9650;&#9660;</span></th>
                    </tr>
                </thead>
                <tbody id="tableBody">
                </tbody>
            </table>
        </div>

        <!-- Category Health -->
        <div class="bg-white rounded-lg p-6 border border-[#E5E7EB]">
            <h2 class="section-heading">Category Health</h2>
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4 mb-6">
                {cat_cards_html}
            </div>
            <div>
                <h3 class="text-md font-semibold text-[#333333] mb-3">Category Analysis</h3>
                {cat_analysis_html}
            </div>
        </div>

        <!-- Needs Investigation -->
        <div class="bg-[#FEF2F2] rounded-lg p-6 border-l-4 border-[#CC0000]">
            <h2 class="section-heading" style="border-bottom-color: #FECACA">
                Needs Investigation
                <span class="text-sm font-normal text-[#6B7280] ml-2">OOS 60+ days with stale restock dates</span>
            </h2>
            {inv_rows_html}
        </div>

        <!-- Methodology Notes -->
        <div class="bg-white rounded-lg border border-[#E5E7EB]">
            <button onclick="toggleMethodology()" class="w-full p-4 flex justify-between items-center text-left hover:bg-[#F5F5F5] transition rounded-lg">
                <h2 class="text-lg font-bold text-[#333333]">Methodology Notes</h2>
                <svg id="methodArrow" class="w-5 h-5 text-[#6B7280] transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
            </button>
            <div id="methodologyContent" class="methodology-content">
                <div class="px-6 pb-6 text-sm text-[#6B7280] space-y-4">
                    <div>
                        <h3 class="text-[#333333] font-semibold mb-1">Seasonal Projection</h3>
                        <p>Days until out-of-stock are calculated by walking forward day-by-day through the calendar, consuming stock at a seasonally-adjusted daily rate. Each product category has monthly coefficients (e.g., Blankets peak at 1.70x in December, trough at 0.20x in June/July). This gives a more accurate picture than flat velocity projection, especially during seasonal transitions.</p>
                    </div>
                    <div>
                        <h3 class="text-[#333333] font-semibold mb-1">Two-Layer Scoring</h3>
                        <p><strong>Urgency Flags</strong> answer "When do I need to act?" They compare projected days until OOS against total lead time plus a buffer. Purple = already OOS, Red = will be OOS before restock can arrive, Yellow = tight window, Blue = comfortable margin, Green = healthy stock.</p>
                        <p class="mt-1"><strong>Risk Tiers</strong> answer "How bad is it financially if I do not act?" They use monthly profit at risk (current velocity times margin times 30 days). Critical = over $5K/month, High = $1K-$5K, Medium = $250-$1K, Watch = under $250.</p>
                    </div>
                    <div>
                        <h3 class="text-[#333333] font-semibold mb-1">Recommended Order Quantity</h3>
                        <p>Projected consumption is summed over the full coverage window (lead time + buffer + target stock days) using seasonal coefficients. Current stock is subtracted. Default target is 60 days on hand after restock arrives. A production system would configure per product/category; overseas products would target 90-120 days.</p>
                    </div>
                    <div>
                        <h3 class="text-[#333333] font-semibold mb-1">Missed Profit</h3>
                        <p>For OOS items, estimated profit lost is calculated as: (days since last restock minus 30 days assumed sell-through) times daily profit. This represents the cost of inaction and helps prioritize restock urgency.</p>
                    </div>
                    <div>
                        <h3 class="text-[#333333] font-semibold mb-1">Margin Note</h3>
                        <p>Profit calculations use gross margin (unit price minus unit cost). A production system would factor in marketplace fees (2.4-2.9% + $0.30), payment processing, warehouse labor/storage, shipping, and returns, which typically reduce gross margin by 15-25 percentage points. The settings panel would support a margin adjustment factor.</p>
                    </div>
                    <div>
                        <h3 class="text-[#333333] font-semibold mb-1">Flat vs Projected Comparison</h3>
                        <p>When flat days and projected days diverge by more than 15%, a seasonal indicator badge appears. A red up-arrow with "Demand increasing" means projected OOS is sooner than flat (more urgent). A green down-arrow with "Demand decreasing" means projected OOS is later (less urgent).</p>
                    </div>
                </div>
            </div>
        </div>
    </main>

    <footer class="max-w-[1600px] mx-auto px-4 py-6 text-center text-xs text-[#9CA3AF]">
        Generated by OOS Intelligence Tool | Schneider Saddlery Technical Assessment
    </footer>

    <script>
    // Embedded data
    const ALL_PRODUCTS = {products_json};
    const SKU_RECS = {sku_recs_json};
    const SEASONALITY = {seasonality_json};
    const DAYS_PER_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    const MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    const FLAG_COLORS = {json.dumps(FLAG_COLORS)};
    const FLAG_WEIGHTS = {json.dumps(FLAG_WEIGHTS)};
    const TIER_ORDER = {{"Critical": 4, "High": 3, "Medium": 2, "Watch": 1}};
    const FLAG_ORDER = {{"OOS": 6, "Restock Now": 5, "Restock Soon": 4, "Monitor": 3, "No Velocity": 1, "Healthy": 2}};
    const AI_AVAILABLE = {'true' if ai_available else 'false'};

    const DEFAULTS = {json.dumps(DEFAULT_CONFIG)};

    let currentProducts = JSON.parse(JSON.stringify(ALL_PRODUCTS));
    let sortCol = 'sort_score';
    let sortAsc = false;

    // Initialize
    document.addEventListener('DOMContentLoaded', function() {{
        loadSettings();
        populateFilters();
        recalculate();
    }});

    // Settings persistence
    function loadSettings() {{
        const saved = localStorage.getItem('oos_settings');
        if (saved) {{
            try {{
                const cfg = JSON.parse(saved);
                if (cfg.red_days !== undefined) document.getElementById('cfg_red_days').value = cfg.red_days;
                if (cfg.yellow_days !== undefined) document.getElementById('cfg_yellow_days').value = cfg.yellow_days;
                if (cfg.blue_days !== undefined) document.getElementById('cfg_blue_days').value = cfg.blue_days;
                if (cfg.buffer_days !== undefined) document.getElementById('cfg_buffer_days').value = cfg.buffer_days;
                if (cfg.critical_threshold !== undefined) document.getElementById('cfg_critical').value = cfg.critical_threshold;
                if (cfg.high_threshold !== undefined) document.getElementById('cfg_high').value = cfg.high_threshold;
                if (cfg.medium_threshold !== undefined) document.getElementById('cfg_medium').value = cfg.medium_threshold;
                if (cfg.target_stock_days !== undefined) document.getElementById('cfg_target_days').value = cfg.target_stock_days;
                if (cfg.default_lead_time !== undefined) document.getElementById('cfg_lead_time').value = cfg.default_lead_time;
                if (cfg.default_reorder_point !== undefined) document.getElementById('cfg_reorder_pt').value = cfg.default_reorder_point;
            }} catch(e) {{}}
        }}
    }}

    function saveSettings() {{
        const cfg = getConfig();
        localStorage.setItem('oos_settings', JSON.stringify(cfg));
    }}

    function getConfig() {{
        return {{
            red_days: parseInt(document.getElementById('cfg_red_days').value) || 0,
            yellow_days: parseInt(document.getElementById('cfg_yellow_days').value) || 0,
            blue_days: parseInt(document.getElementById('cfg_blue_days').value) || 0,
            buffer_days: parseInt(document.getElementById('cfg_buffer_days').value) || 0,
            critical_threshold: parseInt(document.getElementById('cfg_critical').value) || 0,
            high_threshold: parseInt(document.getElementById('cfg_high').value) || 0,
            medium_threshold: parseInt(document.getElementById('cfg_medium').value) || 0,
            target_stock_days: parseInt(document.getElementById('cfg_target_days').value) || 0,
            default_lead_time: parseInt(document.getElementById('cfg_lead_time').value) || 0,
            default_reorder_point: parseInt(document.getElementById('cfg_reorder_pt').value) || 0,
        }};
    }}

    function resetDefaults() {{
        document.getElementById('cfg_red_days').value = DEFAULTS.red_days;
        document.getElementById('cfg_yellow_days').value = DEFAULTS.yellow_days;
        document.getElementById('cfg_blue_days').value = DEFAULTS.blue_days;
        document.getElementById('cfg_buffer_days').value = DEFAULTS.buffer_days;
        document.getElementById('cfg_critical').value = DEFAULTS.critical_threshold;
        document.getElementById('cfg_high').value = DEFAULTS.high_threshold;
        document.getElementById('cfg_medium').value = DEFAULTS.medium_threshold;
        document.getElementById('cfg_target_days').value = DEFAULTS.target_stock_days;
        document.getElementById('cfg_lead_time').value = DEFAULTS.default_lead_time;
        document.getElementById('cfg_reorder_pt').value = DEFAULTS.default_reorder_point;
        localStorage.removeItem('oos_settings');
        recalculate();
    }}

    // Seasonal projection in JS (mirrors Python)
    function jsProjectedDays(stock, baseVel, category, startMonth, startDay) {{
        if (baseVel < 0.01) return 365;
        let remaining = stock;
        let days = 0;
        let month = startMonth;
        let dayInMonth = startDay;
        const coeffs = SEASONALITY[category] || SEASONALITY["General"];
        while (remaining > 0 && days < 365) {{
            remaining -= baseVel * coeffs[month - 1];
            days++;
            dayInMonth++;
            if (dayInMonth > DAYS_PER_MONTH[month - 1]) {{
                dayInMonth = 1;
                month = (month % 12) + 1;
            }}
        }}
        return days;
    }}

    function jsProjectedOrderQty(stock, baseVel, category, startMonth, startDay, totalLead, bufferDays, targetDays) {{
        if (baseVel < 0.01) return 0;
        const window = totalLead + bufferDays + targetDays;
        let consumption = 0;
        let month = startMonth;
        let dayInMonth = startDay;
        const coeffs = SEASONALITY[category] || SEASONALITY["General"];
        for (let i = 0; i < window; i++) {{
            consumption += baseVel * coeffs[month - 1];
            dayInMonth++;
            if (dayInMonth > DAYS_PER_MONTH[month - 1]) {{
                dayInMonth = 1;
                month = (month % 12) + 1;
            }}
        }}
        return Math.max(0, Math.round(consumption - stock));
    }}

    function recalculate() {{
        const cfg = getConfig();
        saveSettings();
        const now = new Date();
        const curMonth = now.getMonth() + 1;
        const curDay = now.getDate();

        let oosCount = 0, atRisk = 0, dailyRevLost = 0, monthlyProfit = 0, missedTotal = 0;
        const flagCounts = {{}};
        const tierCounts = {{}};

        currentProducts = ALL_PRODUCTS.map(function(p) {{
            const item = JSON.parse(JSON.stringify(p));
            const totalLead = item.total_lead_time;
            const projDays = jsProjectedDays(item.current_stock, item.base_velocity, item.category, curMonth, curDay);
            const flatDays = item.avg_daily_velocity >= 0.01 ? item.current_stock / item.avg_daily_velocity : 9999;
            const dailyProfit = item.avg_daily_velocity * (item.unit_price - item.unit_cost);
            const monthProfit = Math.round(dailyProfit * 30 * 100) / 100;

            // Flag
            let flag;
            if (item.base_velocity < 0.01 && item.current_stock > 0) {{
                flag = "No Velocity";
            }} else if (item.current_stock === 0) {{
                flag = "OOS";
            }} else {{
                const urgency = projDays - (totalLead + cfg.buffer_days);
                if (urgency < cfg.red_days) flag = "Restock Now";
                else if (urgency < cfg.yellow_days) flag = "Restock Soon";
                else if (urgency < cfg.blue_days) flag = "Monitor";
                else flag = "Healthy";
            }}

            // Tier
            let tier;
            if (monthProfit > cfg.critical_threshold) tier = "Critical";
            else if (monthProfit > cfg.high_threshold) tier = "High";
            else if (monthProfit > cfg.medium_threshold) tier = "Medium";
            else tier = "Watch";

            const urgencyScore = Math.round((projDays - (totalLead + cfg.buffer_days)) * 10) / 10;
            const recQty = jsProjectedOrderQty(item.current_stock, item.base_velocity, item.category, curMonth, curDay, totalLead, cfg.buffer_days, cfg.target_stock_days);
            const estCost = Math.round(recQty * item.unit_cost * 100) / 100;
            const sortScore = (FLAG_WEIGHTS[flag] || 0) + monthProfit;

            item.projected_days = projDays;
            item.flat_days = Math.round(flatDays * 10) / 10;
            item.flag = flag;
            item.risk_tier = tier;
            item.urgency_score = urgencyScore;
            item.daily_profit = Math.round(dailyProfit * 100) / 100;
            item.monthly_profit_at_risk = monthProfit;
            item.recommended_qty = recQty;
            item.est_order_cost = estCost;
            item.sort_score = sortScore;

            // Summaries
            flagCounts[flag] = (flagCounts[flag] || 0) + 1;
            tierCounts[tier] = (tierCounts[tier] || 0) + 1;
            if (flag === "OOS") {{
                oosCount++;
                dailyRevLost += item.avg_daily_velocity * item.unit_price;
                missedTotal += item.missed_profit || 0;
            }}
            if (["OOS", "Restock Now", "Restock Soon"].includes(flag)) atRisk++;
            if (["OOS", "Restock Now"].includes(flag)) monthlyProfit += monthProfit;

            return item;
        }});

        // Update stats
        document.getElementById('stat_total').textContent = currentProducts.length;
        document.getElementById('stat_oos').textContent = oosCount;
        document.getElementById('stat_atrisk').textContent = atRisk;
        document.getElementById('stat_daily_rev').textContent = '$' + Math.round(dailyRevLost).toLocaleString();
        document.getElementById('stat_monthly').textContent = '$' + Math.round(monthlyProfit).toLocaleString();
        document.getElementById('stat_missed').textContent = '$' + Math.round(missedTotal).toLocaleString();

        sortAndRender();
    }}

    function populateFilters() {{
        const cats = new Set();
        const sups = new Set();
        ALL_PRODUCTS.forEach(function(p) {{
            cats.add(p.category);
            sups.add(p.supplier);
        }});
        const catSel = document.getElementById('filterCategory');
        Array.from(cats).sort().forEach(function(c) {{
            const opt = document.createElement('option');
            opt.value = c;
            opt.textContent = c;
            catSel.appendChild(opt);
        }});
        const supSel = document.getElementById('filterSupplier');
        Array.from(sups).sort().forEach(function(s) {{
            const opt = document.createElement('option');
            opt.value = s;
            opt.textContent = s;
            supSel.appendChild(opt);
        }});
    }}

    function sortTable(col) {{
        if (sortCol === col) {{
            sortAsc = !sortAsc;
        }} else {{
            sortCol = col;
            sortAsc = true;
        }}
        sortAndRender();
    }}

    function sortAndRender() {{
        const filtered = getFilteredProducts();

        filtered.sort(function(a, b) {{
            let aVal = a[sortCol];
            let bVal = b[sortCol];
            // Special sort for flags and tiers
            if (sortCol === 'flag') {{
                aVal = FLAG_ORDER[aVal] || 0;
                bVal = FLAG_ORDER[bVal] || 0;
            }} else if (sortCol === 'risk_tier') {{
                aVal = TIER_ORDER[aVal] || 0;
                bVal = TIER_ORDER[bVal] || 0;
            }}
            if (typeof aVal === 'string') {{
                aVal = aVal.toLowerCase();
                bVal = (bVal || '').toLowerCase();
            }}
            if (aVal < bVal) return sortAsc ? -1 : 1;
            if (aVal > bVal) return sortAsc ? 1 : -1;
            return 0;
        }});

        renderTable(filtered);
    }}

    function getFilteredProducts() {{
        const search = (document.getElementById('searchInput').value || '').toLowerCase();
        const flagF = document.getElementById('filterFlag').value;
        const tierF = document.getElementById('filterTier').value;
        const catF = document.getElementById('filterCategory').value;
        const supF = document.getElementById('filterSupplier').value;

        return currentProducts.filter(function(p) {{
            if (search && !(p.sku.toLowerCase().includes(search) ||
                p.product_name.toLowerCase().includes(search) ||
                p.supplier.toLowerCase().includes(search) ||
                p.category.toLowerCase().includes(search))) return false;
            if (flagF && p.flag !== flagF) return false;
            if (tierF && p.risk_tier !== tierF) return false;
            if (catF && p.category !== catF) return false;
            if (supF && p.supplier !== supF) return false;
            return true;
        }});
    }}

    function filterTable() {{
        sortAndRender();
    }}

    function escHtml(s) {{
        const div = document.createElement('div');
        div.textContent = s;
        return div.innerHTML;
    }}

    function renderTable(products) {{
        const tbody = document.getElementById('tableBody');
        let html = '';

        products.forEach(function(p, idx) {{
            const flagColor = FLAG_COLORS[p.flag] || '#6B7280';
            const tierColors = {{"Critical": "#CC0000", "High": "#D97706", "Medium": "#2563EB", "Watch": "#6B7280"}};
            const tierColor = tierColors[p.risk_tier] || '#6B7280';
            const rowBg = idx % 2 === 0 ? '#FFFFFF' : '#F9FAFB';

            // Trend badge
            let trendHtml = '';
            if (p.trend) {{
                const dir = p.trend.direction;
                let trendArrow = '&#9654;';
                let trendColor = '#2563EB';
                if (dir === 'increasing') {{ trendArrow = '&#9650;'; trendColor = '#CC0000'; }}
                else if (dir === 'decreasing') {{ trendArrow = '&#9660;'; trendColor = '#059669'; }}
                const tooltip = p.trend.next_3 ? p.trend.next_3.map(function(n) {{ return n.month + ' ' + n.coeff + 'x'; }}).join(', ') : '';
                trendHtml = '<span style="color:' + trendColor + '" title="' + escHtml(tooltip) + '">' + trendArrow + '</span>';
            }}

            // Flat vs projected divergence
            let projDisplay = p.projected_days;
            if (p.projected_days < 365 && p.flat_days < 9999) {{
                const diff = Math.abs(p.projected_days - p.flat_days) / Math.max(p.flat_days, 1);
                if (diff > 0.15) {{
                    if (p.projected_days < p.flat_days) {{
                        projDisplay = p.projected_days + ' <span class="text-[10px]" style="color:#CC0000" title="Flat: ' + p.flat_days + ' days">&#9650; Demand increasing</span>';
                    }} else {{
                        projDisplay = p.projected_days + ' <span class="text-[10px]" style="color:#059669" title="Flat: ' + p.flat_days + ' days">&#9660; Demand decreasing</span>';
                    }}
                }}
            }}

            // Below reorder point indicator
            let reorderBadge = '';
            if (p.below_reorder) {{
                reorderBadge = ' <span class="text-[10px] px-1 py-0.5 rounded" style="background: #D9770620; color: #D97706">Below RP</span>';
            }}

            // Has AI rec?
            const rec = SKU_RECS[p.sku];
            const hasRec = rec && rec.length > 0;
            const expandCls = hasRec ? 'cursor-pointer' : '';
            const expandTitle = hasRec ? 'title="Click to view AI recommendation"' : '';

            html += '<tr class="table-row border-b border-[#E5E7EB] ' + expandCls + '" style="background:' + rowBg + '" ' + expandTitle + ' onclick="toggleExpand(\\'' + p.sku + '\\')">';
            html += '<td class="p-3"><span class="px-2 py-1 rounded text-xs font-medium text-white" style="background:' + flagColor + '">' + escHtml(p.flag) + '</span></td>';
            html += '<td class="p-3"><span class="px-2 py-1 rounded text-xs font-medium" style="background:' + tierColor + '15; color:' + tierColor + '">' + escHtml(p.risk_tier) + '</span></td>';
            html += '<td class="p-3 text-[#333333] font-mono">' + escHtml(p.sku) + reorderBadge + '</td>';
            html += '<td class="p-3 text-[#333333] max-w-[200px] truncate" title="' + escHtml(p.product_name) + '">' + escHtml(p.product_name) + '</td>';
            html += '<td class="p-3 text-[#6B7280]">' + escHtml(p.category) + '</td>';
            html += '<td class="p-3 text-[#6B7280]">' + escHtml(p.supplier) + '</td>';
            html += '<td class="p-3 text-right text-[#333333]">' + p.current_stock.toLocaleString() + '</td>';
            html += '<td class="p-3 text-right text-[#6B7280]">' + p.reorder_point + '</td>';
            html += '<td class="p-3 text-right text-[#333333]">' + p.base_velocity + '</td>';
            html += '<td class="p-3 text-right text-[#333333]">' + p.avg_daily_velocity + '</td>';
            html += '<td class="p-3 text-right text-[#333333]">' + projDisplay + '</td>';
            html += '<td class="p-3 text-center">' + trendHtml + '</td>';
            html += '<td class="p-3 text-right text-[#333333]">' + p.urgency_score + '</td>';
            html += '<td class="p-3 text-right text-[#6B7280]">' + p.total_lead_time + 'd</td>';
            html += '<td class="p-3 text-right text-[#333333]">$' + p.monthly_profit_at_risk.toLocaleString(undefined, {{minimumFractionDigits: 0, maximumFractionDigits: 0}}) + '</td>';
            html += '<td class="p-3 text-right text-[#333333]">' + (p.missed_profit > 0 ? '$' + p.missed_profit.toLocaleString(undefined, {{minimumFractionDigits: 0, maximumFractionDigits: 0}}) : '-') + '</td>';
            html += '<td class="p-3 text-right text-[#333333]">' + (p.recommended_qty > 0 ? p.recommended_qty.toLocaleString() : '-') + '</td>';
            html += '<td class="p-3 text-right text-[#333333]">' + (p.est_order_cost > 0 ? '$' + p.est_order_cost.toLocaleString(undefined, {{minimumFractionDigits: 0, maximumFractionDigits: 0}}) : '-') + '</td>';
            html += '</tr>';

            // Expandable row for AI recommendation
            if (hasRec) {{
                html += '<tr class="expand-row border-b border-[#E5E7EB]" id="expand_' + p.sku + '">';
                html += '<td colspan="18" class="p-0"><div class="px-6 py-4 bg-[#F5F5F5] border-l-4" style="border-color:' + flagColor + '">';
                html += '<p class="text-xs text-[#6B7280] uppercase tracking-wider mb-1">AI Recommendation</p>';
                html += '<p class="text-sm text-[#333333]">' + escHtml(rec) + '</p>';
                html += '</div></td></tr>';
            }}
        }});

        tbody.innerHTML = html;
    }}

    function toggleExpand(sku) {{
        const row = document.getElementById('expand_' + sku);
        if (row) {{
            row.classList.toggle('visible');
        }}
    }}

    function toggleSettings() {{
        document.getElementById('settingsPanel').classList.toggle('open');
        document.getElementById('settingsOverlay').classList.toggle('open');
    }}

    function toggleMethodology() {{
        const content = document.getElementById('methodologyContent');
        const arrow = document.getElementById('methodArrow');
        content.classList.toggle('open');
        arrow.style.transform = content.classList.contains('open') ? 'rotate(180deg)' : '';
    }}
    </script>
</body>
</html>"""
    return html_content


# ---------------------------------------------------------------------------
# Section G: CLI Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="AI-Powered Out-of-Stock Intelligence Tool"
    )
    parser.add_argument(
        "--input",
        default=os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "sample_data", "inventory.csv"
        ),
        help="Path to inventory CSV file (default: sample_data/inventory.csv)",
    )
    parser.add_argument(
        "--output",
        default=os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "output", "oos_report.html"
        ),
        help="Path for output HTML report (default: output/oos_report.html)",
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Skip AI API calls (dashboard renders with quantitative data only)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  Out-of-Stock Intelligence Tool")
    print("  Schneider Saddlery Technical Assessment")
    print("=" * 60)

    # Load data
    print(f"\nLoading inventory from: {args.input}")
    if not os.path.exists(args.input):
        print(f"ERROR: File not found: {args.input}")
        sys.exit(1)

    products = load_csv(args.input)
    print(f"  Loaded {len(products)} products")

    # Analyze
    print("\nRunning seasonal projection analysis...")
    today = date.today()
    data = analyze_inventory(products, today=today)
    s = data["summary"]

    print(f"  OOS: {s['oos_count']} | At Risk: {s['at_risk_count']} | Healthy: {s['flags'].get('Healthy', 0)}")
    print(f"  Daily revenue lost: ${s['daily_revenue_lost']:,.2f}")
    print(f"  Monthly profit at risk: ${s['monthly_profit_at_risk']:,.2f}")
    print(f"  Missed profit to date: ${s['missed_profit_total']:,.2f}")

    # AI calls
    ai_results = {
        "executive_summary": None,
        "sku_recommendations": {},
        "category_patterns": {},
    }

    if args.no_ai:
        print("\nAI insights: SKIPPED (--no-ai flag)")
    else:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("\nAI insights: SKIPPED (ANTHROPIC_API_KEY not set)")
            print("  Set ANTHROPIC_API_KEY environment variable to enable AI analysis.")
            print("  All quantitative data and scoring remains fully functional.")
        else:
            print("\nGenerating AI insights (3 API calls)...")

            print("  [1/3] Executive summary...")
            ai_results["executive_summary"] = generate_executive_summary(data)
            if ai_results["executive_summary"]:
                print("    Done.")
            else:
                print("    Failed (will show placeholder).")

            print("  [2/3] Per-SKU recommendations...")
            ai_results["sku_recommendations"] = generate_sku_recommendations(data)
            print(f"    Generated {len(ai_results['sku_recommendations'])} recommendations.")

            print("  [3/3] Category patterns and investigation notes...")
            ai_results["category_patterns"] = generate_category_patterns(data)
            if ai_results["category_patterns"]:
                print("    Done.")
            else:
                print("    Failed (will show placeholder).")

    # Generate HTML
    print("\nGenerating HTML dashboard...")
    html_content = generate_html(data, ai_results)

    # Ensure output directory exists
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"  Saved to: {args.output}")
    file_size = os.path.getsize(args.output)
    print(f"  File size: {file_size / 1024:.1f} KB")

    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    print(f"  Total SKUs:           {s['total_skus']}")
    print(f"  Currently OOS:        {s['oos_count']}")
    print(f"  At Risk:              {s['at_risk_count']}")
    print(f"  Daily Revenue Lost:   ${s['daily_revenue_lost']:,.2f}")
    print(f"  Monthly Profit Risk:  ${s['monthly_profit_at_risk']:,.2f}")
    print(f"  Missed Profit:        ${s['missed_profit_total']:,.2f}")
    print(f"\n  Flags: Purple={s['flags']['OOS']} Red={s['flags']['Restock Now']} "
          f"Yellow={s['flags']['Restock Soon']} Blue={s['flags']['Monitor']} "
          f"Green={s['flags']['Healthy']}")
    if s['flags'].get('No Velocity', 0) > 0:
        print(f"         Gray (No Velocity)={s['flags']['No Velocity']}")
    print(f"  Tiers: Critical={s['tiers']['Critical']} High={s['tiers']['High']} "
          f"Medium={s['tiers']['Medium']} Watch={s['tiers']['Watch']}")
    ai_status = "Enabled" if ai_results["executive_summary"] else "Disabled"
    print(f"  AI Insights:          {ai_status}")
    print(f"\n  Open {args.output} in a browser to view the report.")
    print("=" * 60)


if __name__ == "__main__":
    main()
