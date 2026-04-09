import csv
import random
import os
from datetime import datetime, timedelta

random.seed(42)
CURRENT_MONTH = 4
TODAY = datetime(2026, 4, 9)
RECEIVING_BUFFER = 5

SEASONALITY = {
    "Blankets & Sheets": [0.90, 0.75, 0.60, 0.40, 0.25, 0.20, 0.20, 0.35, 0.70, 1.10, 1.50, 1.70],
    "Fly & Insect Control": [0.30, 0.40, 0.70, 1.00, 1.40, 1.60, 1.70, 1.50, 1.00, 0.50, 0.25, 0.20],
    "Tack & Saddles": [0.75, 0.80, 0.85, 0.90, 0.90, 0.85, 0.85, 0.80, 0.90, 1.00, 1.30, 1.70],
    "Riding Apparel": [0.75, 0.80, 0.85, 0.90, 0.90, 0.85, 0.85, 0.80, 0.90, 1.00, 1.30, 1.70],
    "Barn & Stable": [0.75, 0.80, 0.85, 0.90, 0.90, 0.85, 0.85, 0.80, 0.90, 1.00, 1.30, 1.70],
    "Grooming": [0.75, 0.80, 0.85, 0.90, 0.90, 0.85, 0.85, 0.80, 0.90, 1.00, 1.30, 1.70],
    "Supplements & Health": [0.80, 0.85, 0.90, 0.95, 0.95, 0.90, 0.90, 0.85, 0.90, 0.95, 1.10, 1.30],
    "Boots & Wraps": [0.75, 0.80, 0.85, 0.90, 0.90, 0.85, 0.85, 0.80, 0.90, 1.00, 1.30, 1.70],
    "Horse Tack Accessories": [0.75, 0.80, 0.85, 0.90, 0.90, 0.85, 0.85, 0.80, 0.90, 1.00, 1.30, 1.70],
    "Rider Accessories": [0.75, 0.80, 0.85, 0.90, 0.90, 0.85, 0.85, 0.80, 0.90, 1.00, 1.30, 1.70],
}

SUPPLIERS = {
    "Dover Wholesale":        {"lead": 18, "ship": 5},
    "Weatherbeeta Direct":    {"lead": 55, "ship": 10},
    "Farnam Direct":          {"lead": 16, "ship": 5},
    "Pacific Rim Imports":    {"lead": 75, "ship": 16},
    "Blue Ridge Equine Supply": {"lead": 20, "ship": 4},
    "Mountain Horse EU":      {"lead": 60, "ship": 12},
    "Horsemens Pride":        {"lead": 21, "ship": 5},
    "Local Craftworks":       {"lead": 14, "ship": 3},
}

PRODUCTS = {
    "Blankets & Sheets": [
        ("Contour Collar Classic Surcingle Turnout Blanket", (45, 85), "Weatherbeeta Direct"),
        ("Warrior II V-Free Wither Relief Turnout", (55, 100), "Pacific Rim Imports"),
        ("Challenger Cutback Adjusta-Fit Surcingle Turnout", (50, 90), "Pacific Rim Imports"),
        ("Dura-Nylon Original Cutback Stable Sheet", (22, 40), "Dover Wholesale"),
        ("Tekno-Fleece V-Free Leg Strap Stable Blanket", (28, 50), "Dover Wholesale"),
        ("SuperQuilt Cutback Bellyband Heavy Stable Blanket", (35, 65), "Pacific Rim Imports"),
        ("Memphis Medium Weight Leg Strap Stable Blanket", (25, 45), "Dover Wholesale"),
        ("Blizzard II Attached Neck Euro Turnout", (60, 110), "Weatherbeeta Direct"),
        ("Viking Classic Euro Surcingle Pony Turnout", (30, 55), "Mountain Horse EU"),
        ("Hunt Club Plaid Medium Weight Stable Blanket", (22, 42), "Dover Wholesale"),
        ("Expandable Lightweight Foal Stable Blanket", (17, 32), "Dover Wholesale"),
        ("Insulated Waterproof Reflective Dog Coat", (12, 25), "Pacific Rim Imports"),
        ("Euro Bellyband Medium Weight Foal Turnout", (35, 65), "Weatherbeeta Direct"),
        ("Challenger II Senior VTEK Turnout 220g", (60, 105), "Pacific Rim Imports"),
        ("RipGuard Bellyband Pony Turnout Sheet", (25, 45), "Weatherbeeta Direct"),
        ("Adjusta-Fit Draft Surcingle Turnout", (65, 120), "Pacific Rim Imports"),
        ("Mosquito Mesh Cutback Adjusta-Fit Fly Sheet", (20, 37), "Dover Wholesale"),
        ("Full Zip Slicker Hood", (10, 20), "Dover Wholesale"),
        ("Contour Collar Diamond Surcingle Turnout LE", (50, 95), "Pacific Rim Imports"),
        ("Cooler Show Cover Anti-Static Dress Sheet", (17, 35), "Dover Wholesale"),
        ("Dura-Nylon VTEK Senior Medium Weight Stable Blanket", (30, 55), "Dover Wholesale"),
        ("Ripstop Nylon Mesh Euro Surcingle Fly Sheet", (22, 42), "Dover Wholesale"),
        ("Warrior II VTEK Bellyband Turnout Heavy", (65, 115), "Pacific Rim Imports"),
        ("Challenger II V-Free Adjusta-Fit Draft Turnout", (70, 125), "Pacific Rim Imports"),
        ("Tekno-Fleece Cutback Bellyband Stable Blanket LW", (25, 47), "Dover Wholesale"),
    ],
    "Fly & Insect Control": [
        ("Mosquito Mesh Adjusta-Fit Fly Sheet", (20, 40), "Dover Wholesale"),
        ("Premium Fly Mask with Ears", (6, 12), "Blue Ridge Equine Supply"),
        ("Endure Sweat-Resistant Fly Spray 32oz", (4, 8), "Farnam Direct"),
        ("Ultra Shield EX Fly Spray Gallon", (15, 27), "Farnam Direct"),
        ("Fly Predators Monthly Supply 5-Pack", (10, 20), "Horsemens Pride"),
        ("Mesh Fly Boots Set of 4", (8, 17), "Blue Ridge Equine Supply"),
        ("Pyranha Wipe N Spray Quart", (5, 9), "Farnam Direct"),
        ("Fly Mask with Nose Guard UV Protection", (7, 15), "Blue Ridge Equine Supply"),
        ("Automatic Fly Spray System Refill", (11, 22), "Farnam Direct"),
        ("Mesh Belly Guard Fly Sheet", (22, 42), "Dover Wholesale"),
        ("Natural Botanical Fly Repellent 32oz", (6, 11), "Blue Ridge Equine Supply"),
        ("Fly Trap Disposable Ranch Pack 4ct", (4, 8), "Farnam Direct"),
        ("Mosquito Mesh II Attached Neck V-Free Fly Sheet", (27, 50), "Dover Wholesale"),
        ("Fly Leg Wraps Protective Mesh Set of 4", (10, 20), "Blue Ridge Equine Supply"),
        ("Spot On Fly Control Applicator 3-Pack", (7, 15), "Farnam Direct"),
    ],
    "Tack & Saddles": [
        ("All-Purpose English Saddle Package", (125, 250), "Pacific Rim Imports"),
        ("Western Trail Saddle Flex Tree", (175, 350), "Pacific Rim Imports"),
        ("Leather Raised Snaffle Bridle", (17, 35), "Mountain Horse EU"),
        ("Nylon Web Halter with Brass Hardware", (4, 9), "Dover Wholesale"),
        ("Fleece Lined Dressage Girth", (15, 30), "Mountain Horse EU"),
        ("Contoured Wool Saddle Pad", (20, 40), "Local Craftworks"),
        ("Stainless Steel D-Ring Snaffle Bit", (7, 15), "Dover Wholesale"),
        ("Leather Breastcollar with Running Attachment", (22, 45), "Mountain Horse EU"),
        ("Neoprene Western Cinch", (12, 25), "Pacific Rim Imports"),
        ("Cotton Lead Rope with Brass Snap 10ft", (3, 7), "Blue Ridge Equine Supply"),
        ("Dressage Bridle with Flash Noseband", (25, 50), "Mountain Horse EU"),
        ("Breakaway Halter Safety Release", (6, 12), "Dover Wholesale"),
        ("Synthetic Western Trail Saddle", (100, 200), "Pacific Rim Imports"),
        ("Shaped Fleece Saddle Pad All-Purpose", (12, 25), "Local Craftworks"),
        ("Bit Guard Rubber Pair", (2, 4), "Blue Ridge Equine Supply"),
        ("HDR Advantage All Purpose Saddle", (150, 275), "Pacific Rim Imports"),
        ("Billy Royal Western Show Saddle", (250, 450), "Pacific Rim Imports"),
        ("Wintec Synthetic Dressage Saddle", (175, 325), "Mountain Horse EU"),
        ("Leather Reins Laced with Stops 54in", (10, 20), "Mountain Horse EU"),
        ("Pinnacle Fancy Stitched Padded Bridle", (20, 40), "Mountain Horse EU"),
    ],
    "Riding Apparel": [
        ("Ladies Breech Knee Patch Full Seat", (25, 50), "Mountain Horse EU"),
        ("Tall Field Boot Premium Leather", (75, 150), "Mountain Horse EU"),
        ("Velvet Riding Helmet ASTM Certified", (20, 40), "Pacific Rim Imports"),
        ("Waterproof Riding Jacket Breathable", (30, 60), "Mountain Horse EU"),
        ("Winter Riding Gloves Thinsulate", (7, 15), "Dover Wholesale"),
        ("Show Shirt White Competition Ratcatcher", (15, 30), "Pacific Rim Imports"),
        ("Paddock Boots Zip Front Leather", (35, 70), "Mountain Horse EU"),
        ("Half Chaps Synthetic Suede", (15, 30), "Pacific Rim Imports"),
        ("Riding Vest Quilted Insulated", (17, 35), "Mountain Horse EU"),
        ("Western Boot Cut Riding Jean", (20, 40), "Dover Wholesale"),
        ("Sun Shirt UV Protection Long Sleeve", (12, 25), "Pacific Rim Imports"),
        ("Safety Vest Body Protector BETA Level 3", (45, 90), "Mountain Horse EU"),
        ("Hunt Coat Show Jacket Navy", (40, 75), "Mountain Horse EU"),
        ("Western Show Shirt Sequin Trim", (17, 35), "Pacific Rim Imports"),
        ("Jodhpur Boots Children Zip", (15, 30), "Mountain Horse EU"),
        ("Riding Tights Silicone Grip Full Seat", (22, 45), "Pacific Rim Imports"),
    ],
    "Barn & Stable": [
        ("Heavy Duty Corner Feeder", (10, 20), "Horsemens Pride"),
        ("Rubber Stall Mat 4x6", (17, 32), "Blue Ridge Equine Supply"),
        ("Automatic Waterer Insulated", (45, 85), "Horsemens Pride"),
        ("Hay Net Slow Feed Small Mesh", (7, 15), "Blue Ridge Equine Supply"),
        ("Bucket Hook Over Door 8qt", (2, 5), "Dover Wholesale"),
        ("Cross Tie Panic Snap Set", (5, 10), "Dover Wholesale"),
        ("Stall Guard Adjustable Nylon", (6, 12), "Dover Wholesale"),
        ("Muck Bucket 70qt Heavy Duty", (6, 11), "Horsemens Pride"),
        ("Hay Bale Storage Bag Waterproof", (12, 25), "Blue Ridge Equine Supply"),
        ("Salt Block Holder Wall Mount", (3, 7), "Dover Wholesale"),
        ("Stall Fan Barn 18in Oscillating", (25, 50), "Horsemens Pride"),
        ("Blanket Bar Wall Mount Folding", (10, 20), "Local Craftworks"),
        ("Easy-Up Titan Stall Gate", (50, 95), "Horsemens Pride"),
        ("Manure Fork Platinum Unbreakable", (7, 15), "Horsemens Pride"),
        ("Multipurpose Muck Cart Rolling", (25, 47), "Horsemens Pride"),
        ("Saddle Rack Wall Mount Folding", (12, 25), "Local Craftworks"),
        ("Bridle Rack Coated Metal 4-Hook", (5, 10), "Local Craftworks"),
        ("Corner Floor Hay Rack with Lid", (17, 32), "Horsemens Pride"),
        ("Mounting Block 3-Step Portable", (22, 42), "Horsemens Pride"),
        ("Stall Drapes Show Custom Set", (30, 60), "Local Craftworks"),
    ],
    "Grooming": [
        ("Body Brush Natural Bristle", (5, 10), "Blue Ridge Equine Supply"),
        ("Mane and Tail Detangler Spray 32oz", (4, 7), "Farnam Direct"),
        ("Hoof Pick with Brush Combo", (2, 4), "Blue Ridge Equine Supply"),
        ("Shedding Blade Sweat Scraper Combo", (3, 6), "Dover Wholesale"),
        ("Medicated Shampoo Antifungal 32oz", (5, 11), "Farnam Direct"),
        ("Grooming Tote Bag with Pockets", (7, 15), "Blue Ridge Equine Supply"),
        ("Electric Clipper Body Clip Pro", (65, 125), "Dover Wholesale"),
        ("Rubber Curry Comb Original", (1.50, 3), "Blue Ridge Equine Supply"),
        ("Show Sheen Hair Polish 32oz", (4, 8), "Farnam Direct"),
        ("Mane Pulling Comb Aluminum", (2, 5), "Dover Wholesale"),
        ("Braiding Kit Complete with Thread", (4, 8), "Blue Ridge Equine Supply"),
        ("Hoof Conditioner Moisturizer 32oz", (5, 9), "Farnam Direct"),
        ("Tail Bag Lycra Stretch", (3, 7), "Blue Ridge Equine Supply"),
        ("Clipper Blade Coolant Spray 15oz", (3, 6), "Farnam Direct"),
        ("Grooming Mitt Dual Sided", (2, 5), "Blue Ridge Equine Supply"),
    ],
    "Supplements & Health": [
        ("Joint Supplement Glucosamine Pellets 5lb", (15, 27), "Farnam Direct"),
        ("Electrolyte Powder Apple Flavor 5lb", (7, 15), "Farnam Direct"),
        ("Hoof Supplement Biotin Daily Pellets 10lb", (20, 37), "Farnam Direct"),
        ("Calming Supplement Magnesium Paste 60ml", (10, 20), "Blue Ridge Equine Supply"),
        ("Probiotic Digestive Support Powder 4lb", (12, 25), "Farnam Direct"),
        ("Wound Care Spray Antimicrobial 16oz", (4, 9), "Blue Ridge Equine Supply"),
        ("Thrush Treatment Liquid 16oz", (4, 8), "Farnam Direct"),
        ("Poultice Cooling Clay 5lb", (5, 10), "Blue Ridge Equine Supply"),
        ("Fly Bite Relief Gel 12oz", (3, 7), "Farnam Direct"),
        ("Weight Gain Supplement High Fat 25lb", (17, 32), "Farnam Direct"),
        ("Dewormer Paste Ivermectin Single Dose", (2, 5), "Farnam Direct"),
        ("Liniment Cooling Gel 16oz", (4, 9), "Blue Ridge Equine Supply"),
        ("Vitamin E Selenium Supplement Pellets 10lb", (17, 32), "Farnam Direct"),
        ("Sand Clear Psyllium Pellets 20lb", (15, 27), "Farnam Direct"),
        ("Omega 3 Oil Supplement Gallon", (12, 22), "Farnam Direct"),
        ("Calming Wafer Treats 30ct", (7, 15), "Blue Ridge Equine Supply"),
    ],
    "Boots & Wraps": [
        ("Sport Medicine Boots Front Pair", (15, 30), "Dover Wholesale"),
        ("Polo Wraps Set of 4 Fleece", (7, 15), "Dover Wholesale"),
        ("Bell Boots No Turn Rubber Pair", (5, 10), "Blue Ridge Equine Supply"),
        ("Standing Wraps Quilted Set of 4", (10, 20), "Dover Wholesale"),
        ("Ceramic Therapy Hock Wraps Pair", (25, 50), "Horsemens Pride"),
        ("Shipping Boots Full Set of 4", (17, 35), "Dover Wholesale"),
        ("Splint Boots Neoprene Front Pair", (8, 17), "Blue Ridge Equine Supply"),
        ("Ice Boot Therapy Full Leg", (20, 40), "Horsemens Pride"),
        ("Tendon Boots Open Front Pair", (12, 25), "Mountain Horse EU"),
        ("Quick Wrap Standing Bandage Set of 4", (12, 22), "Dover Wholesale"),
        ("Hoof Boot Emergency Soaking Size M", (10, 20), "Horsemens Pride"),
        ("Fetlock Boots Hind Pair", (10, 20), "Mountain Horse EU"),
        ("Vet Flex Bandage Wrap 4in", (2, 4), "Blue Ridge Equine Supply"),
        ("Ceramic Therapy Knee Boots Pair", (30, 60), "Horsemens Pride"),
        ("Galloping Boots Cross Country Pair", (17, 35), "Mountain Horse EU"),
    ],
    "Horse Tack Accessories": [
        ("Leather Girth Extender 6in", (5, 10), "Dover Wholesale"),
        ("Stirrup Irons Fillis Stainless 4.75in", (10, 20), "Mountain Horse EU"),
        ("Nylon Stirrup Leathers 54in", (6, 12), "Dover Wholesale"),
        ("Martingale Running Attachment Leather", (15, 30), "Mountain Horse EU"),
        ("Saddle Pad Liner Fleece Half Pad", (10, 20), "Local Craftworks"),
        ("Lunge Line Cotton Web 25ft", (5, 10), "Blue Ridge Equine Supply"),
        ("Side Reins Elastic Insert Pair", (7, 15), "Mountain Horse EU"),
        ("Curb Chain Stainless Steel Single Link", (2, 5), "Dover Wholesale"),
        ("Breastplate 5-Point Elastic", (20, 40), "Mountain Horse EU"),
        ("Horse Toy Jolly Ball 10in", (5, 10), "Horsemens Pride"),
        ("Grazing Muzzle Adjustable Nylon", (10, 20), "Dover Wholesale"),
        ("Training Surcingle Fleece Lined", (17, 32), "Dover Wholesale"),
        ("Draw Reins Nylon Web", (6, 12), "Dover Wholesale"),
        ("Salt Lick Himalayan on Rope", (3, 6), "Blue Ridge Equine Supply"),
    ],
    "Rider Accessories": [
        ("Helmet Bag Padded with Vent", (7, 15), "Blue Ridge Equine Supply"),
        ("Spur Straps Leather Plain", (3, 7), "Dover Wholesale"),
        ("Riding Crop Leather Wrapped 26in", (5, 10), "Dover Wholesale"),
        ("Boot Bag Tall Zip with Handle", (7, 15), "Blue Ridge Equine Supply"),
        ("Garment Bag Show Coat Standard", (10, 20), "Blue Ridge Equine Supply"),
        ("Belt Leather Elastic with Buckle", (7, 15), "Dover Wholesale"),
        ("Hair Net Show Ring 2-Pack", (1.50, 3), "Blue Ridge Equine Supply"),
        ("Stock Tie Pre-Tied White", (6, 12), "Mountain Horse EU"),
        ("Riding Sock Tall Boot Moisture Wicking", (4, 7), "Blue Ridge Equine Supply"),
        ("Number Holder Arm Band Pair", (2, 5), "Dover Wholesale"),
        ("Spurs Prince of Wales Stainless", (7, 15), "Dover Wholesale"),
        ("Boot Jack Pull Off", (3, 7), "Blue Ridge Equine Supply"),
    ],
}

def generate_data():
    rows = []
    sku_counter = 10001
    for category, products in PRODUCTS.items():
        season_coeff = SEASONALITY[category][CURRENT_MONTH - 1]
        for item in products:
            product_name, (cost_low, cost_high), default_supplier = item
            sku = f"SCH-{sku_counter}"
            sku_counter += 1
            sup = SUPPLIERS[default_supplier]
            supplier_lead_time = sup["lead"]
            shipping_time = sup["ship"]
            total_lead = supplier_lead_time + shipping_time + RECEIVING_BUFFER

            unit_cost = round(random.uniform(cost_low, cost_high), 2)
            margin_pct = random.uniform(0.50, 0.70)
            unit_price = round(unit_cost / (1 - margin_pct), 2)

            velocity_tier = random.random()
            if velocity_tier < 0.05:
                base_velocity = round(random.uniform(10, 20), 2)
            elif velocity_tier < 0.20:
                base_velocity = round(random.uniform(4, 10), 2)
            elif velocity_tier < 0.50:
                base_velocity = round(random.uniform(1, 4), 2)
            else:
                base_velocity = round(random.uniform(0.1, 1), 2)

            avg_daily_velocity = round(base_velocity * season_coeff, 2)
            if avg_daily_velocity < 0.01:
                avg_daily_velocity = 0.01

            rp_type = random.random()
            if rp_type < 0.05:
                reorder_point = 0
            elif rp_type < 0.20:
                reorder_point = int(avg_daily_velocity * (total_lead + random.randint(10, 25)))
            else:
                reorder_point = max(1, int(avg_daily_velocity * (total_lead + random.randint(3, 7))))

            stock_scenario = random.random()
            if stock_scenario < 0.10:
                current_stock = 0
                last_restock = TODAY - timedelta(days=random.randint(60, 120)) if random.random() < 0.5 else TODAY - timedelta(days=random.randint(20, 45))
            elif stock_scenario < 0.15:
                current_stock = max(1, int(avg_daily_velocity * random.uniform(1, 10)))
                last_restock = TODAY - timedelta(days=random.randint(30, 60))
            elif stock_scenario < 0.22:
                current_stock = max(1, int(avg_daily_velocity * random.uniform(10, 30)))
                last_restock = TODAY - timedelta(days=random.randint(20, 50))
            elif stock_scenario < 0.40:
                current_stock = int(avg_daily_velocity * random.uniform(40, 90))
                last_restock = TODAY - timedelta(days=random.randint(14, 35))
            else:
                current_stock = int(avg_daily_velocity * random.uniform(80, 180))
                last_restock = TODAY - timedelta(days=random.randint(7, 21))

            rows.append({
                "sku": sku, "product_name": product_name, "category": category,
                "current_stock": current_stock, "reorder_point": reorder_point,
                "supplier_lead_time": supplier_lead_time, "shipping_time": shipping_time,
                "receiving_buffer": RECEIVING_BUFFER,
                "base_velocity": base_velocity,
                "avg_daily_velocity": avg_daily_velocity,
                "last_restock_date": last_restock.strftime("%Y-%m-%d"),
                "unit_cost": unit_cost, "unit_price": unit_price, "supplier": default_supplier,
            })

    # Force specific scenarios
    rows[0]["current_stock"] = 0; rows[0]["base_velocity"] = 8.75; rows[0]["avg_daily_velocity"] = 3.5; rows[0]["last_restock_date"] = (TODAY - timedelta(days=75)).strftime("%Y-%m-%d")
    rows[3]["current_stock"] = 8; rows[3]["base_velocity"] = 10.5; rows[3]["avg_daily_velocity"] = 4.2
    idx = next(i for i, r in enumerate(rows) if "Western Trail Saddle" in r["product_name"])
    rows[idx]["current_stock"] = 0; rows[idx]["base_velocity"] = 2.0; rows[idx]["avg_daily_velocity"] = 1.8; rows[idx]["last_restock_date"] = (TODAY - timedelta(days=90)).strftime("%Y-%m-%d")
    idx = next(i for i, r in enumerate(rows) if "Mane Pulling Comb" in r["product_name"])
    rows[idx]["current_stock"] = 0; rows[idx]["base_velocity"] = 2.22; rows[idx]["avg_daily_velocity"] = 2.0
    idx = next(i for i, r in enumerate(rows) if "Ultra Shield EX" in r["product_name"])
    rows[idx]["current_stock"] = 45; rows[idx]["base_velocity"] = 6.5; rows[idx]["avg_daily_velocity"] = 6.5
    idx = next(i for i, r in enumerate(rows) if "Joint Supplement" in r["product_name"])
    rows[idx]["current_stock"] = 85; rows[idx]["base_velocity"] = 8.95; rows[idx]["avg_daily_velocity"] = 8.5
    idx = next(i for i, r in enumerate(rows) if "Billy Royal" in r["product_name"])
    rows[idx]["current_stock"] = 0; rows[idx]["base_velocity"] = 0.89; rows[idx]["avg_daily_velocity"] = 0.8; rows[idx]["last_restock_date"] = (TODAY - timedelta(days=95)).strftime("%Y-%m-%d")
    idx = next(i for i, r in enumerate(rows) if "Titan Stall Gate" in r["product_name"])
    rows[idx]["current_stock"] = 22; rows[idx]["base_velocity"] = 3.56; rows[idx]["avg_daily_velocity"] = 3.2

    filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_data", "inventory.csv")
    fieldnames = ["sku", "product_name", "category", "current_stock", "reorder_point",
        "supplier_lead_time", "shipping_time", "receiving_buffer",
        "base_velocity", "avg_daily_velocity",
        "last_restock_date", "unit_cost", "unit_price", "supplier"]
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # Analysis
    total = len(rows)
    BUFFER = 7
    flags = {"Purple": 0, "Red": 0, "Yellow": 0, "Blue": 0, "Green": 0}
    tiers = {"Critical": 0, "High": 0, "Medium": 0, "Watch": 0}
    for r in rows:
        vel, stock = r["avg_daily_velocity"], r["current_stock"]
        lead = r["supplier_lead_time"] + r["shipping_time"] + r["receiving_buffer"]
        profit_mo = vel * (r["unit_price"] - r["unit_cost"]) * 30
        dos = stock / vel if vel > 0.01 else 9999
        urgency = dos - (lead + BUFFER)
        if stock == 0: flags["Purple"] += 1
        elif urgency < 0: flags["Red"] += 1
        elif urgency < 14: flags["Yellow"] += 1
        elif urgency < 30: flags["Blue"] += 1
        else: flags["Green"] += 1
        if profit_mo > 5000: tiers["Critical"] += 1
        elif profit_mo > 1000: tiers["High"] += 1
        elif profit_mo > 250: tiers["Medium"] += 1
        else: tiers["Watch"] += 1

    print(f"Generated {total} products across {len(PRODUCTS)} categories")
    print(f"\n=== FLAGS ===")
    for f, c in flags.items(): print(f"  {f}: {c} ({c/total*100:.0f}%)")
    print(f"\n=== RISK TIERS ===")
    for t, c in tiers.items(): print(f"  {t}: {c} ({c/total*100:.0f}%)")
    ratios = [r["unit_cost"]/r["unit_price"]*100 for r in rows]
    margins = [(r["unit_price"]-r["unit_cost"])/r["unit_price"]*100 for r in rows]
    leads_l = [r["supplier_lead_time"]+r["shipping_time"]+r["receiving_buffer"] for r in rows]
    rps = [r["reorder_point"] for r in rows]
    rp_zero = sum(1 for rp in rps if rp == 0)
    print(f"\n=== COST/PRICE === Min:{min(ratios):.0f}% Max:{max(ratios):.0f}% Avg:{sum(ratios)/len(ratios):.0f}%")
    print(f"=== MARGIN === Min:{min(margins):.0f}% Max:{max(margins):.0f}% Avg:{sum(margins)/len(margins):.0f}%")
    print(f"=== LEAD TIMES === Min:{min(leads_l)}d Max:{max(leads_l)}d Avg:{sum(leads_l)/len(leads_l):.0f}d")
    print(f"=== REORDER POINTS === Zero: {rp_zero}/{total} ({rp_zero/total*100:.0f}%)")
    print(f"\n=== LEAD TIME BY SUPPLIER ===")
    for s, info in SUPPLIERS.items():
        t = info["lead"] + info["ship"] + RECEIVING_BUFFER
        print(f"  {s}: {info['lead']}d lead + {info['ship']}d ship + {RECEIVING_BUFFER}d buffer = {t}d total")
    print(f"\nFile: {filepath}")

if __name__ == "__main__":
    generate_data()
