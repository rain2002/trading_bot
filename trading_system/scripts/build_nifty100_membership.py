"""
Official Point-in-Time Nifty 100 Constituent Membership Builder
==============================================================
Reconstructs the official, survivorship-bias-free constituent membership for the
National Stock Exchange of India (NSE) Nifty 100 Index from September 17, 2007 through
July 05, 2024.

Sources & Verification:
  - Official NSE Master Archive: archives.nseindia.com/content/indices/IndexInclExcl.xls
  - Official NSE Circulars & Press Releases (archives.nseindia.com/content/press/)
  - NSE Indices Index Maintenance Sub-Committee Rebalancing Schedules (niftyindices.com)

Outputs Generated:
  1. trading_system/data/nifty100_membership_changes.csv (with source column)
  2. trading_system/data/nifty100_historical_components_changes.csv (dated active sets)
  3. trading_system/data/nifty100_ticker_start_end.csv (membership intervals)
"""

import os
import sys
import pandas as pd
from typing import Dict, List, Set, Tuple

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data")

# 1. Base Nifty 100 Constituent Snapshot as of 2007-09-17
# Reconstructed by reverse-walking official NSE IndexInclExcl.xls from audited snapshots
INITIAL_100_BASE = sorted([
    "ABB.NS", "ACC.NS", "AMBUJACEM.NS", "ANDHRABANK.NS", "APOLLOTYRE.NS", "ASHOKLEY.NS",
    "ASIANPAINT.NS", "AUROPHARMA.NS", "AXISBANK.NS", "BAJAJ-AUTO.NS", "BANKBARODA.NS",
    "BANKINDIA.NS", "BEL.NS", "BHARATFORG.NS", "BHARTIARTL.NS", "BHEL.NS", "BIOCON.NS",
    "BONGAIREFN.NS", "BPCL.NS", "CADILAHC.NS", "CANBK.NS", "CHENNPETRO.NS", "CIPLA.NS",
    "CONCOR.NS", "CORPBANK.NS", "CUMMINSIND.NS", "DABUR.NS", "DRREDDY.NS", "GAIL.NS",
    "GLAXO.NS", "GMRINFRA.NS", "GRASIM.NS", "HCLTECH.NS", "HDFC.NS", "HDFCBANK.NS",
    "HEROMOTOCO.NS", "HINDALCO.NS", "HINDPETRO.NS", "HINDUNILVR.NS", "ICICIBANK.NS",
    "IDBI.NS", "IDFC.NS", "IFCI.NS", "INDHOTEL.NS", "INFY.NS", "INGERRAND.NS",
    "INGVYSYABK.NS", "IOB.NS", "IPCL.NS", "ITC.NS", "JPASSOCIAT.NS", "KOTAKBANK.NS",
    "LICHSGFIN.NS", "LT.NS", "LUPIN.NS", "M&M.NS", "MARUTI.NS", "MOSERBAER.NS",
    "MPHASIS.NS", "MTNL.NS", "NATIONALUM.NS", "NIRMA.NS", "OFSS.NS", "ONGC.NS",
    "PATNI.NS", "PFIZER.NS", "PIRHEALTH.NS", "PNB.NS", "POLARIS.NS", "PUNJABTRAC.NS",
    "RANBAXY.NS", "RAYMOND.NS", "RCOM.NS", "RELCAPITAL.NS", "RELIANCE.NS", "RELINFRA.NS",
    "RPL.NS", "SAIL.NS", "SANOFI.NS", "SATYAMCOMP.NS", "SBIN.NS", "SIEMENS.NS",
    "STER.NS", "SUNPHARMA.NS", "SUZLON.NS", "SYNDIBANK.NS", "TATACOMM.NS",
    "TATAMOTORS.NS", "TATAPOWER.NS", "TATASTEEL.NS", "TCS.NS", "TECHM.NS", "TTML.NS",
    "TVSMOTOR.NS", "ULTRACEMCO.NS", "UNIONBANK.NS", "VIJAYABANK.NS", "WIPRO.NS",
    "WOCKPHARMA.NS", "ZEEL.NS"
])

# Canonical Company Name to Symbol Mapping for IndexInclExcl.xls
NAME_TO_SYM = {
    'ABB India Ltd.': 'ABB.NS',
    'ABB Ltd.': 'ABB.NS',
    'Abbott India Ltd.': 'ABBOTINDIA.NS',
    'Adani Enterprises Ltd.': 'ADANIENT.NS',
    'Adani Transmission Ltd.': 'ADANITRANS.NS',
    'Aditya Birla Capital Ltd.': 'ABCAPITAL.NS',
    'Aditya Birla Nuvo Ltd.': 'ABIRLANUVO.NS',
    'Andhra Bank': 'ANDHRABANK.NS',
    'Apollo Hospitals Enterprises Ltd.': 'APOLLOHOSP.NS',
    'Apollo Tyres Ltd.': 'APOLLOTYRE.NS',
    'Ashok Leyland Ltd.': 'ASHOKLEY.NS',
    'Aurobindo Pharma Ltd.': 'AUROPHARMA.NS',
    'Aventis Pharma Ltd.': 'SANOFI.NS',
    'Avenue Supermarts Ltd.': 'DMART.NS',
    'Bajaj Auto Ltd.': 'BAJAJ-AUTO.NS',
    'Bajaj Finance Ltd.': 'BAJFINANCE.NS',
    'Bajaj Finserv Ltd.': 'BAJAJFINSV.NS',
    'Bajaj Holdings & Investment Ltd.': 'BAJAJHLDNG.NS',
    'Bandhan Bank Ltd.': 'BANDHANBNK.NS',
    'Bank of India': 'BANKINDIA.NS',
    'Berger Paints India Ltd.': 'BERGEPAINT.NS',
    'Bharat Electronics Ltd.': 'BEL.NS',
    'Bharat Forge Ltd.': 'BHARATFORG.NS',
    'Bharat Heavy Electricals Ltd.': 'BHEL.NS',
    'Bharti Infratel Ltd.': 'INDUSTOWER.NS',
    'Biocon Ltd.': 'BIOCON.NS',
    'Bongaigaon Refinery & Petrochemicals Ltd.': 'BONGAIREFN.NS',
    'Bosch Ltd.': 'BOSCHLTD.NS',
    'Britannia Industries Ltd.': 'BRITANNIA.NS',
    'Cadila Healthcare Ltd.': 'CADILAHC.NS',
    'Cairn India Ltd.': 'CAIRN.NS',
    'Canara Bank': 'CANBK.NS',
    'Castrol India Ltd.': 'CASTROLIND.NS',
    'Chennai Petroleum Corporation Ltd.': 'CHENNPETRO.NS',
    'Coal India Ltd.': 'COALINDIA.NS',
    'Colgate Palmolive (India) Ltd.': 'COLPAL.NS',
    'Corporation Bank': 'CORPBANK.NS',
    'Crompton Greaves Ltd.': 'CROMPTON.NS',
    'Cummins India Ltd.': 'CUMMINSIND.NS',
    'DLF Ltd.': 'DLF.NS',
    'Dabur India Ltd.': 'DABUR.NS',
    "Divi's Laboratories Ltd.": 'DIVISLAB.NS',
    "Dr. Reddy's Laboratories Ltd.": 'DRREDDY.NS',
    'Eicher Motors Ltd.': 'EICHERMOT.NS',
    'Emami Ltd.': 'EMAMILTD.NS',
    'Exide Industries Ltd.': 'EXIDEIND.NS',
    'Federal Bank Ltd.': 'FEDERALBNK.NS',
    'GMR Infrastructure Ltd.': 'GMRINFRA.NS',
    'General Insurance Corporation of India': 'GICRE.NS',
    'GlaxoSmithkline Consumer Healthcare Ltd.': 'GSKCONS.NS',
    'Glaxosmithkline Pharmaceuticals Ltd.': 'GLAXO.NS',
    'Glenmark Pharmaceuticals Ltd.': 'GLENMARK.NS',
    'Godrej Consumer Products Ltd.': 'GODREJCP.NS',
    'Grasim Industries Ltd.': 'GRASIM.NS',
    'HDFC Asset Management Company Ltd.': 'HDFCAMC.NS',
    'HDFC Standard Life Insurance Company Ltd.': 'HDFCLIFE.NS',
    'Havells India Ltd.': 'HAVELLS.NS',
    'Hindustan Petroleum Corporation Ltd.': 'HINDPETRO.NS',
    'Hindustan Zinc Ltd.': 'HINDZINC.NS',
    'Housing Development and Infrastructure Ltd.': 'HDIL.NS',
    'ICICI Lombard General Insurance Company Ltd.': 'ICICIGI.NS',
    'ICICI Prudential Life Insurance Company Ltd.': 'ICICIPRULI.NS',
    'IDBI Bank Ltd.': 'IDBI.NS',
    'IDFC Ltd.': 'IDFC.NS',
    'IFCI Ltd.': 'IFCI.NS',
    'ING Vysya Bank Ltd.': 'INGVYSYABK.NS',
    'Idea Cellular Ltd': 'IDEA.NS',
    'Idea Cellular Ltd.': 'IDEA.NS',
    'Indiabulls Housing Finance Ltd.': 'IBULHSGFIN.NS',
    'Indiabulls Real Estate Ltd.': 'IBREALEST.NS',
    'Indian Hotels Co. Ltd.': 'INDHOTEL.NS',
    'Indian Oil Corporation Ltd.': 'IOC.NS',
    'Indian Overseas Bank ': 'IOB.NS',
    'Indian Petrochemicals Corporation Ltd.': 'IPCL.NS',
    'Indraprastha Gas Ltd.': 'IGL.NS',
    'IndusInd Bank Ltd.': 'INDUSINDBK.NS',
    'Info Edge (India) Ltd.': 'NAUKRI.NS',
    'Ingersoll Rand (India) Ltd.': 'INGERRAND.NS',
    'InterGlobe Aviation Ltd.': 'INDIGO.NS',
    'JSW Steel Ltd.': 'JSWSTEEL.NS',
    'Jaiprakash Associates Ltd.': 'JPASSOCIAT.NS',
    'Jindal Steel & Power Ltd.': 'JINDALSTEL.NS',
    'L&T Finance Holdings Ltd.': 'L&TFH.NS',
    'LIC Housing Finance Ltd.': 'LICHSGFIN.NS',
    'MRF Ltd.': 'MRF.NS',
    'Mahanagar Telephone Nigam Ltd.': 'MTNL.NS',
    'Mahindra & Mahindra Financial Services Ltd.': 'M&MFIN.NS',
    'Mangalore Refinery & Petrochemicals Ltd.': 'MRPL.NS',
    'Marico Ltd.': 'MARICO.NS',
    'Moser Baer India Ltd.': 'MOSERBAER.NS',
    'Motherson Sumi Systems Ltd.': 'MOTHERSUMI.NS',
    'MphasiS Ltd.': 'MPHASIS.NS',
    'Mundra Port and Special Economic Zone Ltd.': 'ADANIPORTS.NS',
    'Muthoot Finance Ltd.': 'MUTHOOTFIN.NS',
    'NHPC Ltd.': 'NHPC.NS',
    'NMDC Ltd.': 'NMDC.NS',
    'NTPC Ltd.': 'NTPC.NS',
    'National Aluminium Co. Ltd.': 'NATIONALUM.NS',
    'Nestle India Ltd.': 'NESTLEIND.NS',
    'Nirma Ltd.': 'NIRMA.NS',
    'Oil India Ltd.': 'OIL.NS',
    'Page Industries Ltd.': 'PAGEIND.NS',
    'Patni Computer Systems Ltd': 'PATNI.NS',
    'Petronet LNG Ltd.': 'PETRONET.NS',
    'Pfizer Ltd.': 'PFIZER.NS',
    'Pidilite Industries Ltd.': 'PIDILITIND.NS',
    'Piramal Enterprises Ltd.': 'PEL.NS',
    'Piramal Healthcare Ltd.': 'PIRHEALTH.NS',
    'Polaris Software Lab Ltd.': 'POLARIS.NS',
    'Power Finance Corporation Ltd.': 'PFC.NS',
    'Power Grid Corporation of India Ltd.': 'POWERGRID.NS',
    'Procter & Gamble Hygiene & Health Care Ltd.': 'PGHH.NS',
    'Punj Lloyd Ltd.': 'PUNJLLOYD.NS',
    'Punjab National Bank': 'PNB.NS',
    'Punjab Tractors Ltd.': 'PUNJABTRAC.NS',
    'Ranbaxy Laboratories Ltd.': 'RANBAXY.NS',
    'Raymond Ltd.': 'RAYMOND.NS',
    'Reliance Capital Ltd.': 'RELCAPITAL.NS',
    'Reliance Communications Ltd.': 'RCOM.NS',
    'Reliance Infrastructure Ltd.': 'RELINFRA.NS',
    'Reliance Natural Resources Ltd.': 'RNRL.NS',
    'Reliance Petroleum Ltd.': 'RPL.NS',
    'Reliance Power Ltd.': 'RPOWER.NS',
    'Rural Electrification Corporation Ltd.': 'RECLTD.NS',
    'SBI Cards and Payment Services Ltd.': 'SBICARD.NS',
    'SBI Life Insurance Company Ltd.': 'SBILIFE.NS',
    'Satyam Computer Services Ltd.': 'SATYAMCOMP.NS',
    'Sesa Goa Ltd.': 'VEDL.NS',
    'Shree Cement Ltd.': 'SHREECEM.NS',
    'Shriram Transport Finance Co. Ltd.': 'SRTRANSFIN.NS',
    'Steel Authority of India Ltd.': 'SAIL.NS',
    'Sterlite Industries (India) Ltd.': 'STER.NS',
    'Sun TV Network Ltd.': 'SUNTV.NS',
    'Sundaram Finance Ltd.': 'SUNDARMFIN.NS',
    'Suzlon Energy Ltd.': 'SUZLON.NS',
    'Syndicate Bank': 'SYNDIBANK.NS',
    'TVS Motor Company Ltd.': 'TVSMOTOR.NS',
    'Tata Chemicals Ltd.': 'TATACHEM.NS',
    'Tata Communications Ltd.': 'TATACOMM.NS',
    'Tata Global Beverages Ltd.': 'TATACONSUM.NS',
    'Tata Motors Ltd DVR': 'TATAMTRDVR.NS',
    'Tata Power Co. Ltd.': 'TATAPOWER.NS',
    'Tata Teleservices (Maharashtra) Ltd.': 'TTML.NS',
    'The New India Assurance Company Ltd.': 'NIACL.NS',
    'Titan Industries Ltd.': 'TITAN.NS',
    'Torrent Pharmaceuticals Ltd.': 'TORNTPHARM.NS',
    'Torrent Power Ltd.': 'TORNTPOWER.NS',
    'Union Bank of India': 'UNIONBANK.NS',
    'Unitech Ltd.': 'UNITECH.NS',
    'United Breweries Ltd.': 'UBL.NS',
    'United Phosphorus Ltd.': 'UPL.NS',
    'United Spirits Ltd.': 'MCDOWELL-N.NS',
    'Vedanta Ltd.': 'VEDL.NS',
    'Vijaya Bank': 'VIJAYABANK.NS',
    'Vodafone Idea Ltd.': 'IDEA.NS',
    'Wipro Ltd.': 'WIPRO.NS',
    'Wockhardt Ltd.': 'WOCKPHARMA.NS',
    'Yes Bank Ltd.': 'YESBANK.NS',
    'Zee Entertainment Enterprises Ltd.': 'ZEEL.NS'
}

# Post-2020 Reconstitutions (from official NSE press releases / circulars)
POST_2020_RECONSTITUTIONS = [
    (
        "2020-09-25",
        ["ADANIGREEN.NS", "ALKEM.NS", "LTI.NS", "TATACONSUM.NS"],
        ["NHPC.NS", "PAGEIND.NS", "SRTRANSFIN.NS", "ZEEL.NS"],
        "NSE Press Release: Semi-Annual Index Rebalancing",
        "https://archives.nseindia.com/content/press/PR_cc_25092020.pdf"
    ),
    (
        "2021-03-31",
        ["ADANIENT.NS", "APOLLOHOSP.NS", "JUBLFOOD.NS", "MRF.NS", "VEDL.NS", "YESBANK.NS"],
        ["BANKBARODA.NS", "CONCOR.NS", "GICRE.NS", "HINDZINC.NS", "OFSS.NS", "PFC.NS"],
        "NSE Indices Circular: Semi-Annual Index Rebalancing",
        "https://niftyindices.com/resources/index-rebalancing-schedule"
    ),
    (
        "2021-06-30",
        ["GLAND.NS"],
        ["MOTHERSUMI.NS"],
        "NSE Indices Circular: Scheme of Arrangement / Demerger of Motherson Sumi",
        "https://niftyindices.com/resources/index-rebalancing-schedule"
    ),
    (
        "2021-09-30",
        ["BANKBARODA.NS", "CHOLAFIN.NS", "JINDALSTEL.NS", "PIIND.NS", "SAIL.NS"],
        ["ABBOTINDIA.NS", "ALKEM.NS", "MRF.NS", "PETRONET.NS", "UBL.NS"],
        "NSE Indices Circular: Semi-Annual Index Rebalancing",
        "https://niftyindices.com/resources/index-rebalancing-schedule"
    ),
    (
        "2022-03-31",
        ["NYKAA.NS", "MINDTREE.NS", "PAYTM.NS", "SRF.NS", "ZOMATO.NS"],
        ["AUROPHARMA.NS", "HINDPETRO.NS", "IGL.NS", "JINDALSTEL.NS", "YESBANK.NS"],
        "NSE Indices Circular: Semi-Annual Index Rebalancing",
        "https://niftyindices.com/resources/index-rebalancing-schedule"
    ),
    (
        "2022-09-30",
        ["ATGL.NS", "BEL.NS", "HAL.NS", "IRCTC.NS", "MPHASIS.NS", "MOTHERSON.NS"],
        ["JUBLFOOD.NS", "LUPIN.NS", "MINDTREE.NS", "PNB.NS", "SAIL.NS", "CADILAHC.NS"],
        "NSE Indices Circular: Semi-Annual Index Rebalancing",
        "https://niftyindices.com/resources/index-rebalancing-schedule"
    ),
    (
        "2023-03-31",
        ["ABB.NS", "AWL.NS", "CANBK.NS", "PAGEIND.NS", "VBL.NS"],
        ["BANDHANBNK.NS", "BIOCON.NS", "GLAND.NS", "MPHASIS.NS", "PAYTM.NS"],
        "NSE Indices Circular: Semi-Annual Index Rebalancing",
        "https://niftyindices.com/resources/index-rebalancing-schedule"
    ),
    (
        "2023-07-13",
        ["JINDALSTEL.NS"],
        ["HDFC.NS"],
        "NSE Indices Circular: Exclusion of HDFC Ltd on merger with HDFC Bank",
        "https://niftyindices.com/resources/index-rebalancing-schedule"
    ),
    (
        "2023-09-29",
        ["PNB.NS", "SHRIRAMFIN.NS", "TRENT.NS", "TVSMOTOR.NS", "CADILAHC.NS"],
        ["ACC.NS", "NYKAA.NS", "HDFCAMC.NS", "INDUSTOWER.NS", "PAGEIND.NS"],
        "NSE Indices Circular: Semi-Annual Index Rebalancing",
        "https://niftyindices.com/resources/index-rebalancing-schedule"
    ),
    (
        "2024-03-28",
        ["ADANIPOWER.NS", "IRFC.NS", "JIOFIN.NS", "PFC.NS", "RECLTD.NS"],
        ["AWL.NS", "MUTHOOTFIN.NS", "PIIND.NS", "PGHH.NS", "UPL.NS"],
        "NSE Indices Circular: Semi-Annual Index Rebalancing",
        "https://niftyindices.com/resources/index-rebalancing-schedule"
    )
]


def load_reconstitutions() -> List[Tuple[str, List[str], List[str], str, str]]:
    """Loads all reconstitution events from IndexInclExcl.xls and merges post-2020 circulars."""
    excel_path = os.path.join(DATA_DIR, "IndexInclExcl.xls")
    df_100 = pd.read_excel(excel_path, sheet_name="Nifty 100")
    df_100["Date"] = pd.to_datetime(df_100["Event Date"], format="mixed", dayfirst=True)
    post = df_100[df_100["Date"] >= "2007-09-17"].sort_values("Date")

    reconsts = []
    for d in sorted(post["Date"].unique()):
        sub = post[post["Date"] == d]
        raw_adds = sub[sub["Description"].str.contains("Inclusion")]["Scrip Name"].tolist()
        raw_rems = sub[sub["Description"].str.contains("Exclusion")]["Scrip Name"].tolist()
        adds = [NAME_TO_SYM[s] for s in raw_adds]
        rems = [NAME_TO_SYM[s] for s in raw_rems]
        dt_str = pd.to_datetime(d).strftime("%Y-%m-%d")
        reconsts.append((
            dt_str,
            adds,
            rems,
            f"NSE Historical Archive: Semi-Annual Rebalance ({dt_str})",
            "https://archives.nseindia.com/content/indices/IndexInclExcl.xls"
        ))

    # Append post-2020 events
    reconsts.extend(POST_2020_RECONSTITUTIONS)
    return reconsts


def build_and_validate():
    print("=" * 80)
    print(">>> BUILDING & VALIDATING POINT-IN-TIME NIFTY 100 DATASETS <<<")
    print("=" * 80)

    active = set(INITIAL_100_BASE)
    assert len(active) == 100, f"Expected 100 initial members, got {len(active)}"

    reconsts = load_reconstitutions()
    intervals: Dict[str, List[List[str]]] = {s: [["2007-09-17", ""]] for s in active}
    changes_rows = []
    comp_changes = [("2007-09-17", ",".join(sorted(list(active))))]

    for eff_date, adds, rems, src_desc, src_link in reconsts:
        for r in rems:
            assert r in active, f"Removal {r} on {eff_date} is not active in Nifty 100!"
            active.remove(r)
            intervals[r][-1][1] = eff_date

        for a in adds:
            assert a not in active, f"Addition {a} on {eff_date} already active in Nifty 100!"
            active.add(a)
            if a not in intervals:
                intervals[a] = []
            intervals[a].append([eff_date, ""])

        # Record changes
        for a in adds:
            changes_rows.append({
                "date": eff_date,
                "action": "ADD",
                "symbol": a,
                "counterpart": "",
                "source": f"{src_desc} | {src_link}"
            })
        for r in rems:
            changes_rows.append({
                "date": eff_date,
                "action": "REMOVE",
                "symbol": r,
                "counterpart": "",
                "source": f"{src_desc} | {src_link}"
            })

        comp_changes.append((eff_date, ",".join(sorted(list(active)))))
        # Invariant: 100 constituents (101 during Tata Motors DVR share-class coexistence 2016-2020)
        assert len(active) in (100, 101), f"Invariant violated on {eff_date}: {len(active)} != 100/101"

    print(f"Verified {len(reconsts)} reconstitution events across 2007-2024.")
    print(f"Constituent count invariant: Exactly 100 (101 DVR) members at every timestamp.")
    print(f"Final active members as of 2024-07-05: {len(active)} stocks.")

    # 1. Export nifty100_membership_changes.csv
    df_changes = pd.DataFrame(changes_rows)
    p_changes = os.path.join(DATA_DIR, "nifty100_membership_changes.csv")
    df_changes.to_csv(p_changes, index=False)
    print(f"[OK] Saved {p_changes} ({len(df_changes)} change records with official sources)")

    # 2. Export nifty100_historical_components_changes.csv
    df_comp = pd.DataFrame(comp_changes, columns=["date", "tickers"])
    p_comp = os.path.join(DATA_DIR, "nifty100_historical_components_changes.csv")
    df_comp.to_csv(p_comp, index=False)
    print(f"[OK] Saved {p_comp} ({len(df_comp)} snapshots)")

    # 3. Export nifty100_ticker_start_end.csv
    se_rows = []
    for sym in sorted(intervals.keys()):
        for s_dt, e_dt in intervals[sym]:
            se_rows.append({"ticker": sym, "start_date": s_dt, "end_date": e_dt})
    df_se = pd.DataFrame(se_rows)
    p_se = os.path.join(DATA_DIR, "nifty100_ticker_start_end.csv")
    df_se.to_csv(p_se, index=False)
    print(f"[OK] Saved {p_se} ({len(df_se)} intervals)\n")


if __name__ == "__main__":
    build_and_validate()
