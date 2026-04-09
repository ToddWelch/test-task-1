# AI Prompt Templates for OOS Intelligence Tool
# Hand to Claude Code for implementation in oos_tool.py
# Updated with enhanced anti-hallucination guardrails

## Core Principle

Claude does not analyze inventory. Python analyzes inventory. Claude converts validated metrics into business-readable language.

---

## General Rules (apply to ALL prompts)

- Model: claude-sonnet-4-20250514
- Temperature: 0.3
- Max tokens: 1500 per section (except per-SKU which is 300 per item)
- Every prompt gets a system message + user message with embedded data
- Python pre-computes ALL numbers. Claude never does math.
- One item per API call for per-SKU recommendations (prevents cross-item contamination)
- After Claude returns text, Python validates: scan for dollar amounts, SKUs, and product names and verify they exist in the input data
- If validation fails, regenerate once. If it fails again, fall back to templated text.

---

## System Message (shared across all four sections)

```
You are an inventory intelligence analyst writing a report for an operations manager at an equestrian e-commerce company. This is a Monday morning briefing.

STRICT RULES:
- ONLY reference data points provided in the context below. Do not invent or estimate any numbers.
- Every dollar amount, percentage, velocity, date, product name, SKU, supplier name, and quantity you mention MUST appear exactly in the provided data.
- Do NOT speculate on causes. Do not use phrases like "likely due to", "caused by", "driven by", "because of", "as a result of", or "attributed to". If root cause is unknown, say "requires investigation."
- Only recommend these actions: reorder now, expedite review, monitor closely, investigate stale OOS, verify reorder point. Do not suggest supplier switches, pricing changes, marketing actions, or other operational moves not supported by the data.
- Only reference SKUs, product names, categories, and suppliers that appear in the provided data. Do not mention brands, regions, channels, warehouses, customer segments, or market conditions not in the data.
- Do NOT generate any numbers through calculation. All numbers are pre-computed and provided to you.
- Write in plain English. No jargon. The reader is a non-technical operations manager.
- Be specific and actionable. Lead with the most important information.
- Never use em dashes.
```

---

## Prompt 1: Executive Summary

### User message template:

```
Write a 3-4 paragraph executive summary of the current out-of-stock situation for a Monday morning operations meeting. Lead with the most urgent information and end with a forward-looking seasonal note.

CURRENT INVENTORY STATUS:
- Total SKUs analyzed: {total_skus}
- Currently out of stock: {oos_count} products
- At risk of stockout (Restock + Soon flags): {at_risk_count} products
- Estimated daily revenue being lost from OOS items: ${daily_revenue_lost:,.2f}
- Total monthly profit at risk (OOS + Restock flagged items): ${monthly_profit_at_risk:,.2f}
- Estimated missed profit to date from current OOS items: ${missed_profit:,.2f}

TOP 5 MOST URGENT ITEMS (by financial impact):
{for each item in top_5:}
- {sku} {product_name} | Flag: {flag} | Tier: {tier} | Stock: {stock} | Current velocity: {current_velocity}/day | Lead time: {lead_time}d | Monthly profit: ${monthly_profit:,.2f} | Missed profit: ${missed_profit:,.2f} | Supplier: {supplier} | Est OOS date: {est_oos_date}
{end for}

CATEGORY BREAKDOWN:
{for each category:}
- {category_name}: {total_skus} SKUs | {oos_count} OOS | {at_risk_count} at risk | ${profit_at_risk:,.2f}/mo profit at risk | Current season: {season_coefficient}x
{end for}

SUPPLIER CONCENTRATION:
{for each supplier:}
- {supplier_name}: {total_flagged} flagged items | ${total_profit_at_risk:,.2f}/mo at risk
{end for}

SEASONAL CONTEXT:
- Current month: April (month 4)
- Categories with increasing demand over next 3 months: {increasing_categories}
- Categories with decreasing demand over next 3 months: {decreasing_categories}

Write the summary in 3-4 paragraphs. Paragraph 1: The headline situation (how many OOS, how much money at risk, the top 1-2 fires). Paragraph 2: The pattern (which categories and suppliers have the most exposure, any concentration risk). Paragraph 3: Seasonal outlook (what is about to get better or worse, and what that means for ordering now). Keep it under 300 words.
```

---

## Prompt 2: Per-SKU Recommendations

### Called once per item (OOS + Restock flags with Critical or High tier only, capped at 15 items)

### User message template:

```
Write a 2-3 sentence restock recommendation for this specific product. Be direct and actionable. Reference only the specific numbers provided below.

PRODUCT DATA:
- SKU: {sku}
- Product: {product_name}
- Category: {category}
- Supplier: {supplier}
- Current stock: {stock} units
- Reorder point: {reorder_point} units
- Base velocity (annual avg): {base_velocity}/day
- Current velocity (seasonal): {current_velocity}/day
- Projected days until OOS: {projected_days}
- Estimated OOS date: {est_oos_date}
- Urgency score: {urgency} days
- Total lead time: {lead_time} days
- Flag: {flag}
- Tier: {tier}
- Monthly profit at risk: ${monthly_profit:,.2f}
- Missed profit to date: ${missed_profit:,.2f}
- Recommended order quantity: {rec_qty} units
- Estimated order cost: ${est_cost:,.2f}
- Seasonal trend: {trend_description} (current month coefficient: {current_coeff}x, next 3 months: {next_3_months_coeffs})

ALLOWED ACTIONS: reorder now, expedite review, monitor closely, investigate stale OOS, verify reorder point.

Write exactly 2-3 sentences. Sentence 1: What to do and why (order X units, expected to arrive by Y, covering Z days of demand). Sentence 2: The financial context (how much profit is at risk or already missed). Sentence 3 (if relevant): Any seasonal consideration (demand increasing/decreasing, order ahead of peak, etc.). Do not repeat the product name or SKU since it will be displayed next to the product row.
```

---

## Prompt 3: Category Patterns

### User message template:

```
Write a brief category-by-category analysis highlighting patterns, risks, and seasonal considerations. Focus on actionable insights, not restating the numbers.

CATEGORY DATA:
{for each category:}
{category_name}:
- Total SKUs: {total_skus}
- OOS: {oos_count} ({oos_pct}%)
- Restock flag: {restock_count}
- Soon flag: {soon_count}
- Watch flag: {watch_count}
- Healthy: {healthy_count}
- Total monthly profit at risk: ${profit_at_risk:,.2f}
- Total missed profit: ${missed_profit:,.2f}
- Seasonal coefficient now: {current_coeff}x
- Next 3 months coefficients: {month_plus_1}x, {month_plus_2}x, {month_plus_3}x
- Seasonal direction: {increasing/decreasing/stable}
- Top OOS item: {top_oos_name} (${top_oos_profit:,.2f}/mo)
- Primary suppliers: {supplier_list}
- Average lead time: {avg_lead_time}d
{end for}

SUPPLIER RISK:
{for each supplier with 3+ flagged items:}
- {supplier_name}: {flagged_count} flagged items across {category_count} categories | Avg lead time: {avg_lead}d | Total profit at risk: ${profit:,.2f}/mo
{end for}

Write 1-2 sentences per category, focusing on the most actionable insight for each. Then add a final paragraph on any supplier concentration risks (multiple critical items from the same supplier or long lead time suppliers with high exposure). Keep the entire analysis under 250 words. Do not speculate on causes for stockouts. If a pattern is unclear, say it requires investigation.
```

---

## Prompt 4: Needs Investigation

### Called once, only if there are OOS items with last_restock_date more than 60 days ago

### User message template:

```
Write a brief note about products that have been out of stock for an extended period with no recent restock activity. These items need a sourcing decision.

STALE OOS ITEMS:
{for each item:}
- {sku} {product_name} | Category: {category} | Supplier: {supplier} | Base velocity: {base_velocity}/day | Last restock: {last_restock_date} | Estimated days OOS: ~{est_days_oos} | Monthly profit when in stock: ${monthly_profit:,.2f} | Estimated missed profit: ${missed_profit:,.2f}
{end for}

TOTAL: {count} products have been OOS for 60+ days
Combined monthly profit when in stock: ${combined_monthly:,.2f}
Combined estimated missed profit: ${combined_missed:,.2f}

Write 2-3 sentences. Note how many items have been OOS for over 60 days and the combined financial impact. Group by pattern if visible (same supplier, same category, etc.). State that each item needs a sourcing decision: reorder now, find an alternative supplier, or formally discontinue. Do not speculate about specific reasons for the extended stockout. Keep it under 100 words.
```

---

## Fallback Templates (used when AI is unavailable or validation fails)

If the Claude API is unavailable, the key is not set, or post-generation validation fails twice, use these Python-generated templates instead:

### Executive Summary Fallback:

```python
def fallback_executive_summary(stats):
    return (
        f"Of {stats['total_skus']} SKUs analyzed, {stats['oos_count']} are currently "
        f"out of stock and {stats['at_risk_count']} additional products are at risk of "
        f"stockout. Estimated daily revenue lost from OOS items is "
        f"${stats['daily_revenue_lost']:,.2f}, with ${stats['monthly_profit_at_risk']:,.2f} "
        f"in total monthly profit at risk. Missed profit to date from current OOS items "
        f"is estimated at ${stats['missed_profit']:,.2f}.\n\n"
        f"The most urgent item is {stats['top_item_name']} ({stats['top_item_sku']}), "
        f"which is {stats['top_item_flag']} with ${stats['top_item_monthly']:,.2f} in "
        f"monthly profit at risk and an estimated ${stats['top_item_missed']:,.2f} in "
        f"missed profit to date."
    )
```

### Per-SKU Fallback:

```python
def fallback_sku_recommendation(item):
    if item['stock'] == 0:
        action = "Reorder now"
        context = (
            f"This product has been out of stock since approximately {item['est_oos_date']}. "
            f"With a lead time of {item['lead_time']} days, new stock would arrive "
            f"approximately {item['lead_time']} days after ordering."
        )
    else:
        action = "Reorder now"
        context = (
            f"Current stock of {item['stock']} units covers approximately "
            f"{item['projected_days']} days at current velocity. Lead time is "
            f"{item['lead_time']} days."
        )
    
    financial = (
        f"${item['monthly_profit']:,.2f} in monthly profit is at risk."
    )
    
    if item['missed_profit'] and item['missed_profit'] > 0:
        financial += f" Estimated missed profit to date: ${item['missed_profit']:,.2f}."
    
    order = (
        f"Recommended order: {item['rec_qty']} units "
        f"(estimated cost: ${item['est_cost']:,.2f})."
    )
    
    return f"{action}. {context} {financial} {order}"
```

### Category Analysis Fallback:

```python
def fallback_category_analysis(categories):
    lines = []
    for cat in categories:
        lines.append(
            f"{cat['name']}: {cat['oos_count']} OOS, {cat['at_risk_count']} at risk, "
            f"${cat['profit_at_risk']:,.2f}/mo profit at risk. "
            f"Season: {cat['current_coeff']}x (direction: {cat['direction']})."
        )
    return "\n".join(lines)
```

### Investigation Fallback:

```python
def fallback_investigation(stale_items, combined_monthly, combined_missed):
    return (
        f"{len(stale_items)} products have been out of stock for over 60 days with "
        f"no recent restock activity. Combined monthly profit when in stock: "
        f"${combined_monthly:,.2f}. Estimated missed profit to date: "
        f"${combined_missed:,.2f}. Each item requires a sourcing decision: "
        f"reorder now, find an alternative supplier, or formally discontinue."
    )
```

---

## Post-Generation Validation

```python
def validate_ai_output(text, products, stats):
    """Validate AI output references only real data. Returns (is_valid, warnings)."""
    import re
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
    allowed_actions = [
        "reorder now", "expedite review", "monitor closely",
        "investigate", "verify reorder point"
    ]
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


def generate_with_validation(client, system_msg, user_msg, products, stats, max_retries=1):
    """Generate AI text with validation and fallback."""
    for attempt in range(max_retries + 1):
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            temperature=0.3,
            system=system_msg,
            messages=[{"role": "user", "content": user_msg}]
        )
        text = response.content[0].text
        is_valid, warnings = validate_ai_output(text, products, stats)
        
        if is_valid:
            return text, True
        
        if attempt < max_retries:
            print(f"AI validation failed (attempt {attempt + 1}): {warnings}")
            print("Retrying...")
        else:
            print(f"AI validation failed after {max_retries + 1} attempts: {warnings}")
            print("Falling back to templated text.")
            return None, False
    
    return None, False
```

---

## Implementation Flow in oos_tool.py

```python
def generate_ai_insights(products, categories, stats, settings):
    """Generate all AI insight sections with validation and fallback."""
    
    if not os.environ.get('ANTHROPIC_API_KEY'):
        print("No ANTHROPIC_API_KEY set. Using fallback templates.")
        return generate_fallback_insights(products, categories, stats)
    
    try:
        client = anthropic.Anthropic()
        system_msg = SYSTEM_MESSAGE
        insights = {}
        
        # 1. Executive Summary
        exec_prompt = format_executive_prompt(products, categories, stats)
        exec_text, exec_valid = generate_with_validation(
            client, system_msg, exec_prompt, products, stats
        )
        insights['executive_summary'] = exec_text or fallback_executive_summary(stats)
        
        # 2. Per-SKU Recommendations (one call per item, capped at 15)
        priority_items = [
            p for p in products 
            if p['flag'] in ('OOS', 'Restock') 
            and p['tier'] in ('Critical', 'High')
        ][:15]
        
        sku_recs = {}
        for item in priority_items:
            sku_prompt = format_sku_prompt(item)
            sku_text, sku_valid = generate_with_validation(
                client, system_msg, sku_prompt, products, stats
            )
            sku_recs[item['sku']] = sku_text or fallback_sku_recommendation(item)
        insights['sku_recommendations'] = sku_recs
        
        # 3. Category Analysis
        cat_prompt = format_category_prompt(categories, products, stats)
        cat_text, cat_valid = generate_with_validation(
            client, system_msg, cat_prompt, products, stats
        )
        insights['category_analysis'] = cat_text or fallback_category_analysis(categories)
        
        # 4. Needs Investigation
        stale_items = [p for p in products if p['stock'] == 0 and p.get('est_days_oos', 0) > 60]
        if stale_items:
            inv_prompt = format_investigation_prompt(stale_items)
            inv_text, inv_valid = generate_with_validation(
                client, system_msg, inv_prompt, products, stats
            )
            combined_monthly = sum(i['monthly_profit'] for i in stale_items)
            combined_missed = sum(i.get('missed_profit', 0) for i in stale_items)
            insights['investigation_notes'] = inv_text or fallback_investigation(
                stale_items, combined_monthly, combined_missed
            )
        else:
            insights['investigation_notes'] = None
        
        return insights
    
    except Exception as e:
        print(f"AI generation failed: {e}")
        print("Using fallback templates for all sections.")
        return generate_fallback_insights(products, categories, stats)


def generate_fallback_insights(products, categories, stats):
    """Generate all sections using deterministic templates."""
    stale_items = [p for p in products if p['stock'] == 0 and p.get('est_days_oos', 0) > 60]
    combined_monthly = sum(i['monthly_profit'] for i in stale_items)
    combined_missed = sum(i.get('missed_profit', 0) for i in stale_items)
    
    priority_items = [
        p for p in products 
        if p['flag'] in ('OOS', 'Restock') 
        and p['tier'] in ('Critical', 'High')
    ][:15]
    
    return {
        'executive_summary': fallback_executive_summary(stats),
        'sku_recommendations': {item['sku']: fallback_sku_recommendation(item) for item in priority_items},
        'category_analysis': fallback_category_analysis(categories),
        'investigation_notes': fallback_investigation(stale_items, combined_monthly, combined_missed) if stale_items else None
    }
```

---

## README Documentation for AI Guardrails

Include this in the README:

```
### AI Guardrails

Claude does not analyze inventory. Python analyzes inventory. Claude converts 
validated metrics into business-readable language.

The AI layer uses five safeguards:

1. **Deterministic computation**: All metrics (flags, tiers, urgency scores, 
   projected days, profit at risk, recommended quantities) are computed in 
   Python. The LLM receives pre-computed results only.

2. **Narrow prompts**: Each AI section receives only the data it needs. 
   Per-SKU recommendations receive one product at a time to prevent 
   cross-item contamination.

3. **Constrained output**: The system prompt explicitly bans causal 
   speculation ("likely due to", "caused by"), unauthorized actions 
   (supplier switches, pricing changes), external references (market 
   trends, competitor activity), and any numbers not in the provided data.

4. **Post-generation validation**: After each AI response, Python scans 
   for unknown SKUs, banned phrases, unauthorized actions, and external 
   entity references. If validation fails, the text is regenerated once. 
   If it fails again, the system falls back to deterministic templates.

5. **Graceful fallback**: If the API key is not set, the API is unreachable, 
   or validation fails, every section renders using Python-generated 
   template text. The dashboard is fully functional without AI.
```

---

## Cost Estimate

- Executive summary: ~1500 tokens out = ~$0.02
- 15 SKU recommendations: ~300 tokens each = ~$0.07
- Category analysis: ~1500 tokens = ~$0.02
- Investigation: ~500 tokens = ~$0.01
- Validation retries (rare): ~$0.02
- Total per run: ~$0.14
