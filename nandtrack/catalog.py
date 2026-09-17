"""The tracked SKUs.

`baseline` is the street price (EUR, incl. VAT, cheapest reputable EU retailer)
around 1 September 2025 - the calm week before NAND and DRAM contract pricing
broke. `surge_scale` says how hard this particular SKU rides its category curve:
1.0 tracks the category exactly, 0.5 moves half as far above the baseline, 1.8
moves nearly twice as far. See market.py for where the curves come from.

Add your own SKUs here - `sku` just has to stay unique and stable.
"""

from __future__ import annotations

from typing import Dict, List

CATEGORIES: Dict[str, dict] = {
    "ram": {"label": "RAM", "blurb": "DDR4 and DDR5 modules", "colour": "#F2994A"},
    "gpu": {"label": "Graphics cards", "blurb": "GDDR6 / GDDR7 board pricing", "colour": "#B47DE8"},
    "sata_ssd": {"label": "SATA SSDs", "blurb": "2.5-inch TLC and QLC drives", "colour": "#4EA8FF"},
    "nvme_ssd": {"label": "NVMe SSDs", "blurb": "M.2 PCIe 4.0 and 5.0 drives", "colour": "#3ECFB0"},
}

CATEGORY_ORDER = ["ram", "gpu", "sata_ssd", "nvme_ssd"]


def _p(sku, name, category, brand, baseline, scale=1.0, capacity_gb=None,
       form_factor="", interface="") -> dict:
    return {
        "sku": sku, "name": name, "category": category, "brand": brand,
        "capacity_gb": capacity_gb, "form_factor": form_factor,
        "interface": interface, "baseline": float(baseline),
        "surge_scale": float(scale),
    }


CATALOG: List[dict] = [
    # ---------------- RAM -------------------------------------------------
    _p("ram-ddr5-32-6000c30", "Corsair Vengeance 32GB (2x16) DDR5-6000 CL30", "ram",
       "Corsair", 89.0, 1.00, 32, "DIMM", "DDR5-6000 CL30"),
    _p("ram-ddr5-32-6400c32", "G.Skill Trident Z5 32GB (2x16) DDR5-6400 CL32", "ram",
       "G.Skill", 129.0, 1.05, 32, "DIMM", "DDR5-6400 CL32"),
    _p("ram-ddr5-64-6000c30", "Kingston Fury Beast 64GB (2x32) DDR5-6000 CL30", "ram",
       "Kingston", 198.0, 1.10, 64, "DIMM", "DDR5-6000 CL30"),
    _p("ram-ddr5-16-5600c36", "Crucial Pro 16GB (1x16) DDR5-5600 CL36", "ram",
       "Crucial", 44.0, 0.95, 16, "DIMM", "DDR5-5600 CL36"),
    _p("ram-ddr5-so-32-5600", "Crucial 32GB (2x16) DDR5-5600 SO-DIMM", "ram",
       "Crucial", 102.0, 0.92, 32, "SO-DIMM", "DDR5-5600 CL46"),
    _p("ram-ddr4-32-3200c16", "Corsair Vengeance LPX 32GB (2x16) DDR4-3200 CL16", "ram",
       "Corsair", 58.0, 0.80, 32, "DIMM", "DDR4-3200 CL16"),
    _p("ram-ddr4-16-3600c18", "G.Skill Ripjaws V 16GB (2x8) DDR4-3600 CL18", "ram",
       "G.Skill", 34.0, 0.78, 16, "DIMM", "DDR4-3600 CL18"),

    # ---------------- GPU -------------------------------------------------
    _p("gpu-rtx5090", "NVIDIA GeForce RTX 5090 32GB", "gpu",
       "NVIDIA", 2149.0, 1.90, 32, "Triple-slot", "GDDR7 512-bit"),
    _p("gpu-rtx5080", "NVIDIA GeForce RTX 5080 16GB", "gpu",
       "NVIDIA", 1199.0, 0.48, 16, "Triple-slot", "GDDR7 256-bit"),
    _p("gpu-rtx5070ti", "NVIDIA GeForce RTX 5070 Ti 16GB", "gpu",
       "NVIDIA", 819.0, 0.70, 16, "Triple-slot", "GDDR7 256-bit"),
    _p("gpu-rtx5070", "NVIDIA GeForce RTX 5070 12GB", "gpu",
       "NVIDIA", 589.0, 0.62, 12, "Dual-slot", "GDDR7 192-bit"),
    _p("gpu-rtx5060ti16", "NVIDIA GeForce RTX 5060 Ti 16GB", "gpu",
       "NVIDIA", 449.0, 0.86, 16, "Dual-slot", "GDDR7 128-bit"),
    _p("gpu-rx9070xt", "AMD Radeon RX 9070 XT 16GB", "gpu",
       "AMD", 649.0, 0.90, 16, "Triple-slot", "GDDR6 256-bit"),
    _p("gpu-rx9060xt16", "AMD Radeon RX 9060 XT 16GB", "gpu",
       "AMD", 379.0, 0.82, 16, "Dual-slot", "GDDR6 128-bit"),
    _p("gpu-arcb580", "Intel Arc B580 12GB", "gpu",
       "Intel", 289.0, 0.75, 12, "Dual-slot", "GDDR6 192-bit"),

    # ---------------- SATA SSD -------------------------------------------
    _p("sata-870evo-1tb", "Samsung 870 EVO 1TB", "sata_ssd",
       "Samsung", 69.0, 0.95, 1000, '2.5"', "SATA III TLC"),
    _p("sata-870evo-2tb", "Samsung 870 EVO 2TB", "sata_ssd",
       "Samsung", 124.0, 1.00, 2000, '2.5"', "SATA III TLC"),
    _p("sata-870qvo-4tb", "Samsung 870 QVO 4TB", "sata_ssd",
       "Samsung", 209.0, 1.12, 4000, '2.5"', "SATA III QLC"),
    _p("sata-mx500-1tb", "Crucial MX500 1TB", "sata_ssd",
       "Crucial", 59.0, 0.92, 1000, '2.5"', "SATA III TLC"),
    _p("sata-wdblue-2tb", "WD Blue SA510 2TB", "sata_ssd",
       "Western Digital", 112.0, 0.98, 2000, '2.5"', "SATA III TLC"),
    _p("sata-a400-480gb", "Kingston A400 480GB", "sata_ssd",
       "Kingston", 29.0, 0.88, 480, '2.5"', "SATA III TLC"),

    # ---------------- NVMe ------------------------------------------------
    _p("nvme-sn850x-1tb", "WD Black SN850X 1TB", "nvme_ssd",
       "Western Digital", 74.0, 1.00, 1000, "M.2 2280", "PCIe 4.0 x4"),
    _p("nvme-sn850x-2tb", "WD Black SN850X 2TB", "nvme_ssd",
       "Western Digital", 129.0, 1.05, 2000, "M.2 2280", "PCIe 4.0 x4"),
    _p("nvme-990pro-2tb", "Samsung 990 PRO 2TB", "nvme_ssd",
       "Samsung", 149.0, 1.02, 2000, "M.2 2280", "PCIe 4.0 x4"),
    _p("nvme-990pro-4tb", "Samsung 990 PRO 4TB", "nvme_ssd",
       "Samsung", 289.0, 1.15, 4000, "M.2 2280", "PCIe 4.0 x4"),
    _p("nvme-t700-2tb", "Crucial T700 2TB", "nvme_ssd",
       "Crucial", 199.0, 0.88, 2000, "M.2 2280", "PCIe 5.0 x4"),
    _p("nvme-p3plus-1tb", "Crucial P3 Plus 1TB", "nvme_ssd",
       "Crucial", 52.0, 1.18, 1000, "M.2 2280", "PCIe 4.0 x4"),
    _p("nvme-kc3000-1tb", "Kingston KC3000 1TB", "nvme_ssd",
       "Kingston", 69.0, 1.04, 1000, "M.2 2280", "PCIe 4.0 x4"),
    _p("nvme-firecuda530-4tb", "Seagate FireCuda 530R 4TB", "nvme_ssd",
       "Seagate", 319.0, 1.10, 4000, "M.2 2280", "PCIe 4.0 x4"),
]

DEFAULT_WATCHLIST = [
    "ram-ddr5-32-6000c30",
    "nvme-sn850x-2tb",
    "gpu-rtx5070",
    "sata-870evo-2tb",
]


def by_category(category: str) -> List[dict]:
    return [p for p in CATALOG if p["category"] == category]
