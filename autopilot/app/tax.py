"""Canadian sales tax helpers.

Rates are per province and kept in one place so a rate change (like Nova
Scotia's HST drop to 14% on 2025-04-01) is a one-line edit. Amounts are
integer cents, rounded half-up per component, which is how CRA expects a
single invoice total to be presented.
"""
from dataclasses import dataclass
from typing import Optional

PROVINCE_PROFILES = {
    "QC": "qc_gst_qst",
    "ON": "on_hst",
    "NB": "nb_hst",
    "NL": "nl_hst",
    "NS": "ns_hst",
    "PE": "pe_hst",
    "BC": "bc_gst",
    "AB": "ab_gst",
    "SK": "sk_gst",
    "MB": "mb_gst",
    "YT": "yt_gst",
    "NT": "nt_gst",
    "NU": "nu_gst",
}

TAX_PROFILES = {
    "qc_gst_qst": [("GST", 0.05), ("QST", 0.09975)],
    "on_hst": [("HST", 0.13)],
    "nb_hst": [("HST", 0.15)],
    "nl_hst": [("HST", 0.15)],
    "ns_hst": [("HST", 0.14)],
    "pe_hst": [("HST", 0.15)],
    "bc_gst": [("GST", 0.05)],
    "ab_gst": [("GST", 0.05)],
    "sk_gst": [("GST", 0.05)],
    "mb_gst": [("GST", 0.05)],
    "yt_gst": [("GST", 0.05)],
    "nt_gst": [("GST", 0.05)],
    "nu_gst": [("GST", 0.05)],
    "none": [],
}

PROVINCE_TIMEZONES = {
    "QC": "America/Toronto",
    "ON": "America/Toronto",
    "NB": "America/Moncton",
    "NL": "America/St_Johns",
    "NS": "America/Halifax",
    "PE": "America/Halifax",
    "BC": "America/Vancouver",
    "AB": "America/Edmonton",
    "SK": "America/Regina",
    "MB": "America/Winnipeg",
    "YT": "America/Whitehorse",
    "NT": "America/Yellowknife",
    "NU": "America/Iqaluit",
}


@dataclass
class TaxResult:
    subtotal_cents: int
    tax_cents: int
    total_cents: int
    breakdown: list[dict]


def profile_for_province(province: Optional[str]) -> str:
    return PROVINCE_PROFILES.get((province or "QC").upper(), "qc_gst_qst")


def timezone_for_province(province: Optional[str]) -> str:
    return PROVINCE_TIMEZONES.get((province or "QC").upper(), "America/Toronto")


def compute_tax(
    subtotal_cents: int,
    tax_profile: str = "qc_gst_qst",
    enabled: bool = True,
    rates: Optional[dict] = None,
) -> TaxResult:
    """Compute tax components on a subtotal.

    `rates` may override the built-in profile, e.g. {"GST": 0.05, "QST": 0.09975}
    for a business whose accountant wants a specific treatment.
    """
    subtotal = max(int(subtotal_cents or 0), 0)
    if not enabled:
        return TaxResult(subtotal, 0, subtotal, [])

    components = (
        [(label, rates[label]) for label in ("GST", "QST", "HST") if label in rates]
        if rates
        else TAX_PROFILES.get(tax_profile, [])
    )

    breakdown = []
    total_tax = 0
    for label, rate in components:
        amount = int(subtotal * float(rate) + 0.5)  # half-up on cents
        total_tax += amount
        breakdown.append(
            {
                "label": label,
                "rate": round(float(rate), 5),
                "amount_cents": amount,
            }
        )

    return TaxResult(subtotal, total_tax, subtotal + total_tax, breakdown)
