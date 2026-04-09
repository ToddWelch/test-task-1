#!/usr/bin/env python3
"""
AI-Powered Out-of-Stock Intelligence Tool
Schneider Saddlery Technical Assessment

Generates a self-contained HTML dashboard with seasonally-projected
inventory analysis and AI-generated insights via Claude API.
"""

import argparse
import base64
import csv
import html
import json
import os
import re
import sys
from datetime import datetime, date, timedelta

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
    "Watch": 100_000,
    "Healthy": 0,
    "No Velocity": 0,
}

FLAG_COLORS = {
    "OOS": "#7C3AED",
    "Restock Now": "#CC0000",
    "Restock Soon": "#D97706",
    "Watch": "#2563EB",
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


FULL_MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def format_seasonal_context(category, current_month):
    """Pre-compute human-readable seasonal text for a category.

    Returns a dict with named months and coefficients so that AI prompts
    never receive raw coefficient arrays.
    """
    coefficients = SEASONALITY.get(category, SEASONALITY["General"])
    current_coeff = coefficients[current_month - 1]
    current_month_name = FULL_MONTH_NAMES[current_month - 1]

    # Next 3 months with names
    next_3 = []
    for i in range(1, 4):
        idx = (current_month - 1 + i) % 12
        next_3.append({
            "name": FULL_MONTH_NAMES[idx],
            "coeff": coefficients[idx],
        })

    # Peak and low months
    peak_idx = max(range(12), key=lambda i: coefficients[i])
    low_idx = min(range(12), key=lambda i: coefficients[i])

    # Direction
    avg_next = sum(n["coeff"] for n in next_3) / 3
    if avg_next > current_coeff * 1.15:
        direction = "increasing"
    elif avg_next < current_coeff * 0.85:
        direction = "decreasing"
    else:
        direction = "stable"

    next_3_text = ", ".join(
        f"{n['name']} {n['coeff']}x" for n in next_3
    )

    return {
        "current_month_name": current_month_name,
        "current_coeff": current_coeff,
        "next_3_text": next_3_text,
        "peak_month": FULL_MONTH_NAMES[peak_idx],
        "peak_coeff": coefficients[peak_idx],
        "low_month": FULL_MONTH_NAMES[low_idx],
        "low_coeff": coefficients[low_idx],
        "direction": direction,
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
        return "Watch"
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
        return "Low"


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
    """Higher score = higher priority in the table.
    Sorts by flag urgency first (OOS > Restock Now > Restock Soon > Watch > Healthy),
    then by monthly_profit_at_risk descending within each flag group."""
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
                  "Watch": 0, "Healthy": 0, "No Velocity": 0},
        "tiers": {"Critical": 0, "High": 0, "Medium": 0, "Low": 0},
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

        # Estimated OOS date calculation
        est_oos_date = None
        est_oos_date_raw = None
        if p["current_stock"] == 0:
            # Already OOS: approximate when stock hit zero (last restock + 30 days)
            # Cap to today so OOS products never show a future estimated OOS date
            last_dt = datetime.strptime(p["last_restock_date"], "%Y-%m-%d").date()
            approx_date = min(last_dt + timedelta(days=30), today)
            est_oos_date = "~" + approx_date.strftime("%Y-%m-%d")
            est_oos_date_raw = approx_date.strftime("%Y-%m-%d")
        elif flag not in ("Healthy", "No Velocity") or (flag == "Healthy" and proj_days < 365):
            if proj_days < 365:
                oos_date = today + timedelta(days=proj_days)
                est_oos_date = oos_date.strftime("%Y-%m-%d")
                est_oos_date_raw = oos_date.strftime("%Y-%m-%d")

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
            "est_oos_date": est_oos_date,
            "est_oos_date_raw": est_oos_date_raw,
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

SYSTEM_MESSAGE = (
    "You are an inventory intelligence analyst writing a report for an "
    "operations manager at an equestrian e-commerce company. This is a "
    "Monday morning briefing.\n\n"
    "STRICT RULES:\n"
    "- ONLY reference data points provided in the context below. Do not "
    "invent or estimate any numbers.\n"
    "- Every dollar amount, percentage, velocity, date, product name, SKU, "
    "supplier name, and quantity you mention MUST appear exactly in the "
    "provided data.\n"
    "- Do NOT speculate on causes. Do not use phrases like \"likely due to\", "
    "\"caused by\", \"driven by\", \"because of\", \"as a result of\", or "
    "\"attributed to\". If root cause is unknown, say \"requires investigation.\"\n"
    "- Only recommend these actions: reorder now, expedite review, monitor "
    "closely, investigate stale OOS, verify reorder point. Do not suggest "
    "supplier switches, pricing changes, marketing actions, or other "
    "operational moves not supported by the data.\n"
    "- Only reference SKUs, product names, categories, and suppliers that "
    "appear in the provided data. Do not mention brands, regions, channels, "
    "warehouses, customer segments, or market conditions not in the data.\n"
    "- Do NOT generate any numbers through calculation. All numbers are "
    "pre-computed and provided to you.\n"
    "- Write in plain English. No jargon. The reader is a non-technical "
    "operations manager.\n"
    "- Be specific and actionable. Lead with the most important information.\n"
    "- Never use em dashes."
)


# ---- Validation ----

def validate_ai_output(text, products, stats):
    """Validate AI output references only real data. Returns (is_valid, warnings)."""
    warnings = []

    # Check for SKU references that don't exist
    sku_refs = re.findall(r'SCH-\d{5}', text)
    valid_skus = {p['sku'] for p in products}
    for sku in sku_refs:
        if sku not in valid_skus:
            warnings.append(f"Referenced unknown SKU: {sku}")

    # Check for banned causal language
    banned_phrases = [
        "likely due to", "caused by", "driven by", "because of",
        "as a result of", "attributed to", "stems from", "resulting from"
    ]
    text_lower = text.lower()
    for phrase in banned_phrases:
        if phrase in text_lower:
            warnings.append(f"Contains banned causal phrase: '{phrase}'")

    # Check for unauthorized action recommendations
    action_phrases = [
        "switch supplier", "change supplier", "find new supplier",
        "adjust pricing", "raise price", "lower price",
        "run promotion", "increase marketing", "discount"
    ]
    for phrase in action_phrases:
        if phrase in text_lower:
            warnings.append(f"Contains unauthorized action: '{phrase}'")

    # Check for external entity references
    external_phrases = [
        "market trend", "competitor", "industry",
        "economic", "inflation", "recession"
    ]
    for phrase in external_phrases:
        if phrase in text_lower:
            warnings.append(f"References external context: '{phrase}'")

    is_valid = len(warnings) == 0
    return is_valid, warnings


def generate_with_validation(client, system_msg, user_msg, products, stats,
                             max_tokens=1500, max_retries=1):
    """Generate AI text with validation and fallback."""
    for attempt in range(max_retries + 1):
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=max_tokens,
            temperature=0.3,
            system=system_msg,
            messages=[{"role": "user", "content": user_msg}]
        )
        text = response.content[0].text
        is_valid, warnings = validate_ai_output(text, products, stats)

        if is_valid:
            return text, True

        if attempt < max_retries:
            print(f"  AI validation failed (attempt {attempt + 1}): {warnings}")
            print("  Retrying...")
        else:
            print(f"  AI validation failed after {max_retries + 1} attempts: {warnings}")
            print("  Falling back to templated text.")
            return None, False

    return None, False


# ---- Prompt Formatters ----

def format_executive_prompt(products, categories, stats):
    """Build the user message for the executive summary prompt."""
    current_month = datetime.now().month

    # Top 5 by sort_score (already sorted)
    top5 = products[:5]
    top5_lines = []
    for p in top5:
        top5_lines.append(
            f"- {p['sku']} {p['product_name']} | Flag: {p['flag']} | "
            f"Tier: {p['risk_tier']} | Stock: {p['current_stock']} | "
            f"Current velocity: {p['trend']['current_velocity']}/day | "
            f"Lead time: {p['total_lead_time']}d | "
            f"Monthly profit: ${p['monthly_profit_at_risk']:,.2f} | "
            f"Missed profit: ${p['missed_profit']:,.2f} | "
            f"Supplier: {p['supplier']} | "
            f"Est OOS date: {p['est_oos_date'] or 'N/A'}"
        )
    top5_text = "\n".join(top5_lines)

    # Category breakdown
    cat_lines = []
    increasing_cats = []
    decreasing_cats = []
    current_month_name = FULL_MONTH_NAMES[current_month - 1]
    for name, c in categories.items():
        trend = get_seasonal_trend(0, name, current_month)
        coeff = trend["current_coeff"]
        cat_lines.append(
            f"- {name}: {c['total']} SKUs | {c['oos']} OOS | "
            f"{c['at_risk']} at risk | ${c['profit_at_risk']:,.2f}/mo profit at risk | "
            f"Current month ({current_month_name}): {coeff}x"
        )
        if trend["direction"] == "increasing":
            increasing_cats.append(name)
        elif trend["direction"] == "decreasing":
            decreasing_cats.append(name)
    cat_text = "\n".join(cat_lines)

    # Supplier concentration
    supplier_flags = {}
    for p in products:
        if p["flag"] in ("OOS", "Restock Now", "Restock Soon"):
            sup = p["supplier"]
            if sup not in supplier_flags:
                supplier_flags[sup] = {"count": 0, "profit": 0.0}
            supplier_flags[sup]["count"] += 1
            supplier_flags[sup]["profit"] += p["monthly_profit_at_risk"]
    supplier_lines = []
    for sup, info in sorted(supplier_flags.items(), key=lambda x: -x[1]["profit"]):
        supplier_lines.append(
            f"- {sup}: {info['count']} flagged items | "
            f"${info['profit']:,.2f}/mo at risk"
        )
    supplier_text = "\n".join(supplier_lines) if supplier_lines else "- No supplier concentration issues"

    prompt = (
        "Write a 3-4 paragraph executive summary of the current out-of-stock "
        "situation for a Monday morning operations meeting. Lead with the most "
        "urgent information and end with a forward-looking seasonal note.\n\n"
        "CURRENT INVENTORY STATUS:\n"
        f"- Total SKUs analyzed: {stats['total_skus']}\n"
        f"- Currently out of stock: {stats['oos_count']} products\n"
        f"- At risk of stockout (Restock + Soon flags): {stats['at_risk_count']} products\n"
        f"- Estimated daily revenue being lost from OOS items: ${stats['daily_revenue_lost']:,.2f}\n"
        f"- Total monthly profit at risk (OOS + Restock flagged items): ${stats['monthly_profit_at_risk']:,.2f}\n"
        f"- Estimated missed profit to date from current OOS items: ${stats['missed_profit_total']:,.2f}\n\n"
        "TOP 5 MOST URGENT ITEMS (by financial impact):\n"
        f"{top5_text}\n\n"
        "CATEGORY BREAKDOWN:\n"
        f"{cat_text}\n\n"
        "SUPPLIER CONCENTRATION:\n"
        f"{supplier_text}\n\n"
        "SEASONAL CONTEXT:\n"
        f"- Current month: {datetime.now().strftime('%B')} (month {current_month})\n"
        f"- Categories with increasing demand over next 3 months: {', '.join(increasing_cats) if increasing_cats else 'None'}\n"
        f"- Categories with decreasing demand over next 3 months: {', '.join(decreasing_cats) if decreasing_cats else 'None'}\n\n"
        "Write the summary in 3-4 paragraphs. Paragraph 1: The headline situation "
        "(how many OOS, how much money at risk, the top 1-2 fires). Paragraph 2: "
        "The pattern (which categories and suppliers have the most exposure, any "
        "concentration risk). Paragraph 3: Seasonal outlook (what is about to get "
        "better or worse, and what that means for ordering now). Keep it under 300 words."
    )
    return prompt


def format_sku_prompt(item):
    """Build the user message for a single per-SKU recommendation."""
    trend = item["trend"]
    current_month = datetime.now().month
    seasonal = format_seasonal_context(item["category"], current_month)

    # Trend description
    if seasonal["direction"] == "increasing":
        trend_desc = "Demand increasing"
    elif seasonal["direction"] == "decreasing":
        trend_desc = "Demand decreasing"
    else:
        trend_desc = "Demand stable"

    prompt = (
        "Write a 2-3 sentence restock recommendation for this specific product. "
        "Be direct and actionable. Reference only the specific numbers provided below.\n\n"
        "PRODUCT DATA:\n"
        f"- SKU: {item['sku']}\n"
        f"- Product: {item['product_name']}\n"
        f"- Category: {item['category']}\n"
        f"- Supplier: {item['supplier']}\n"
        f"- Current stock: {item['current_stock']} units\n"
        f"- Reorder point: {item['reorder_point']} units\n"
        f"- Base velocity (annual avg): {item['base_velocity']}/day\n"
        f"- Current velocity (seasonal): {trend['current_velocity']}/day\n"
        f"- Projected days until OOS: {item['projected_days']}\n"
        f"- Estimated OOS date: {item['est_oos_date'] or 'N/A'}\n"
        f"- Urgency score: {item['urgency_score']} days\n"
        f"- Total lead time: {item['total_lead_time']} days\n"
        f"- Flag: {item['flag']}\n"
        f"- Tier: {item['risk_tier']}\n"
        f"- Monthly profit at risk: ${item['monthly_profit_at_risk']:,.2f}\n"
        f"- Missed profit to date: ${item['missed_profit']:,.2f}\n"
        f"- Recommended order quantity: {item['recommended_qty']} units\n"
        f"- Estimated order cost: ${item['est_order_cost']:,.2f}\n"
        f"- Seasonal trend: {trend_desc}\n"
        f"- Current month ({seasonal['current_month_name']}): {seasonal['current_coeff']}x\n"
        f"- Next 3 months: {seasonal['next_3_text']}\n"
        f"- Peak month: {seasonal['peak_month']} at {seasonal['peak_coeff']}x\n"
        f"- Low month: {seasonal['low_month']} at {seasonal['low_coeff']}x\n\n"
        "ALLOWED ACTIONS: reorder now, expedite review, monitor closely, "
        "investigate stale OOS, verify reorder point.\n\n"
        "Write exactly 2-3 sentences. Sentence 1: What to do and why (order X units, "
        "expected to arrive by Y, covering Z days of demand). Sentence 2: The financial "
        "context (how much profit is at risk or already missed). Sentence 3 (if relevant): "
        "Any seasonal consideration (demand increasing/decreasing, order ahead of peak, etc.). "
        "Do not repeat the product name or SKU since it will be displayed next to the product row."
    )
    return prompt


def format_category_prompt(categories, products, stats):
    """Build the user message for the category patterns prompt."""
    current_month = datetime.now().month

    cat_lines = []
    for name, c in categories.items():
        seasonal = format_seasonal_context(name, current_month)

        # Count flags within category
        restock_count = sum(1 for s in c["skus"] if s["flag"] == "Restock Now")
        soon_count = sum(1 for s in c["skus"] if s["flag"] == "Restock Soon")
        watch_count = sum(1 for s in c["skus"] if s["flag"] == "Watch")
        healthy_count = sum(1 for s in c["skus"] if s["flag"] == "Healthy")
        oos_pct = round(c["oos"] / c["total"] * 100) if c["total"] > 0 else 0

        # Missed profit for category
        cat_missed = sum(s["missed_profit"] for s in c["skus"])

        # Top OOS item by monthly profit
        oos_items = [s for s in c["skus"] if s["flag"] == "OOS"]
        if oos_items:
            top_oos = max(oos_items, key=lambda x: x["monthly_profit_at_risk"])
            top_oos_str = f"{top_oos['product_name']} (${top_oos['monthly_profit_at_risk']:,.2f}/mo)"
        else:
            top_oos_str = "None"

        # Suppliers in category
        suppliers = {}
        for s in c["skus"]:
            suppliers[s["supplier"]] = suppliers.get(s["supplier"], 0) + 1
        supplier_str = ", ".join(
            f"{k} ({v})" for k, v in sorted(suppliers.items(), key=lambda x: -x[1])
        )

        # Avg lead time
        lead_times = [s["total_lead_time"] for s in c["skus"]]
        avg_lead = round(sum(lead_times) / len(lead_times)) if lead_times else 0

        cat_lines.append(
            f"{name}:\n"
            f"- Total SKUs: {c['total']}\n"
            f"- OOS: {c['oos']} ({oos_pct}%)\n"
            f"- Restock flag: {restock_count}\n"
            f"- Soon flag: {soon_count}\n"
            f"- Watch flag: {watch_count}\n"
            f"- Healthy: {healthy_count}\n"
            f"- Total monthly profit at risk: ${c['profit_at_risk']:,.2f}\n"
            f"- Total missed profit: ${cat_missed:,.2f}\n"
            f"- Current month ({seasonal['current_month_name']}): {seasonal['current_coeff']}x\n"
            f"- Next 3 months: {seasonal['next_3_text']}\n"
            f"- Peak month: {seasonal['peak_month']} at {seasonal['peak_coeff']}x\n"
            f"- Low month: {seasonal['low_month']} at {seasonal['low_coeff']}x\n"
            f"- Seasonal direction: {seasonal['direction']}\n"
            f"- Top OOS item: {top_oos_str}\n"
            f"- Primary suppliers: {supplier_str}\n"
            f"- Average lead time: {avg_lead}d"
        )
    cat_text = "\n\n".join(cat_lines)

    # Supplier risk: suppliers with 3+ flagged items
    supplier_data = {}
    for p in products:
        if p["flag"] in ("OOS", "Restock Now", "Restock Soon"):
            sup = p["supplier"]
            if sup not in supplier_data:
                supplier_data[sup] = {
                    "count": 0, "categories": set(),
                    "leads": [], "profit": 0.0
                }
            supplier_data[sup]["count"] += 1
            supplier_data[sup]["categories"].add(p["category"])
            supplier_data[sup]["leads"].append(p["total_lead_time"])
            supplier_data[sup]["profit"] += p["monthly_profit_at_risk"]

    supplier_risk_lines = []
    for sup, info in sorted(supplier_data.items(), key=lambda x: -x[1]["profit"]):
        if info["count"] >= 3:
            avg_lead = round(sum(info["leads"]) / len(info["leads"]))
            supplier_risk_lines.append(
                f"- {sup}: {info['count']} flagged items across "
                f"{len(info['categories'])} categories | Avg lead time: {avg_lead}d | "
                f"Total profit at risk: ${info['profit']:,.2f}/mo"
            )
    supplier_risk_text = "\n".join(supplier_risk_lines) if supplier_risk_lines else "- No suppliers with 3+ flagged items"

    prompt = (
        "Write a brief category-by-category analysis highlighting patterns, risks, "
        "and seasonal considerations. Focus on actionable insights, not restating "
        "the numbers.\n\n"
        "CATEGORY DATA:\n"
        f"{cat_text}\n\n"
        "SUPPLIER RISK:\n"
        f"{supplier_risk_text}\n\n"
        "Write 1-2 sentences per category, focusing on the most actionable insight "
        "for each. Then add a final paragraph on any supplier concentration risks "
        "(multiple critical items from the same supplier or long lead time suppliers "
        "with high exposure). Keep the entire analysis under 250 words. Do not "
        "speculate on causes for stockouts. If a pattern is unclear, say it requires "
        "investigation."
    )
    return prompt


def format_investigation_prompt(stale_items, combined_monthly, combined_missed):
    """Build the user message for the needs-investigation prompt."""
    item_lines = []
    for p in stale_items:
        est_days_oos = p.get("days_since_restock", 0)
        if est_days_oos > 30:
            est_days_oos = est_days_oos - 30
        else:
            est_days_oos = 0
        item_lines.append(
            f"- {p['sku']} {p['product_name']} | Category: {p['category']} | "
            f"Supplier: {p['supplier']} | Base velocity: {p['base_velocity']}/day | "
            f"Last restock: {p['last_restock_date']} | "
            f"Estimated days OOS: ~{est_days_oos} | "
            f"Monthly profit when in stock: ${p['monthly_profit_at_risk']:,.2f} | "
            f"Estimated missed profit: ${p['missed_profit']:,.2f}"
        )
    items_text = "\n".join(item_lines)

    prompt = (
        "Write a brief note about products that have been out of stock for an "
        "extended period with no recent restock activity. These items need a "
        "sourcing decision.\n\n"
        "STALE OOS ITEMS:\n"
        f"{items_text}\n\n"
        f"TOTAL: {len(stale_items)} products have been OOS for 60+ days\n"
        f"Combined monthly profit when in stock: ${combined_monthly:,.2f}\n"
        f"Combined estimated missed profit: ${combined_missed:,.2f}\n\n"
        "Write 2-3 sentences. Note how many items have been OOS for over 60 days "
        "and the combined financial impact. Group by pattern if visible (same "
        "supplier, same category, etc.). State that each item needs a sourcing "
        "decision: reorder now, find an alternative supplier, or formally "
        "discontinue. Do not speculate about specific reasons for the extended "
        "stockout. Keep it under 100 words."
    )
    return prompt


# ---- Fallback Templates ----

def fallback_executive_summary(stats):
    """Deterministic executive summary when AI is unavailable."""
    return (
        f"Of {stats['total_skus']} SKUs analyzed, {stats['oos_count']} are currently "
        f"out of stock and {stats['at_risk_count']} additional products are at risk of "
        f"stockout. Estimated daily revenue lost from OOS items is "
        f"${stats['daily_revenue_lost']:,.2f}, with ${stats['monthly_profit_at_risk']:,.2f} "
        f"in total monthly profit at risk. Missed profit to date from current OOS items "
        f"is estimated at ${stats['missed_profit_total']:,.2f}.\n\n"
        f"The most urgent item is {stats['top_item_name']} ({stats['top_item_sku']}), "
        f"which is {stats['top_item_flag']} with ${stats['top_item_monthly']:,.2f} in "
        f"monthly profit at risk and an estimated ${stats['top_item_missed']:,.2f} in "
        f"missed profit to date."
    )


def fallback_sku_recommendation(item):
    """Deterministic per-SKU recommendation when AI is unavailable."""
    if item['current_stock'] == 0:
        action = "Reorder now"
        context = (
            f"This product has been out of stock since approximately {item['est_oos_date'] or 'unknown'}. "
            f"With a lead time of {item['total_lead_time']} days, new stock would arrive "
            f"approximately {item['total_lead_time']} days after ordering."
        )
    else:
        action = "Reorder now"
        context = (
            f"Current stock of {item['current_stock']} units covers approximately "
            f"{item['projected_days']} days at current velocity. Lead time is "
            f"{item['total_lead_time']} days."
        )

    financial = (
        f"${item['monthly_profit_at_risk']:,.2f} in monthly profit is at risk."
    )

    if item['missed_profit'] and item['missed_profit'] > 0:
        financial += f" Estimated missed profit to date: ${item['missed_profit']:,.2f}."

    order = (
        f"Recommended order: {item['recommended_qty']} units "
        f"(estimated cost: ${item['est_order_cost']:,.2f})."
    )

    return f"{action}. {context} {financial} {order}"


def fallback_category_analysis(categories):
    """Deterministic category analysis when AI is unavailable."""
    current_month = datetime.now().month
    lines = []
    for name, c in categories.items():
        trend = get_seasonal_trend(0, name, current_month)
        lines.append(
            f"{name}: {c['oos']} OOS, {c['at_risk']} at risk, "
            f"${c['profit_at_risk']:,.2f}/mo profit at risk. "
            f"Season: {trend['current_coeff']}x (direction: {trend['direction']})."
        )
    return "\n".join(lines)


def fallback_investigation(stale_items, combined_monthly, combined_missed):
    """Deterministic investigation note when AI is unavailable."""
    return (
        f"{len(stale_items)} products have been out of stock for over 60 days with "
        f"no recent restock activity. Combined monthly profit when in stock: "
        f"${combined_monthly:,.2f}. Estimated missed profit to date: "
        f"${combined_missed:,.2f}. Each item requires a sourcing decision: "
        f"reorder now, find an alternative supplier, or formally discontinue."
    )


# ---- Main AI Generation ----

def generate_ai_insights(products, categories, stats, needs_investigation):
    """Generate all AI insight sections with validation and fallback."""

    # Enrich stats with top item info for fallback
    if products:
        top = products[0]
        stats["top_item_name"] = top["product_name"]
        stats["top_item_sku"] = top["sku"]
        stats["top_item_flag"] = top["flag"]
        stats["top_item_monthly"] = top["monthly_profit_at_risk"]
        stats["top_item_missed"] = top["missed_profit"]

    if not os.environ.get('ANTHROPIC_API_KEY'):
        print("  No ANTHROPIC_API_KEY set. Using fallback templates.")
        return generate_fallback_insights(products, categories, stats, needs_investigation)

    try:
        import anthropic
        client = anthropic.Anthropic()
        system_msg = SYSTEM_MESSAGE
        insights = {}

        # 1. Executive Summary
        print("  [1/4] Executive summary...")
        exec_prompt = format_executive_prompt(products, categories, stats)
        exec_text, exec_valid = generate_with_validation(
            client, system_msg, exec_prompt, products, stats
        )
        insights['executive_summary'] = exec_text or fallback_executive_summary(stats)
        print(f"    {'Done.' if exec_valid else 'Used fallback.'}")

        # 2. Per-SKU Recommendations (one call per item, capped at 15)
        print("  [2/4] Per-SKU recommendations...")
        priority_items = [
            p for p in products
            if p['flag'] in ('OOS', 'Restock Now')
            and p['risk_tier'] in ('Critical', 'High')
        ][:15]

        sku_recs = {}
        for i, item in enumerate(priority_items):
            sku_prompt = format_sku_prompt(item)
            sku_text, sku_valid = generate_with_validation(
                client, system_msg, sku_prompt, products, stats,
                max_tokens=300
            )
            sku_recs[item['sku']] = sku_text or fallback_sku_recommendation(item)
        insights['sku_recommendations'] = sku_recs
        print(f"    Generated {len(sku_recs)} recommendations.")

        # 3. Category Analysis
        print("  [3/4] Category patterns...")
        cat_prompt = format_category_prompt(categories, products, stats)
        cat_text, cat_valid = generate_with_validation(
            client, system_msg, cat_prompt, products, stats
        )
        insights['category_analysis'] = cat_text or fallback_category_analysis(categories)
        print(f"    {'Done.' if cat_valid else 'Used fallback.'}")

        # 4. Needs Investigation
        print("  [4/4] Investigation notes...")
        stale_items = [p for p in needs_investigation]
        if stale_items:
            combined_monthly = sum(i['monthly_profit_at_risk'] for i in stale_items)
            combined_missed = sum(i.get('missed_profit', 0) for i in stale_items)
            inv_prompt = format_investigation_prompt(
                stale_items, combined_monthly, combined_missed
            )
            inv_text, inv_valid = generate_with_validation(
                client, system_msg, inv_prompt, products, stats
            )
            insights['investigation_notes'] = inv_text or fallback_investigation(
                stale_items, combined_monthly, combined_missed
            )
            print(f"    {'Done.' if inv_valid else 'Used fallback.'}")
        else:
            insights['investigation_notes'] = None
            print("    No stale OOS items found.")

        return insights

    except Exception as e:
        print(f"  AI generation failed: {e}")
        print("  Using fallback templates for all sections.")
        return generate_fallback_insights(products, categories, stats, needs_investigation)


def generate_fallback_insights(products, categories, stats, needs_investigation):
    """Generate all sections using deterministic templates."""
    # Enrich stats with top item info for fallback executive summary
    if products and "top_item_name" not in stats:
        top = products[0]
        stats["top_item_name"] = top["product_name"]
        stats["top_item_sku"] = top["sku"]
        stats["top_item_flag"] = top["flag"]
        stats["top_item_monthly"] = top["monthly_profit_at_risk"]
        stats["top_item_missed"] = top["missed_profit"]

    stale_items = [p for p in needs_investigation]
    combined_monthly = sum(i['monthly_profit_at_risk'] for i in stale_items)
    combined_missed = sum(i.get('missed_profit', 0) for i in stale_items)

    priority_items = [
        p for p in products
        if p['flag'] in ('OOS', 'Restock Now')
        and p['risk_tier'] in ('Critical', 'High')
    ][:15]

    return {
        'executive_summary': fallback_executive_summary(stats),
        'sku_recommendations': {
            item['sku']: fallback_sku_recommendation(item) for item in priority_items
        },
        'category_analysis': fallback_category_analysis(categories),
        'investigation_notes': fallback_investigation(
            stale_items, combined_monthly, combined_missed
        ) if stale_items else None,
    }


# ---------------------------------------------------------------------------
# Section F: HTML Dashboard Generator
# ---------------------------------------------------------------------------

def clean_ai_text(text):
    """Convert markdown formatting in AI output to HTML.

    Applies html.escape() first to neutralize any raw HTML in the AI output,
    then converts markdown patterns to safe HTML tags.
    """
    if not text:
        return text

    # Step 1: Escape any HTML in the raw AI text
    text = html.escape(str(text))

    # Step 2: Convert markdown headers (### Header) to bold text with breaks
    text = re.sub(r'^#{1,6}\s+(.+)$', r'<br><strong>\1</strong><br>', text, flags=re.MULTILINE)

    # Step 3: Convert bold (**text**) before italic (*text*) to avoid conflicts
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)

    # Step 4: Convert italic (*text*) -- single asterisks
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)

    # Step 5: Convert bullet points to HTML (must come before newline conversion)
    text = re.sub(r'^\s*[-*]\s+', '<br>&bull; ', text, flags=re.MULTILINE)

    # Step 6: Convert paragraph breaks (double newline) before single newlines
    text = text.replace('\n\n', '<br><br>')
    text = text.replace('\n', '<br>')

    # Step 7: Clean up any leading <br> at the start
    text = re.sub(r'^(<br>)+', '', text)

    return text


def generate_html(data, ai_results, config=None):
    """Generate self-contained HTML dashboard."""
    cfg = config or DEFAULT_CONFIG
    products_json = json.dumps(data["products"], default=str).replace('</','<\\/')
    summary = data["summary"]
    categories = data["categories"]
    investigation = data["needs_investigation"]

    exec_summary = ai_results.get("executive_summary")
    sku_recs = ai_results.get("sku_recommendations", {})
    cat_analysis = ai_results.get("category_analysis", "")
    inv_notes_text = ai_results.get("investigation_notes", "")

    ai_available = exec_summary is not None

    # Escape all string fields for HTML embedding
    def esc(s):
        return html.escape(str(s)) if s else ""

    timestamp = datetime.now().strftime("%B %d, %Y at %I:%M %p")

    # Embed logo as base64 data URI
    logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'images', 'ss-logo-new.webp')
    if os.path.exists(logo_path):
        with open(logo_path, 'rb') as f:
            logo_b64 = base64.b64encode(f.read()).decode('utf-8')
        logo_tag = f'<img src="data:image/webp;base64,{logo_b64}" alt="Schneiders" style="height:50px;">'
    else:
        logo_tag = '<span style="font-weight:bold;color:#CC0000;font-size:1.5rem;">Schneiders</span>'

    # Build category cards HTML
    cat_cards_html = ""
    for name, c in sorted(categories.items()):
        trend = get_seasonal_trend(0, name, datetime.now().month)
        trend_arrow = {"increasing": "&#9650;", "decreasing": "&#9660;", "stable": "&#9654;"}
        trend_color = {"increasing": "#059669", "decreasing": "#CC0000", "stable": "#2563EB"}
        next_months_str = ", ".join(
            f"{n['month']} {n['coeff']}x" for n in trend["next_3"]
        )
        cat_cards_html += f"""
        <div class="bg-white rounded-lg p-5 border border-[#D1D5DB]">
            <div class="flex justify-between items-start mb-3">
                <h3 class="text-[#333333] font-semibold text-base">{esc(name)}</h3>
                <span class="text-sm" style="color: {trend_color[trend['direction']]}"
                    title="Next 3 months: {next_months_str}">
                    {trend_arrow[trend['direction']]} {trend['direction'].title()}
                </span>
            </div>
            <div class="grid grid-cols-2 gap-2 text-sm">
                <div><span class="text-[#555555]">Total SKUs:</span> <span class="text-[#1a1a1a]">{c['total']}</span></div>
                <div><span class="text-[#555555]">OOS:</span> <span class="text-[#1a1a1a]" style="color: {FLAG_COLORS['OOS'] if c['oos'] > 0 else '#1a1a1a'}">{c['oos']}</span></div>
                <div><span class="text-[#555555]">At Risk:</span> <span class="text-[#1a1a1a]" style="color: {'#CC0000' if c['at_risk'] > 0 else '#1a1a1a'}">{c['at_risk']}</span></div>
                <div><span class="text-[#555555]">Profit/Mo:</span> <span class="text-[#1a1a1a]">${c['profit_at_risk']:,.0f}</span></div>
            </div>
            <div class="mt-2 text-sm text-[#555555]">Season: {trend['current_coeff']}x now</div>
        </div>"""

    # Build investigation rows HTML
    inv_rows_html = ""
    if investigation:
        # Show AI/fallback investigation summary at top
        if inv_notes_text:
            inv_rows_html += f"""
            <div class="bg-white rounded-lg p-4 border border-[#D1D5DB] mb-4">
                <div class="text-[#1a1a1a] text-base leading-relaxed">{clean_ai_text(inv_notes_text)}</div>
            </div>"""
        # Individual item detail cards
        for p in investigation:
            inv_rows_html += f"""
            <div class="bg-white rounded-lg p-4 border border-[#D1D5DB] mb-3">
                <div class="flex justify-between items-start">
                    <div>
                        <span class="text-[#1a1a1a] font-semibold">{esc(p['sku'])}</span>
                        <span class="text-[#555555] ml-2">{esc(p['product_name'])}</span>
                    </div>
                    <span class="inline-flex items-center whitespace-nowrap text-sm px-2 py-1 rounded-full" style="background: #CC000015; color: #CC0000">
                        OOS ~{p.get('days_since_restock', 'N/A')} days
                    </span>
                </div>
                <div class="mt-2 text-sm text-[#555555]">
                    Category: {esc(p['category'])} | Supplier: {esc(p['supplier'])} |
                    Base velocity: {p['base_velocity']}/day | Last restock: {p['last_restock_date']}
                </div>
            </div>"""
    else:
        inv_rows_html = '<p class="text-[#555555] text-base">No items currently require investigation.</p>'

    # AI section content
    if ai_available:
        exec_html = f'<div class="text-[#1a1a1a] text-base leading-relaxed">{clean_ai_text(exec_summary)}</div>'
        cat_analysis_html = f'<div class="text-[#1a1a1a] text-base leading-relaxed">{clean_ai_text(cat_analysis)}</div>' if cat_analysis else '<p class="text-[#555555] text-base italic">No category analysis generated.</p>'
    else:
        exec_html = """<div class="bg-[#EAEAEA] rounded-lg p-6 text-center">
            <svg class="mx-auto mb-3 w-10 h-10 text-[#555555]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0112 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5"/>
            </svg>
            <p class="text-[#555555] font-medium">AI insights unavailable</p>
            <p class="text-[#555555] text-base mt-1">Run with ANTHROPIC_API_KEY set to enable AI-powered analysis. All quantitative data and scoring remains fully functional.</p>
        </div>"""
        cat_analysis_html = """<div class="bg-[#EAEAEA] rounded-lg p-4 text-center">
            <p class="text-[#555555] text-base">AI category analysis unavailable. Run with ANTHROPIC_API_KEY set to enable.</p>
        </div>"""

    # Build the SKU recs JSON for embedding (pre-convert markdown to HTML)
    sku_recs_cleaned = {sku: clean_ai_text(text) for sku, text in sku_recs.items()}
    sku_recs_json = json.dumps(sku_recs_cleaned).replace('</','<\\/')

    # Seasonality JSON for JS recalculation
    seasonality_json = json.dumps(SEASONALITY).replace('</','<\\/')

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Out-of-Stock Intelligence Report | Schneider Saddlery</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body {{ background: #FFFFFF; color: #1a1a1a; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
        .settings-panel {{ transform: translateX(100%); transition: transform 0.3s ease; }}
        .settings-panel.open {{ transform: translateX(0); }}
        .settings-overlay {{ opacity: 0; pointer-events: none; transition: opacity 0.3s ease; }}
        .settings-overlay.open {{ opacity: 1; pointer-events: auto; }}
        .sort-arrow {{ opacity: 0.3; cursor: pointer; }}
        .sort-arrow.active {{ opacity: 1; }}
        .expand-row {{ display: none; }}
        .expand-row.visible {{ display: table-row; }}
        .table-row.expandable-row:hover {{ background: #E8E8E8 !important; }}
        .table-row:hover {{ background: #F5F5F5; }}
        input[type="number"] {{ background: #FFFFFF; border: 1px solid #D1D5DB; color: #333333; padding: 4px 8px; border-radius: 4px; width: 100%; }}
        input[type="number"]:focus {{ outline: none; border-color: #2D2D2D; }}
        input[type="text"] {{ background: #EAEAEA; border: 1px solid #D1D5DB; color: #333333; padding: 8px 12px; border-radius: 6px; }}
        input[type="text"]:focus {{ outline: none; border-color: #2D2D2D; }}
        input[type="text"]::placeholder {{ color: #333333; }}
        select {{ background: #FFFFFF; border: 1px solid #D1D5DB; color: #333333; padding: 6px 10px; border-radius: 6px; }}
        select:focus {{ outline: none; border-color: #2D2D2D; }}
        .methodology-content {{ max-height: 0; overflow: hidden; transition: max-height 0.3s ease; }}
        .methodology-content.open {{ max-height: 2000px; }}
        .section-heading {{ color: #1a1a1a; font-size: 1.25rem; font-weight: 700; padding-bottom: 0.75rem; border-bottom: 2px solid #D1D5DB; margin-bottom: 1rem; }}
        ::-webkit-scrollbar {{ width: 8px; height: 8px; }}
        ::-webkit-scrollbar-track {{ background: #F5F5F5; }}
        ::-webkit-scrollbar-thumb {{ background: #D1D5DB; border-radius: 4px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: #9CA3AF; }}
        .cursor-help {{ cursor: help; }}
        .table-scroll-container {{ max-height: 70vh; overflow-x: auto; overflow-y: auto; }}
        .table-scroll-container thead {{ position: sticky; top: 0; z-index: 10; }}
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
                <h2 class="text-xl font-bold text-[#1a1a1a]">Settings</h2>
                <button onclick="toggleSettings()" class="text-[#555555] hover:text-[#333333]">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
                </button>
            </div>

            <div class="space-y-6">
                <div>
                    <h3 class="text-base font-semibold text-[#555555] uppercase tracking-wider mb-3">OOS Flag Thresholds</h3>
                    <div class="space-y-2">
                        <div class="flex items-center justify-between">
                            <label class="text-base text-[#333333]">Red (Restock Now) days</label>
                            <input type="number" id="cfg_red_days" value="{cfg['red_days']}" min="0" max="90" class="w-20 text-right" onchange="recalculate()">
                        </div>
                        <div class="flex items-center justify-between">
                            <label class="text-base text-[#333333]">Yellow (Restock Soon) days</label>
                            <input type="number" id="cfg_yellow_days" value="{cfg['yellow_days']}" min="0" max="90" class="w-20 text-right" onchange="recalculate()">
                        </div>
                        <div class="flex items-center justify-between">
                            <label class="text-base text-[#333333]">Blue (Watch) days</label>
                            <input type="number" id="cfg_blue_days" value="{cfg['blue_days']}" min="0" max="180" class="w-20 text-right" onchange="recalculate()">
                        </div>
                        <div class="flex items-center justify-between">
                            <label class="text-base text-[#333333]">Buffer days</label>
                            <input type="number" id="cfg_buffer_days" value="{cfg['buffer_days']}" min="0" max="60" class="w-20 text-right" onchange="recalculate()">
                        </div>
                    </div>
                </div>

                <div>
                    <h3 class="text-base font-semibold text-[#555555] uppercase tracking-wider mb-3">Risk Tier Thresholds</h3>
                    <div class="space-y-2">
                        <div class="flex items-center justify-between">
                            <label class="text-base text-[#333333]">Critical (&gt;$/mo)</label>
                            <input type="number" id="cfg_critical" value="{cfg['critical_threshold']}" min="0" step="100" class="w-24 text-right" onchange="recalculate()">
                        </div>
                        <div class="flex items-center justify-between">
                            <label class="text-base text-[#333333]">High (&gt;$/mo)</label>
                            <input type="number" id="cfg_high" value="{cfg['high_threshold']}" min="0" step="100" class="w-24 text-right" onchange="recalculate()">
                        </div>
                        <div class="flex items-center justify-between">
                            <label class="text-base text-[#333333]">Medium (&gt;$/mo)</label>
                            <input type="number" id="cfg_medium" value="{cfg['medium_threshold']}" min="0" step="50" class="w-24 text-right" onchange="recalculate()">
                        </div>
                    </div>
                </div>

                <div>
                    <h3 class="text-base font-semibold text-[#555555] uppercase tracking-wider mb-3">Restock Settings</h3>
                    <div class="space-y-2">
                        <div class="flex items-center justify-between">
                            <label class="text-base text-[#333333]">Target stock days</label>
                            <input type="number" id="cfg_target_days" value="{cfg['target_stock_days']}" min="0" max="365" class="w-20 text-right" onchange="recalculate()">
                        </div>
                        <div class="flex items-center justify-between">
                            <label class="text-base text-[#333333]">Default lead time</label>
                            <input type="number" id="cfg_lead_time" value="{cfg['default_lead_time']}" min="0" max="180" class="w-20 text-right" onchange="recalculate()">
                        </div>
                        <div class="flex items-center justify-between">
                            <label class="text-base text-[#333333]">Default reorder point</label>
                            <input type="number" id="cfg_reorder_pt" value="{cfg['default_reorder_point']}" min="0" class="w-20 text-right" onchange="recalculate()">
                        </div>
                    </div>
                </div>

                <button onclick="resetDefaults()" class="w-full py-2 px-4 bg-[#F5F5F5] text-[#555555] rounded-lg hover:bg-[#EAEAEA] hover:text-[#333333] transition text-base">
                    Reset to Defaults
                </button>
            </div>
        </div>
    </div>

    <!-- Top Bar (White) -->
    <header class="bg-white border-b border-[#D1D5DB] sticky top-0 z-30">
        <div class="max-w-[1600px] mx-auto px-4 py-3 flex items-center justify-between">
            <div class="flex-shrink-0">
                {logo_tag}
            </div>
            <div class="flex-1 text-center">
                <h1 class="text-2xl font-bold text-[#1a1a1a]">Out-of-Stock Intelligence Report</h1>
            </div>
            <div class="flex items-center gap-3 no-print flex-shrink-0">
                <p class="text-sm text-[#555555]">Generated {timestamp}</p>
                <button onclick="window.print()" class="px-3 py-1.5 text-sm bg-white text-[#333333] rounded-lg hover:bg-[#F5F5F5] border border-[#D1D5DB] transition">
                    Print
                </button>
                <button onclick="alert('To upload new data, re-run the tool with: python oos_tool.py --input your_file.csv')" class="px-3 py-1.5 text-sm bg-white text-[#333333] rounded-lg hover:bg-[#F5F5F5] border border-[#D1D5DB] transition">
                    Upload New Data
                </button>
                <button onclick="toggleSettings()" class="p-1.5 text-[#555555] hover:text-[#1a1a1a] transition" title="Settings">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
                </button>
            </div>
        </div>
    </header>

    <!-- Blue Stats Bar -->
    <div class="bg-[#002848]">
        <div id="statsCards" class="max-w-[1600px] mx-auto px-4 py-4 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
            <div class="stat-card rounded-lg p-4" style="background: rgba(255,255,255,0.1);">
                <p class="text-sm uppercase tracking-wider" style="color: rgba(255,255,255,0.7);">Total SKUs</p>
                <p class="text-3xl font-bold text-white mt-1" id="stat_total">{summary['total_skus']}</p>
            </div>
            <div class="stat-card rounded-lg p-4" style="background: rgba(255,255,255,0.1);">
                <p class="text-sm uppercase tracking-wider" style="color: rgba(255,255,255,0.7);">Currently OOS</p>
                <p class="text-3xl font-bold mt-1" style="color: #FBEAEA" id="stat_oos">{summary['oos_count']}</p>
            </div>
            <div class="stat-card rounded-lg p-4" style="background: rgba(255,255,255,0.1);">
                <p class="text-sm uppercase tracking-wider" style="color: rgba(255,255,255,0.7);">At Risk</p>
                <p class="text-3xl font-bold mt-1" style="color: #FBEAEA" id="stat_atrisk">{summary['at_risk_count']}</p>
            </div>
            <div class="stat-card rounded-lg p-4" style="background: rgba(255,255,255,0.1);">
                <p class="text-sm uppercase tracking-wider" style="color: rgba(255,255,255,0.7);">Est Daily Revenue Lost</p>
                <p class="text-3xl font-bold mt-1" style="color: #FBEAEA" id="stat_daily_rev">${summary['daily_revenue_lost']:,.0f}</p>
            </div>
            <div class="stat-card rounded-lg p-4" style="background: rgba(255,255,255,0.1);">
                <p class="text-sm uppercase tracking-wider" style="color: rgba(255,255,255,0.7);">Monthly Profit at Risk</p>
                <p class="text-3xl font-bold mt-1" style="color: #FBEAEA" id="stat_monthly">${summary['monthly_profit_at_risk']:,.0f}</p>
            </div>
            <div class="stat-card rounded-lg p-4" style="background: rgba(255,255,255,0.1);">
                <p class="text-sm uppercase tracking-wider" style="color: rgba(255,255,255,0.7);">Missed Profit to Date</p>
                <p class="text-3xl font-bold mt-1" style="color: #FBEAEA" id="stat_missed">${summary['missed_profit_total']:,.0f}</p>
            </div>
        </div>
    </div>

    <main class="max-w-[1600px] mx-auto px-4 py-6 space-y-6">

        <!-- Executive Summary -->
        <div class="bg-[#EEEEEE] rounded-lg p-6 border border-[#D1D5DB]">
            <h2 class="section-heading">Executive Summary</h2>
            <div id="execSummary">{exec_html}</div>
        </div>

        <!-- Legend -->
        <div class="bg-[#EEEEEE] rounded-lg p-4 border border-[#D1D5DB]">
            <div class="flex flex-wrap gap-x-6 gap-y-2 text-sm text-[#1a1a1a]">
                <div class="flex flex-wrap items-center gap-x-4 gap-y-1">
                    <span class="font-semibold">Flags:</span>
                    <span class="inline-flex items-center gap-1"><span class="inline-block w-3 h-3 rounded-full" style="background:#7C3AED"></span> OOS = Already out of stock</span>
                    <span class="inline-flex items-center gap-1"><span class="inline-block w-3 h-3 rounded-full" style="background:#CC0000"></span> Restock = Will stock out before restock arrives</span>
                    <span class="inline-flex items-center gap-1"><span class="inline-block w-3 h-3 rounded-full" style="background:#D97706"></span> Soon = Tight window, order now</span>
                    <span class="inline-flex items-center gap-1"><span class="inline-block w-3 h-3 rounded-full" style="background:#2563EB"></span> Watch = Order within 30 days</span>
                    <span class="inline-flex items-center gap-1"><span class="inline-block w-3 h-3 rounded-full" style="background:#059669"></span> Healthy = Sufficient stock</span>
                </div>
            </div>
            <div class="flex flex-wrap gap-x-6 gap-y-2 text-sm text-[#1a1a1a] mt-2">
                <div class="flex flex-wrap items-center gap-x-4 gap-y-1">
                    <span class="font-semibold">Tiers:</span>
                    <span class="inline-flex items-center gap-1"><span class="inline-block w-3 h-3 rounded-full" style="background:#CC0000"></span> Critical = Over $5,000/mo profit at risk</span>
                    <span class="inline-flex items-center gap-1"><span class="inline-block w-3 h-3 rounded-full" style="background:#D97706"></span> High = $1,000-$5,000/mo</span>
                    <span class="inline-flex items-center gap-1"><span class="inline-block w-3 h-3 rounded-full" style="background:#2563EB"></span> Medium = $250-$1,000/mo</span>
                    <span class="inline-flex items-center gap-1"><span class="inline-block w-3 h-3 rounded-full" style="background:#6B7280"></span> Low = Under $250/mo</span>
                </div>
            </div>
        </div>

        <!-- Filters and Search -->
        <div class="bg-[#EEEEEE] rounded-lg p-4 border border-[#D1D5DB] no-print">
            <div class="flex flex-wrap gap-3 items-center">
                <input type="text" id="searchInput" placeholder="Search SKU, product, supplier..." class="flex-1 min-w-[200px]" onkeyup="filterTable()">
                <select id="filterFlag" onchange="filterTable()" class="text-base">
                    <option value="">All Flags</option>
                    <option value="OOS">OOS (Purple)</option>
                    <option value="Restock Now">Restock Now (Red)</option>
                    <option value="Restock Soon">Restock Soon (Yellow)</option>
                    <option value="Watch">Watch (Blue)</option>
                    <option value="Healthy">Healthy (Green)</option>
                    <option value="No Velocity">No Velocity (Gray)</option>
                </select>
                <select id="filterTier" onchange="filterTable()" class="text-base">
                    <option value="">All Tiers</option>
                    <option value="Critical">Critical</option>
                    <option value="High">High</option>
                    <option value="Medium">Medium</option>
                    <option value="Low">Low</option>
                </select>
                <select id="filterCategory" onchange="filterTable()" class="text-base">
                    <option value="">All Categories</option>
                </select>
                <select id="filterSupplier" onchange="filterTable()" class="text-base">
                    <option value="">All Suppliers</option>
                </select>
            </div>
        </div>

        <!-- Main Data Table -->
        <div class="table-scroll-container bg-white rounded-lg border border-[#D1D5DB] overflow-x-auto">
            <table class="w-full table-auto text-sm" id="mainTable">
                <thead>
                    <tr class="bg-[#002848] text-white text-sm font-semibold uppercase tracking-wider">
                        <th class="p-3 text-left cursor-pointer cursor-help hover:text-gray-200 min-w-[80px]" onclick="sortTable('flag')" title="Restock urgency based on projected days until OOS vs lead time" style="position:sticky;left:0;z-index:20;background:#002848;">Flag <span class="sort-arrow" data-col="flag">&#9650;&#9660;</span></th>
                        <th class="p-3 text-left cursor-pointer cursor-help hover:text-gray-200 min-w-[70px]" onclick="sortTable('risk_tier')" title="Financial impact tier based on monthly profit at risk" style="position:sticky;left:80px;z-index:20;background:#002848;">Tier <span class="sort-arrow" data-col="risk_tier">&#9650;&#9660;</span></th>
                        <th class="p-3 text-left cursor-pointer cursor-help hover:text-gray-200 min-w-[90px]" onclick="sortTable('sku')" title="Product SKU identifier">SKU <span class="sort-arrow" data-col="sku">&#9650;&#9660;</span></th>
                        <th class="p-3 text-left cursor-pointer cursor-help hover:text-gray-200 min-w-[200px]" onclick="sortTable('product_name')" title="Product name">Product <span class="sort-arrow" data-col="product_name">&#9650;&#9660;</span></th>
                        <th class="p-3 text-left cursor-pointer cursor-help hover:text-gray-200 min-w-[130px]" onclick="sortTable('category')" title="Product category">Category <span class="sort-arrow" data-col="category">&#9650;&#9660;</span></th>
                        <th class="p-3 text-left cursor-pointer cursor-help hover:text-gray-200 min-w-[130px]" onclick="sortTable('supplier')" title="Supplier name and source">Supplier <span class="sort-arrow" data-col="supplier">&#9650;&#9660;</span></th>
                        <th class="p-3 text-right cursor-pointer cursor-help hover:text-gray-200 min-w-[60px]" onclick="sortTable('current_stock')" title="Current units in stock">Stock <span class="sort-arrow" data-col="current_stock">&#9650;&#9660;</span></th>
                        <th class="p-3 text-right cursor-pointer cursor-help hover:text-gray-200 min-w-[70px]" onclick="sortTable('reorder_point')" title="Stock level that triggers a reorder for this product">Reorder Pt <span class="sort-arrow" data-col="reorder_point">&#9650;&#9660;</span></th>
                        <th class="p-3 text-right cursor-pointer cursor-help hover:text-gray-200 min-w-[65px]" onclick="sortTable('base_velocity')" title="Annual average daily sales velocity before seasonality">Base Vel <span class="sort-arrow" data-col="base_velocity">&#9650;&#9660;</span></th>
                        <th class="p-3 text-right cursor-pointer cursor-help hover:text-gray-200 min-w-[60px]" onclick="sortTable('avg_daily_velocity')" title="Current daily velocity adjusted for seasonal demand">Cur Vel <span class="sort-arrow" data-col="avg_daily_velocity">&#9650;&#9660;</span></th>
                        <th class="p-3 text-right cursor-pointer cursor-help hover:text-gray-200 min-w-[75px]" onclick="sortTable('projected_days')" title="Projected days until out of stock using seasonal velocity curve">Proj Days <span class="sort-arrow" data-col="projected_days">&#9650;&#9660;</span></th>
                        <th class="p-3 text-right cursor-pointer cursor-help hover:text-gray-200 min-w-[90px]" onclick="sortTable('est_oos_date_raw')" title="Estimated date stock will reach zero based on seasonal projection">Est. OOS <span class="sort-arrow" data-col="est_oos_date_raw">&#9650;&#9660;</span></th>
                        <th class="p-3 text-center cursor-help min-w-[70px]" title="Seasonal demand direction for the next 3 months">Trend</th>
                        <th class="p-3 text-right cursor-pointer cursor-help hover:text-gray-200 min-w-[65px]" onclick="sortTable('urgency_score')" title="Proj Days minus total lead time and buffer. Negative means cannot restock in time">Urgency <span class="sort-arrow" data-col="urgency_score">&#9650;&#9660;</span></th>
                        <th class="p-3 text-right cursor-pointer cursor-help hover:text-gray-200 min-w-[70px]" onclick="sortTable('total_lead_time')" title="Total days from order to stock available (supplier lead + shipping + receiving buffer)">Lead Time <span class="sort-arrow" data-col="total_lead_time">&#9650;&#9660;</span></th>
                        <th class="p-3 text-right cursor-pointer cursor-help hover:text-gray-200 min-w-[80px]" onclick="sortTable('monthly_profit_at_risk')" title="Estimated monthly gross profit based on current velocity">Profit/Mo <span class="sort-arrow" data-col="monthly_profit_at_risk">&#9650;&#9660;</span></th>
                        <th class="p-3 text-right cursor-pointer cursor-help hover:text-gray-200 min-w-[70px]" onclick="sortTable('missed_profit')" title="Estimated profit lost while product has been out of stock">Missed $ <span class="sort-arrow" data-col="missed_profit">&#9650;&#9660;</span></th>
                        <th class="p-3 text-right cursor-pointer cursor-help hover:text-gray-200 min-w-[65px]" onclick="sortTable('recommended_qty')" title="Recommended order quantity using seasonal demand projection">Rec Qty <span class="sort-arrow" data-col="recommended_qty">&#9650;&#9660;</span></th>
                        <th class="p-3 text-center min-w-[30px]" title="Rows with AI recommendations can be expanded"></th>
                    </tr>
                </thead>
                <tbody id="tableBody">
                </tbody>
            </table>
        </div>

        <!-- Category Health -->
        <div class="bg-white rounded-lg p-6 border border-[#D1D5DB]">
            <h2 class="section-heading">Category Health</h2>
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4 mb-6">
                {cat_cards_html}
            </div>
            <div>
                <h3 class="text-lg font-semibold text-[#1a1a1a] mb-3">Category Analysis</h3>
                {cat_analysis_html}
            </div>
        </div>

        <!-- Needs Investigation -->
        <div class="bg-[#FEF2F2] rounded-lg p-6 border-l-4 border-[#CC0000]">
            <h2 class="section-heading" style="border-bottom-color: #FECACA">
                Needs Investigation
                <span class="text-base font-normal text-[#555555] ml-2">OOS 60+ days with stale restock dates</span>
            </h2>
            {inv_rows_html}
        </div>

        <!-- Methodology Notes -->
        <div class="bg-white rounded-lg border border-[#D1D5DB]">
            <button onclick="toggleMethodology()" class="w-full p-4 flex justify-between items-center text-left hover:bg-[#F5F5F5] transition rounded-lg">
                <h2 class="text-xl font-bold text-[#1a1a1a]">Methodology Notes</h2>
                <svg id="methodArrow" class="w-5 h-5 text-[#555555] transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
            </button>
            <div id="methodologyContent" class="methodology-content">
                <div class="px-6 pb-6 text-base text-[#555555] space-y-4">
                    <div>
                        <h3 class="text-[#1a1a1a] font-semibold mb-1">Seasonal Projection</h3>
                        <p>Days until out-of-stock are calculated by walking forward day-by-day through the calendar, consuming stock at a seasonally-adjusted daily rate. Each product category has monthly coefficients (e.g., Blankets peak at 1.70x in December, trough at 0.20x in June/July). This gives a more accurate picture than flat velocity projection, especially during seasonal transitions.</p>
                    </div>
                    <div>
                        <h3 class="text-[#1a1a1a] font-semibold mb-1">Two-Layer Scoring</h3>
                        <p><strong>Urgency Flags</strong> answer "When do I need to act?" They compare projected days until OOS against total lead time plus a buffer. Purple = already OOS, Red = will be OOS before restock can arrive, Yellow = tight window, Blue = comfortable margin, Green = healthy stock.</p>
                        <p class="mt-1"><strong>Risk Tiers</strong> answer "How bad is it financially if I do not act?" They use monthly profit at risk (current velocity times margin times 30 days). Critical = over $5K/month, High = $1K-$5K, Medium = $250-$1K, Low = under $250.</p>
                    </div>
                    <div>
                        <h3 class="text-[#1a1a1a] font-semibold mb-1">Recommended Order Quantity</h3>
                        <p>Projected consumption is summed over the full coverage window (lead time + buffer + target stock days) using seasonal coefficients. Current stock is subtracted. Default target is 60 days on hand after restock arrives. A production system would configure per product/category; overseas products would target 90-120 days.</p>
                    </div>
                    <div>
                        <h3 class="text-[#1a1a1a] font-semibold mb-1">Missed Profit</h3>
                        <p>For OOS items, estimated profit lost is calculated as: (days since last restock minus 30 days assumed sell-through) times daily profit. This represents the cost of inaction and helps prioritize restock urgency.</p>
                    </div>
                    <div>
                        <h3 class="text-[#1a1a1a] font-semibold mb-1">Margin Note</h3>
                        <p>Profit calculations use gross margin (unit price minus unit cost). A production system would factor in marketplace fees (2.4-2.9% + $0.30), payment processing, warehouse labor/storage, shipping, and returns, which typically reduce gross margin by 15-25 percentage points. The settings panel would support a margin adjustment factor.</p>
                    </div>
                    <div>
                        <h3 class="text-[#1a1a1a] font-semibold mb-1">Flat vs Projected Comparison</h3>
                        <p>When flat days and projected days diverge by more than 15%, a seasonal indicator badge appears. A red up-arrow with "Demand increasing" means projected OOS is sooner than flat (more urgent). A green down-arrow with "Demand decreasing" means projected OOS is later (less urgent).</p>
                    </div>
                </div>
            </div>
        </div>
    </main>

    <footer class="max-w-[1600px] mx-auto px-4 py-6 text-center text-sm text-[#555555]">
        Generated by OOS Intelligence Tool | Schneider Saddlery Technical Assessment
    </footer>

    <script>
    // Embedded data
    const ALL_PRODUCTS = {products_json};
    const SKU_RECS = {sku_recs_json};
    const SEASONALITY = {seasonality_json};
    const DAYS_PER_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    const MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    const FLAG_COLORS = {json.dumps(FLAG_COLORS).replace('</','<\\/')};
    const FLAG_WEIGHTS = {json.dumps(FLAG_WEIGHTS).replace('</','<\\/')};

    const TIER_ORDER = {{"Critical": 4, "High": 3, "Medium": 2, "Low": 1}};
    const TIER_WEIGHTS = {{"Critical": 4000000, "High": 3000000, "Medium": 2000000, "Low": 1000000}};
    const FLAG_ORDER = {{"OOS": 6, "Restock Now": 5, "Restock Soon": 4, "Watch": 3, "No Velocity": 1, "Healthy": 2}};
    const AI_AVAILABLE = {'true' if ai_available else 'false'};

    const DEFAULTS = {json.dumps(DEFAULT_CONFIG).replace('</','<\\/')};

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
                else if (urgency < cfg.blue_days) flag = "Watch";
                else flag = "Healthy";
            }}

            // Tier
            let tier;
            if (monthProfit > cfg.critical_threshold) tier = "Critical";
            else if (monthProfit > cfg.high_threshold) tier = "High";
            else if (monthProfit > cfg.medium_threshold) tier = "Medium";
            else tier = "Low";

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

            // Estimated OOS date
            item.est_oos_date = null;
            item.est_oos_date_raw = null;
            if (item.current_stock === 0) {{
                // Already OOS: approximate as last restock + 30 days
                // Cap to today so OOS products never show a future estimated OOS date
                if (item.last_restock_date) {{
                    const parts = item.last_restock_date.split('-');
                    const restockDate = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
                    restockDate.setDate(restockDate.getDate() + 30);
                    const capDate = restockDate > now ? now : restockDate;
                    const rawStr = capDate.getFullYear() + '-' + String(capDate.getMonth() + 1).padStart(2, '0') + '-' + String(capDate.getDate()).padStart(2, '0');
                    item.est_oos_date = '~' + rawStr;
                    item.est_oos_date_raw = rawStr;
                }}
            }} else if (flag !== 'No Velocity' && projDays < 365) {{
                const oosDate = new Date(now);
                oosDate.setDate(oosDate.getDate() + projDays);
                const rawStr = oosDate.getFullYear() + '-' + String(oosDate.getMonth() + 1).padStart(2, '0') + '-' + String(oosDate.getDate()).padStart(2, '0');
                item.est_oos_date = rawStr;
                item.est_oos_date_raw = rawStr;
            }}

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
            // Null values sort to end regardless of direction
            if (aVal == null && bVal == null) return 0;
            if (aVal == null) return 1;
            if (bVal == null) return -1;
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
            const tierColors = {{"Critical": "#CC0000", "High": "#D97706", "Medium": "#2563EB", "Low": "#6B7280"}};
            const tierColor = tierColors[p.risk_tier] || '#6B7280';
            const rowBg = idx % 2 === 0 ? '#FFFFFF' : '#F9FAFB';

            // Trend badge (arrow only, full text as tooltip)
            let trendHtml = '';
            if (p.trend) {{
                const dir = p.trend.direction;
                let trendArrow = '&#8722;';
                let trendColor = '#2563EB';
                let trendLabel = 'Stable';
                if (dir === 'increasing') {{ trendArrow = '&#9650;'; trendColor = '#059669'; trendLabel = 'Demand Increasing'; }}
                else if (dir === 'decreasing') {{ trendArrow = '&#9660;'; trendColor = '#CC0000'; trendLabel = 'Demand Decreasing'; }}
                const monthDetail = p.trend.next_3 ? p.trend.next_3.map(function(n) {{ return n.month + ': ' + n.coeff + 'x'; }}).join(', ') : '';
                const tooltip = trendLabel + (monthDetail ? ' (' + monthDetail + ')' : '');
                trendHtml = '<span style="color:' + trendColor + ';font-size:14px;" title="' + escHtml(tooltip) + '">' + trendArrow + '</span>';
            }}

            // Flat vs projected divergence
            let projDisplay = p.projected_days;
            if (p.projected_days < 365 && p.flat_days < 9999) {{
                const diff = Math.abs(p.projected_days - p.flat_days) / Math.max(p.flat_days, 1);
                if (diff > 0.15) {{
                    if (p.projected_days < p.flat_days) {{
                        projDisplay = p.projected_days + ' <span class="text-[11px]" style="color:#059669" title="Flat: ' + p.flat_days + ' days">&#9650; Demand increasing</span>';
                    }} else {{
                        projDisplay = p.projected_days + ' <span class="text-[11px]" style="color:#CC0000" title="Flat: ' + p.flat_days + ' days">&#9660; Demand decreasing</span>';
                    }}
                }}
            }}

            // Below reorder point indicator (hide on OOS rows where stock is 0)
            let reorderBadge = '';
            if (p.below_reorder && p.current_stock > 0) {{
                reorderBadge = ' <span class="inline-flex items-center whitespace-nowrap text-[11px] px-1.5 py-0.5 rounded-full" style="background: #D9770620; color: #D97706">Below Reorder Pt</span>';
            }}

            // Tier badge: hide for Healthy and No Velocity products
            let tierBadgeHtml = '';
            if (p.flag !== 'Healthy' && p.flag !== 'No Velocity') {{
                tierBadgeHtml = '<span class="inline-flex items-center whitespace-nowrap px-2 py-1 rounded-full text-sm font-medium" style="background:' + tierColor + '15; color:' + tierColor + '">' + escHtml(p.risk_tier) + '</span>';
            }} else {{
                tierBadgeHtml = '<span class="text-[#1a1a1a]">-</span>';
            }}

            // Has AI rec?
            const rec = SKU_RECS[p.sku];
            const hasRec = rec && rec.length > 0;

            const bgColor = idx % 2 === 0 ? '#FFFFFF' : '#F9FAFB';
            if (hasRec) {{
                html += '<tr class="table-row expandable-row border-b border-[#D1D5DB] cursor-pointer" style="background:' + rowBg + '" title="Click to view AI recommendation" onclick="toggleExpand(\\'' + p.sku + '\\')">';
            }} else {{
                html += '<tr class="table-row border-b border-[#D1D5DB]" style="background:' + rowBg + '">';
            }}
            // Abbreviate "Restock Now" to "Restock" for badge, full text on hover
            const flagLabel = p.flag === 'Restock Now' ? 'Restock' : p.flag;
            const flagTitle = p.flag === 'Restock Now' ? ' title="Restock Now"' : '';
            html += '<td class="p-3" style="position:sticky;left:0;z-index:5;background:' + bgColor + ';"><span class="inline-flex items-center whitespace-nowrap px-2 py-1 rounded-full text-sm font-medium text-white" style="background:' + flagColor + '"' + flagTitle + '>' + escHtml(flagLabel) + '</span></td>';
            html += '<td class="p-3" style="position:sticky;left:80px;z-index:5;background:' + bgColor + ';">' + tierBadgeHtml + '</td>';
            html += '<td class="p-3 text-[#1a1a1a] font-mono whitespace-nowrap">' + escHtml(p.sku) + reorderBadge + '</td>';
            html += '<td class="p-3 text-[#1a1a1a] min-w-[200px]" title="' + escHtml(p.product_name) + '">' + escHtml(p.product_name) + '</td>';
            html += '<td class="p-3 text-[#1a1a1a]">' + escHtml(p.category) + '</td>';
            html += '<td class="p-3 text-[#1a1a1a]">' + escHtml(p.supplier) + '</td>';
            html += '<td class="p-3 text-right text-[#1a1a1a]">' + p.current_stock.toLocaleString() + '</td>';
            html += '<td class="p-3 text-right text-[#1a1a1a]">' + p.reorder_point + '</td>';
            html += '<td class="p-3 text-right text-[#1a1a1a]">' + p.base_velocity + '</td>';
            html += '<td class="p-3 text-right text-[#1a1a1a]">' + p.avg_daily_velocity + '</td>';
            html += '<td class="p-3 text-right text-[#1a1a1a]">' + projDisplay + '</td>';

            // Est. OOS date cell
            let estOosHtml = '-';
            if (p.est_oos_date) {{
                let estColor = '#1a1a1a';
                let estTooltip = 'Projected date stock will reach zero';
                if (p.flag === 'OOS' || p.flag === 'Restock Now') {{
                    estColor = '#CC0000';
                    if (p.flag === 'OOS') estTooltip = 'Approximate date stock reached zero';
                }} else if (p.flag === 'Restock Soon') {{
                    estColor = '#D97706';
                }} else if (p.flag === 'Healthy' || p.flag === 'No Velocity') {{
                    estOosHtml = '-';
                }}
                if (p.flag !== 'Healthy' && p.flag !== 'No Velocity') {{
                    estOosHtml = '<span style="color:' + estColor + '" title="' + escHtml(estTooltip) + '">' + escHtml(p.est_oos_date) + '</span>';
                }}
            }}
            html += '<td class="p-3 text-right">' + estOosHtml + '</td>';

            html += '<td class="p-3 text-center">' + trendHtml + '</td>';
            html += '<td class="p-3 text-right text-[#1a1a1a]">' + p.urgency_score + '</td>';
            html += '<td class="p-3 text-right text-[#1a1a1a]">' + p.total_lead_time + 'd</td>';
            html += '<td class="p-3 text-right text-[#1a1a1a]">$' + p.monthly_profit_at_risk.toLocaleString(undefined, {{minimumFractionDigits: 0, maximumFractionDigits: 0}}) + '</td>';
            html += '<td class="p-3 text-right text-[#1a1a1a]">' + (p.missed_profit > 0 ? '$' + p.missed_profit.toLocaleString(undefined, {{minimumFractionDigits: 0, maximumFractionDigits: 0}}) : '-') + '</td>';
            html += '<td class="p-3 text-right text-[#1a1a1a]">' + (p.recommended_qty > 0 ? p.recommended_qty.toLocaleString() : '-') + '</td>';
            // Expand indicator cell
            if (hasRec) {{
                html += '<td class="p-3 text-center text-[#555555]"><span class="expand-chevron" id="chevron_' + p.sku + '" style="font-size:12px;transition:transform 0.2s;">&#9660;</span></td>';
            }} else {{
                html += '<td class="p-3"></td>';
            }}
            html += '</tr>';

            // Expandable row for AI recommendation
            if (hasRec) {{
                html += '<tr class="expand-row border-b border-[#D1D5DB]" id="expand_' + p.sku + '">';
                html += '<td colspan="19" class="p-0"><div class="px-6 py-4 bg-[#F5F5F5] border-l-4" style="border-color:' + flagColor + '">';
                html += '<p class="text-sm text-[#555555] uppercase tracking-wider mb-1">AI Recommendation</p>';
                html += '<p class="text-base text-[#1a1a1a]">' + rec + '</p>';
                html += '</div></td></tr>';
            }}
        }});

        tbody.innerHTML = html;
    }}

    function toggleExpand(sku) {{
        const row = document.getElementById('expand_' + sku);
        const chevron = document.getElementById('chevron_' + sku);
        if (row) {{
            row.classList.toggle('visible');
            if (chevron) {{
                chevron.style.transform = row.classList.contains('visible') ? 'rotate(180deg)' : '';
            }}
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
    if args.no_ai:
        print("\nAI insights: Using fallback templates (--no-ai flag)")
        ai_results = generate_fallback_insights(
            data["products"], data["categories"], s, data["needs_investigation"]
        )
    else:
        print("\nGenerating AI insights...")
        ai_results = generate_ai_insights(
            data["products"], data["categories"], s, data["needs_investigation"]
        )

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
          f"Yellow={s['flags']['Restock Soon']} Blue={s['flags']['Watch']} "
          f"Green={s['flags']['Healthy']}")
    if s['flags'].get('No Velocity', 0) > 0:
        print(f"         Gray (No Velocity)={s['flags']['No Velocity']}")
    print(f"  Tiers: Critical={s['tiers']['Critical']} High={s['tiers']['High']} "
          f"Medium={s['tiers']['Medium']} Low={s['tiers']['Low']}")
    ai_status = "Enabled (AI)" if os.environ.get("ANTHROPIC_API_KEY") and not args.no_ai else "Fallback templates"
    print(f"  AI Insights:          {ai_status}")
    print(f"\n  Open {args.output} in a browser to view the report.")
    print("=" * 60)


if __name__ == "__main__":
    main()
