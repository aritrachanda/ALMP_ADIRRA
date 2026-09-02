"""
create_test_db.py  –  Populate a DuckDB with realistic fake banking data.

Creates ten interrelated tables in a dedicated DuckDB file
(sources/duckdb/test_bank.duckdb, schema: src):

    src.counterparties          – 500 corporate/individual counterparties
    src.accounts                – 800 deposit/current accounts
    src.credit_facilities       – 300 credit facility umbrellas
    src.loans                   – 1500 loan instruments under facilities
    src.collateral              – 600 collateral items
    src.loan_collateral_map     – 1200 M:N links between loans and collateral
    src.guarantees              – 200 guarantee instruments
    src.transactions            – 5000 payment/disbursement events
    src.loan_counterparty_roles – 2500 role assignments (borrower, guarantor, etc.)
    src.derivatives             – 300 derivative contracts (IRS, FX, options, CDS)

Column names are intentionally readable / standard so they provide a
realistic mapping challenge against the cryptic BIRD/AnaCredit target.

Usage:
    python sources/loader/create_test_db.py
"""
from __future__ import annotations

import random
import string
import uuid
from datetime import date, timedelta
from pathlib import Path

import duckdb

TARGET_DB = Path(__file__).resolve().parent.parent / "duckdb" / "test_bank.duckdb"

# ---------------------------------------------------------------------------
# Fake-data helpers (stdlib only)
# ---------------------------------------------------------------------------

_COUNTRIES = ["DE", "FR", "FI", "NL", "SE", "NO", "DK", "IT", "ES", "AT"]
_CITIES = {
    "DE": ["Berlin", "Frankfurt", "Munich", "Hamburg"],
    "FR": ["Paris", "Lyon", "Marseille", "Toulouse"],
    "FI": ["Helsinki", "Tampere", "Espoo", "Oulu"],
    "NL": ["Amsterdam", "Rotterdam", "The Hague", "Utrecht"],
    "SE": ["Stockholm", "Gothenburg", "Malmö", "Uppsala"],
    "NO": ["Oslo", "Bergen", "Trondheim", "Stavanger"],
    "DK": ["Copenhagen", "Aarhus", "Odense", "Aalborg"],
    "IT": ["Rome", "Milan", "Naples", "Turin"],
    "ES": ["Madrid", "Barcelona", "Valencia", "Seville"],
    "AT": ["Vienna", "Graz", "Linz", "Salzburg"],
}
_SECTORS = ["S11", "S12", "S121", "S122", "S124", "S125", "S126", "S128", "S13", "S14"]
_LEGAL_FORMS = ["PLC", "LLC", "SA", "GmbH", "AG", "NV", "BV", "SAS", "SpA"]
_ENTITY_STATUS = ["Active", "Inactive", "Defaulted", "InLiquidation"]
_ENTITY_TYPES = ["Corporate", "SME", "Retail", "Financial", "PublicSector"]
_CREDIT_QUALITY = ["1", "2", "3", "4", "5", "6"]
_ACCOUNTING_CLASS = ["FVTPL", "FVOCI", "AmortisedCost"]
_CURRENCIES = ["EUR", "USD", "GBP", "CHF", "SEK", "NOK", "DKK"]
_COLLATERAL_TYPES = ["RealEstate", "FinancialAsset", "Guarantee", "CashDeposit", "Receivables"]
_ECONOMIC_ACTIVITIES = [
    "A01", "C10", "C20", "C26", "D35", "F41", "G47", "H49", "I55", "J62",
    "K64", "K65", "L68", "M70", "N77", "O84", "P85", "Q86", "R90", "S96",
]
_ACCOUNT_TYPES = ["CurrentAccount", "SavingsAccount", "TermDeposit", "CustodyAccount"]
_ACCOUNT_STATUS = ["Open", "Closed", "Dormant", "Frozen"]
_FACILITY_TYPES = ["Revolving", "TermLoan", "Overdraft", "TradeFinance", "ProjectFinance"]
_FACILITY_STATUS = ["Active", "Expired", "Cancelled", "Fully Drawn"]
_GUARANTEE_TYPES = ["BankGuarantee", "CorporateGuarantee", "GovernmentGuarantee", "PersonalGuarantee"]
_TX_TYPES = ["Disbursement", "Repayment", "InterestPayment", "FeePayment", "Prepayment", "WriteOff"]
_ROLE_TYPES = ["Borrower", "Guarantor", "Servicer", "Originator", "CoBorrower"]
_DERIVATIVE_TYPES = ["IRS", "FX_Forward", "CDS", "EquityOption", "CurrencySwap", "FRA"]
_FLOAT_INDICES = ["EURIBOR_3M", "EURIBOR_6M", "EURIBOR_12M", "SOFR", "SONIA", "STIBOR_3M"]
_UNDERLYINGS = ["EUR/USD", "EUR/GBP", "EUR/SEK", "EUR/NOK", "EUR/CHF",
                "STOXX600", "DAX", "OMX30", "CAC40", "FTSE100"]


def rnd_date(start: date, end: date) -> date:
    return start + timedelta(days=random.randint(0, (end - start).days))


def rnd_lei() -> str:
    """Random 20-char alphanumeric LEI-like code."""
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=20))


def rnd_national_id(country: str) -> str:
    return f"{country}-{random.randint(1000000, 9999999)}"


def rnd_amount(lo: float, hi: float) -> float:
    return round(random.uniform(lo, hi), 2)


def rnd_id() -> str:
    return str(uuid.uuid4())[:18].upper().replace("-", "")


# ---------------------------------------------------------------------------
# Data generation
# ---------------------------------------------------------------------------

def generate_counterparties(n: int = 500) -> list[dict]:
    rows = []
    for i in range(n):
        country = random.choice(_COUNTRIES)
        city = random.choice(_CITIES[country])
        entity_status = random.choice(_ENTITY_STATUS)
        status_date = rnd_date(date(2018, 1, 1), date(2024, 12, 31))
        is_defaulted = entity_status == "Defaulted"
        rows.append({
            "counterparty_id": rnd_id(),
            "name": f"Entity {i+1:04d} {random.choice(_LEGAL_FORMS)}",
            "lei": rnd_lei() if random.random() > 0.1 else None,
            "national_id": rnd_national_id(country),
            "country": country,
            "city": city,
            "street": f"{random.randint(1,200)} Main Street",
            "postal_code": f"{random.randint(10000,99999)}",
            "territorial_unit": f"{country}-{random.randint(1,9):02d}",
            "legal_form": random.choice(_LEGAL_FORMS),
            "institutional_sector": random.choice(_SECTORS),
            "entity_type": random.choice(_ENTITY_TYPES),
            "entity_status": entity_status,
            "status_date": status_date.isoformat(),
            "default_date": rnd_date(status_date, date(2025, 1, 1)).isoformat() if is_defaulted else None,
            "credit_quality": random.choice(_CREDIT_QUALITY),
            "economic_activity": random.choice(_ECONOMIC_ACTIVITIES),
            "annual_turnover": rnd_amount(500_000, 2_000_000_000) if random.random() > 0.05 else None,
            "balance_sheet_total": rnd_amount(1_000_000, 5_000_000_000) if random.random() > 0.05 else None,
            "num_employees": random.randint(1, 50_000) if random.random() > 0.1 else None,
            "enterprise_size": random.choice(["Micro", "Small", "Medium", "Large"]),
            "accounting_framework": random.choice(["IFRS", "GAAP", "FINREP"]),
            "is_public_body_controlled": random.choice([True, False, None]),
            "parent_entity_id": None,  # filled in second pass for ~20%
            "ultimate_parent_id": None,
        })

    # Wire up ~20% to a parent within the set
    ids = [r["counterparty_id"] for r in rows]
    for r in random.sample(rows, k=int(n * 0.2)):
        r["parent_entity_id"] = random.choice(ids)
        r["ultimate_parent_id"] = random.choice(ids)

    return rows


def generate_accounts(counterparty_ids: list[str], n: int = 800) -> list[dict]:
    rows = []
    for i in range(n):
        opening = rnd_date(date(2010, 1, 1), date(2024, 6, 30))
        acct_status = random.choice(_ACCOUNT_STATUS)
        rows.append({
            "account_id": rnd_id(),
            "counterparty_id": random.choice(counterparty_ids),
            "account_type": random.choice(_ACCOUNT_TYPES),
            "currency": random.choice(_CURRENCIES),
            "balance": rnd_amount(-50_000, 10_000_000),
            "opening_date": opening.isoformat(),
            "closing_date": rnd_date(opening, date(2025, 12, 31)).isoformat() if acct_status == "Closed" else None,
            "status": acct_status,
            "interest_rate": round(random.uniform(-0.5, 5.0), 4) if random.random() > 0.2 else None,
            "branch_code": f"BR-{random.randint(100, 999)}",
            "iban": f"{random.choice(_COUNTRIES)}{''.join(random.choices(string.digits, k=20))}",
        })
    return rows


def generate_credit_facilities(counterparty_ids: list[str], n: int = 300) -> list[dict]:
    rows = []
    for _ in range(n):
        start = rnd_date(date(2015, 1, 1), date(2023, 12, 31))
        expiry = start + timedelta(days=random.randint(365, 10 * 365))
        total_limit = rnd_amount(100_000, 200_000_000)
        rows.append({
            "facility_id": rnd_id(),
            "counterparty_id": random.choice(counterparty_ids),
            "facility_type": random.choice(_FACILITY_TYPES),
            "currency": random.choice(_CURRENCIES),
            "total_limit": total_limit,
            "available_limit": round(total_limit * random.uniform(0.0, 1.0), 2),
            "start_date": start.isoformat(),
            "expiry_date": expiry.isoformat(),
            "status": random.choice(_FACILITY_STATUS),
            "interest_rate_type": random.choice(["Fixed", "Floating", "Mixed"]),
            "purpose": random.choice(["WorkingCapital", "Investment", "RealEstate", "TradeFinance", "General"]),
        })
    return rows


def generate_loans(counterparty_ids: list[str], facility_ids: list[str], n: int = 1500) -> list[dict]:
    rows = []
    for _ in range(n):
        start = rnd_date(date(2015, 1, 1), date(2023, 12, 31))
        maturity = start + timedelta(days=random.randint(180, 5 * 365))
        currency = random.choice(_CURRENCIES)
        outstanding = rnd_amount(10_000, 50_000_000)
        rows.append({
            "loan_id": rnd_id(),
            "counterparty_id": random.choice(counterparty_ids),
            "facility_id": random.choice(facility_ids) if random.random() > 0.1 else None,
            "contract_id": rnd_id(),
            "currency": currency,
            "outstanding_nominal_amount": outstanding,
            "carrying_amount": round(outstanding * random.uniform(0.85, 1.0), 2),
            "accrued_interest": rnd_amount(0, outstanding * 0.05),
            "commitment_at_inception": rnd_amount(outstanding, outstanding * 1.5),
            "accumulated_impairment": rnd_amount(0, outstanding * 0.2) if random.random() > 0.6 else None,
            "accumulated_writeoffs": rnd_amount(0, outstanding * 0.1) if random.random() > 0.8 else None,
            "arrears": rnd_amount(0, outstanding * 0.1) if random.random() > 0.7 else None,
            "credit_quality": random.choice(_CREDIT_QUALITY),
            "accounting_classification": random.choice(_ACCOUNTING_CLASS),
            "prudential_portfolio": random.choice(["Banking", "Trading"]),
            "start_date": start.isoformat(),
            "maturity_date": maturity.isoformat(),
            "default_date": rnd_date(start, maturity).isoformat() if random.random() > 0.85 else None,
            "forbearance_date": rnd_date(start, maturity).isoformat() if random.random() > 0.9 else None,
            "project_finance": random.choice([True, False]),
            "recourse": random.choice(["Full", "Partial", "None"]),
            "is_syndicated": random.choice([True, False, None]),
        })
    return rows


def generate_collateral(n: int = 600) -> list[dict]:
    rows = []
    for _ in range(n):
        coll_type = random.choice(_COLLATERAL_TYPES)
        rows.append({
            "collateral_id": rnd_id(),
            "collateral_type": coll_type,
            "description": f"{coll_type} collateral item",
            "nominal_value": rnd_amount(10_000, 20_000_000),
            "fair_value": rnd_amount(10_000, 20_000_000),
            "currency": random.choice(_CURRENCIES),
            "valuation_date": rnd_date(date(2020, 1, 1), date(2025, 12, 31)).isoformat(),
            "country": random.choice(_COUNTRIES),
            "is_immovable": coll_type == "RealEstate",
            "maturity_date": rnd_date(date(2025, 1, 1), date(2035, 12, 31)).isoformat() if coll_type != "RealEstate" else None,
        })
    return rows


def generate_loan_collateral_map(loan_ids: list[str], collateral_ids: list[str], n: int = 1200) -> list[dict]:
    rows = []
    seen = set()
    for _ in range(n):
        loan_id = random.choice(loan_ids)
        coll_id = random.choice(collateral_ids)
        key = (loan_id, coll_id)
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "loan_id": loan_id,
            "collateral_id": coll_id,
            "allocated_amount": rnd_amount(5_000, 15_000_000),
            "allocation_date": rnd_date(date(2018, 1, 1), date(2025, 6, 30)).isoformat(),
        })
    return rows


def generate_guarantees(loan_ids: list[str], counterparty_ids: list[str], n: int = 200) -> list[dict]:
    rows = []
    for _ in range(n):
        start = rnd_date(date(2016, 1, 1), date(2024, 6, 30))
        rows.append({
            "guarantee_id": rnd_id(),
            "loan_id": random.choice(loan_ids),
            "guarantor_id": random.choice(counterparty_ids),
            "guarantee_type": random.choice(_GUARANTEE_TYPES),
            "amount": rnd_amount(50_000, 30_000_000),
            "currency": random.choice(_CURRENCIES),
            "start_date": start.isoformat(),
            "expiry_date": (start + timedelta(days=random.randint(365, 7 * 365))).isoformat(),
            "is_financial_collateral": random.choice([True, False]),
        })
    return rows


def generate_transactions(loan_ids: list[str], n: int = 5000) -> list[dict]:
    rows = []
    for _ in range(n):
        tx_date = rnd_date(date(2018, 1, 1), date(2025, 6, 30))
        rows.append({
            "transaction_id": rnd_id(),
            "loan_id": random.choice(loan_ids),
            "transaction_type": random.choice(_TX_TYPES),
            "amount": rnd_amount(100, 5_000_000),
            "currency": random.choice(_CURRENCIES),
            "transaction_date": tx_date.isoformat(),
            "value_date": (tx_date + timedelta(days=random.randint(0, 3))).isoformat(),
            "description": random.choice([
                "Scheduled payment", "Early repayment", "Interest accrual",
                "Fee charge", "Partial prepayment", "Write-off adjustment",
            ]),
        })
    return rows


def generate_loan_counterparty_roles(loan_ids: list[str], counterparty_ids: list[str], n: int = 2500) -> list[dict]:
    rows = []
    seen = set()
    for _ in range(n):
        loan_id = random.choice(loan_ids)
        cp_id = random.choice(counterparty_ids)
        role = random.choice(_ROLE_TYPES)
        key = (loan_id, cp_id, role)
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "loan_id": loan_id,
            "counterparty_id": cp_id,
            "role": role,
            "share_percent": round(random.uniform(1.0, 100.0), 2) if role in ("Borrower", "CoBorrower") else None,
            "effective_date": rnd_date(date(2015, 1, 1), date(2024, 12, 31)).isoformat(),
        })
    return rows


def generate_derivatives(counterparty_ids: list[str], n: int = 300) -> list[dict]:
    rows = []
    for _ in range(n):
        deriv_type = random.choice(_DERIVATIVE_TYPES)
        trade_date = rnd_date(date(2018, 1, 1), date(2024, 12, 31))
        maturity = trade_date + timedelta(days=random.randint(90, 10 * 365))
        notional = rnd_amount(100_000, 500_000_000)

        # Type-specific fields
        fixed_rate = round(random.uniform(0.5, 6.0), 4) if deriv_type in ("IRS", "CurrencySwap", "FRA") else None
        floating_index = random.choice(_FLOAT_INDICES) if deriv_type in ("IRS", "CurrencySwap", "FRA") else None
        underlying = random.choice(_UNDERLYINGS) if deriv_type in ("FX_Forward", "EquityOption", "CurrencySwap") else None
        strike_price = rnd_amount(0.5, 200.0) if deriv_type == "EquityOption" else None
        cds_reference = f"Entity {random.randint(1, 500):04d}" if deriv_type == "CDS" else None

        rows.append({
            "derivative_id": rnd_id(),
            "counterparty_id": random.choice(counterparty_ids),
            "derivative_type": deriv_type,
            "notional_amount": notional,
            "currency": random.choice(_CURRENCIES),
            "trade_date": trade_date.isoformat(),
            "maturity_date": maturity.isoformat(),
            "settlement_date": (maturity - timedelta(days=random.randint(0, 5))).isoformat(),
            "underlying": underlying,
            "fixed_rate": fixed_rate,
            "floating_rate_index": floating_index,
            "spread": round(random.uniform(-0.5, 2.0), 4) if floating_index else None,
            "strike_price": strike_price,
            "cds_reference_entity": cds_reference,
            "fair_value": rnd_amount(-notional * 0.1, notional * 0.1),
            "direction": random.choice(["Buy", "Sell"]),
            "is_hedge": random.choice([True, False]),
            "hedge_type": random.choice(["FairValue", "CashFlow", "NetInvestment", None]) if random.random() > 0.5 else None,
            "accounting_classification": random.choice(_ACCOUNTING_CLASS),
            "status": random.choice(["Active", "Matured", "Terminated", "Novated"]),
        })
    return rows


# ---------------------------------------------------------------------------
# DDL + load
# ---------------------------------------------------------------------------

DDL = """
CREATE SCHEMA IF NOT EXISTS src;

DROP TABLE IF EXISTS src.loan_counterparty_roles CASCADE;
DROP TABLE IF EXISTS src.transactions CASCADE;
DROP TABLE IF EXISTS src.guarantees CASCADE;
DROP TABLE IF EXISTS src.loan_collateral_map CASCADE;
DROP TABLE IF EXISTS src.loan_collateral CASCADE;
DROP TABLE IF EXISTS src.collateral CASCADE;
DROP TABLE IF EXISTS src.derivatives CASCADE;
DROP TABLE IF EXISTS src.loans CASCADE;
DROP TABLE IF EXISTS src.credit_facilities CASCADE;
DROP TABLE IF EXISTS src.accounts CASCADE;
DROP TABLE IF EXISTS src.counterparties CASCADE;

CREATE OR REPLACE TABLE src.counterparties (
    counterparty_id         VARCHAR PRIMARY KEY,
    name                    VARCHAR,
    lei                     VARCHAR,
    national_id             VARCHAR,
    country                 VARCHAR,
    city                    VARCHAR,
    street                  VARCHAR,
    postal_code             VARCHAR,
    territorial_unit        VARCHAR,
    legal_form              VARCHAR,
    institutional_sector    VARCHAR,
    entity_type             VARCHAR,
    entity_status           VARCHAR,
    status_date             DATE,
    default_date            DATE,
    credit_quality          VARCHAR,
    economic_activity       VARCHAR,
    annual_turnover         DOUBLE,
    balance_sheet_total     DOUBLE,
    num_employees           INTEGER,
    enterprise_size         VARCHAR,
    accounting_framework    VARCHAR,
    is_public_body_controlled BOOLEAN,
    parent_entity_id        VARCHAR,
    ultimate_parent_id      VARCHAR
);

CREATE OR REPLACE TABLE src.accounts (
    account_id      VARCHAR PRIMARY KEY,
    counterparty_id VARCHAR REFERENCES src.counterparties(counterparty_id),
    account_type    VARCHAR,
    currency        VARCHAR,
    balance         DOUBLE,
    opening_date    DATE,
    closing_date    DATE,
    status          VARCHAR,
    interest_rate   DOUBLE,
    branch_code     VARCHAR,
    iban            VARCHAR
);

CREATE OR REPLACE TABLE src.credit_facilities (
    facility_id         VARCHAR PRIMARY KEY,
    counterparty_id     VARCHAR REFERENCES src.counterparties(counterparty_id),
    facility_type       VARCHAR,
    currency            VARCHAR,
    total_limit         DOUBLE,
    available_limit     DOUBLE,
    start_date          DATE,
    expiry_date         DATE,
    status              VARCHAR,
    interest_rate_type  VARCHAR,
    purpose             VARCHAR
);

CREATE OR REPLACE TABLE src.loans (
    loan_id                     VARCHAR PRIMARY KEY,
    counterparty_id             VARCHAR REFERENCES src.counterparties(counterparty_id),
    facility_id                 VARCHAR REFERENCES src.credit_facilities(facility_id),
    contract_id                 VARCHAR,
    currency                    VARCHAR,
    outstanding_nominal_amount  DOUBLE,
    carrying_amount             DOUBLE,
    accrued_interest            DOUBLE,
    commitment_at_inception     DOUBLE,
    accumulated_impairment      DOUBLE,
    accumulated_writeoffs       DOUBLE,
    arrears                     DOUBLE,
    credit_quality              VARCHAR,
    accounting_classification   VARCHAR,
    prudential_portfolio        VARCHAR,
    start_date                  DATE,
    maturity_date               DATE,
    default_date                DATE,
    forbearance_date            DATE,
    project_finance             BOOLEAN,
    recourse                    VARCHAR,
    is_syndicated               BOOLEAN
);

CREATE OR REPLACE TABLE src.collateral (
    collateral_id   VARCHAR PRIMARY KEY,
    collateral_type VARCHAR,
    description     VARCHAR,
    nominal_value   DOUBLE,
    fair_value      DOUBLE,
    currency        VARCHAR,
    valuation_date  DATE,
    country         VARCHAR,
    is_immovable    BOOLEAN,
    maturity_date   DATE
);

CREATE OR REPLACE TABLE src.loan_collateral_map (
    loan_id             VARCHAR REFERENCES src.loans(loan_id),
    collateral_id       VARCHAR REFERENCES src.collateral(collateral_id),
    allocated_amount    DOUBLE,
    allocation_date     DATE,
    PRIMARY KEY (loan_id, collateral_id)
);

CREATE OR REPLACE TABLE src.guarantees (
    guarantee_id            VARCHAR PRIMARY KEY,
    loan_id                 VARCHAR REFERENCES src.loans(loan_id),
    guarantor_id            VARCHAR REFERENCES src.counterparties(counterparty_id),
    guarantee_type          VARCHAR,
    amount                  DOUBLE,
    currency                VARCHAR,
    start_date              DATE,
    expiry_date             DATE,
    is_financial_collateral BOOLEAN
);

CREATE OR REPLACE TABLE src.transactions (
    transaction_id      VARCHAR PRIMARY KEY,
    loan_id             VARCHAR REFERENCES src.loans(loan_id),
    transaction_type    VARCHAR,
    amount              DOUBLE,
    currency            VARCHAR,
    transaction_date    DATE,
    value_date          DATE,
    description         VARCHAR
);

CREATE OR REPLACE TABLE src.loan_counterparty_roles (
    loan_id             VARCHAR REFERENCES src.loans(loan_id),
    counterparty_id     VARCHAR REFERENCES src.counterparties(counterparty_id),
    role                VARCHAR,
    share_percent       DOUBLE,
    effective_date      DATE,
    PRIMARY KEY (loan_id, counterparty_id, role)
);

CREATE OR REPLACE TABLE src.derivatives (
    derivative_id               VARCHAR PRIMARY KEY,
    counterparty_id             VARCHAR REFERENCES src.counterparties(counterparty_id),
    derivative_type             VARCHAR,
    notional_amount             DOUBLE,
    currency                    VARCHAR,
    trade_date                  DATE,
    maturity_date               DATE,
    settlement_date             DATE,
    underlying                  VARCHAR,
    fixed_rate                  DOUBLE,
    floating_rate_index         VARCHAR,
    spread                      DOUBLE,
    strike_price                DOUBLE,
    cds_reference_entity        VARCHAR,
    fair_value                  DOUBLE,
    direction                   VARCHAR,
    is_hedge                    BOOLEAN,
    hedge_type                  VARCHAR,
    accounting_classification   VARCHAR,
    status                      VARCHAR
);
"""


def load_rows(conn: duckdb.DuckDBPyConnection, table: str, rows: list[dict]) -> None:
    if not rows:
        return
    cols = list(rows[0].keys())
    placeholders = ", ".join(["?"] * len(cols))
    col_list = ", ".join(cols)
    sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"
    conn.executemany(sql, [[r[c] for c in cols] for r in rows])


def main() -> None:
    TARGET_DB.parent.mkdir(parents=True, exist_ok=True)
    print(f"Target DB : {TARGET_DB}")

    counterparties = generate_counterparties(500)
    cp_ids = [r["counterparty_id"] for r in counterparties]

    accounts = generate_accounts(cp_ids, 800)
    facilities = generate_credit_facilities(cp_ids, 300)
    fac_ids = [r["facility_id"] for r in facilities]

    loans = generate_loans(cp_ids, fac_ids, 1500)
    loan_ids = [r["loan_id"] for r in loans]

    collateral = generate_collateral(600)
    coll_ids = [r["collateral_id"] for r in collateral]
    loan_coll_map = generate_loan_collateral_map(loan_ids, coll_ids, 1200)

    guarantees = generate_guarantees(loan_ids, cp_ids, 200)
    transactions = generate_transactions(loan_ids, 5000)
    roles = generate_loan_counterparty_roles(loan_ids, cp_ids, 2500)
    derivatives = generate_derivatives(cp_ids, 300)

    with duckdb.connect(str(TARGET_DB)) as conn:
        conn.execute(DDL)
        load_rows(conn, "src.counterparties", counterparties)
        load_rows(conn, "src.accounts", accounts)
        load_rows(conn, "src.credit_facilities", facilities)
        load_rows(conn, "src.loans", loans)
        load_rows(conn, "src.collateral", collateral)
        load_rows(conn, "src.loan_collateral_map", loan_coll_map)
        load_rows(conn, "src.guarantees", guarantees)
        load_rows(conn, "src.transactions", transactions)
        load_rows(conn, "src.loan_counterparty_roles", roles)
        load_rows(conn, "src.derivatives", derivatives)
        conn.commit()

    print(f"  src.counterparties          : {len(counterparties)} rows")
    print(f"  src.accounts                : {len(accounts)} rows")
    print(f"  src.credit_facilities       : {len(facilities)} rows")
    print(f"  src.loans                   : {len(loans)} rows")
    print(f"  src.collateral              : {len(collateral)} rows")
    print(f"  src.loan_collateral_map     : {len(loan_coll_map)} rows")
    print(f"  src.guarantees              : {len(guarantees)} rows")
    print(f"  src.transactions            : {len(transactions)} rows")
    print(f"  src.loan_counterparty_roles : {len(roles)} rows")
    print(f"  src.derivatives             : {len(derivatives)} rows")
    print("Done.")


if __name__ == "__main__":
    main()
