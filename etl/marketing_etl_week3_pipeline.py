import os
import logging
from datetime import datetime, date, timedelta

import pandas as pd
from sqlalchemy import create_engine, text
from google.ads.googleads.client import GoogleAdsClient


# -----------------------------
# CONFIGURATION
# -----------------------------

PROJECT_FOLDER = r"C:\Users\shams\marketing_etl_project"
LEADS_FILE = r"C:\Users\shams\Downloads\cleaned_data.xlsx"
HISTORIC_SPEND_FILE = r"C:\Users\shams\marketing_etl_project\Grad Programs Spend.xlsx"
GOOGLE_ADS_YAML = r"C:\Users\shams\marketing_etl_project\google-ads.yaml"

CUSTOMER_ID = "2694730081"

from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

MTD_SPEND_FILE = os.path.join(PROJECT_FOLDER, "mtd_campaign_spend.csv")
PROGRAM_SPEND_FILE = os.path.join(PROJECT_FOLDER, "program_spend_merge_ready.csv")
FINAL_OUTPUT_FILE = os.path.join(PROJECT_FOLDER, "final_leads_spend_summary.csv")


# -----------------------------
# LOGGING
# -----------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


# -----------------------------
# FISCAL YEAR LOGIC
# -----------------------------

def get_fiscal_year(date_value):
    """
    UofL fiscal year logic:
    July 2025 - June 2026 = Fiscal Year 2026
    July 2026 - June 2027 = Fiscal Year 2027
    """
    if date_value.month >= 7:
        return date_value.year + 1
    return date_value.year


def get_last_month_date():
    first_day_this_month = date.today().replace(day=1)
    last_day_previous_month = first_day_this_month - timedelta(days=1)
    return last_day_previous_month


# -----------------------------
# PROGRAM NORMALIZATION
# -----------------------------

program_map = {
    "MSBA": ["MSBA", "OMSBA", "MSBA online"],
    "IMBA": ["IMBA"],
    "Managerial Analytics": ["Managerial Analytics", "MAC"],
    "Healthcare Cert": ["Healthcare Cert", "Lean for Healthcare"],
    "Distilled Spirits Cert": ["Distilled Spirits"],
    "Franchise Cert": ["Franchise"],
    "Family Business Cert": ["Family Business"],
    "Equine Online Cert": ["Equine"],
    "Accounting Cert": ["Accounting"],
    "Executive Education": [
        "Exec Ed", "AI for Execs", "SuccessfulSupervisor",
        "Navigating Leadership", "Positive Leadership",
        "Six Sigma", "Goldratt", "Problem Solving",
        "Transformative Leadership"
    ],
    "MSAA": ["MSAA"],
    "Global MBA": ["Global MBA"],
    "PMP": ["PMP"],
    "Strategic Communication": ["Strat Comm"]
}


def extract_program(campaign_name):
    if pd.isna(campaign_name):
        return "UofL MBA"

    campaign_name = str(campaign_name).lower()

    for standard_program, keywords in program_map.items():
        for keyword in keywords:
            if keyword.lower() in campaign_name:
                return standard_program

    return "UofL MBA"


# -----------------------------
# EXTRACT
# -----------------------------

def extract_google_ads_period(ga_service, period_label, period_date):
    logger.info(f"Extracting Google Ads spend for {period_label}...")

    query = f"""
    SELECT
        campaign.name,
        metrics.cost_micros
    FROM campaign
    WHERE segments.date DURING {period_label}
    """

    response = ga_service.search(customer_id=CUSTOMER_ID, query=query)

    rows = []

    for row in response:
        rows.append({
            "campaign": row.campaign.name,
            "mtd_spend": row.metrics.cost_micros / 1_000_000,
            "reporting_year": get_fiscal_year(period_date),
            "reporting_month": period_date.strftime("%B"),
            "source": "Google",
            "period_label": period_label
        })

    return rows


def extract_google_ads_spend():
    logger.info("Extracting Google Ads spend from API...")

    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga_service = client.get_service("GoogleAdsService")

    today_date = date.today()
    last_month_date = get_last_month_date()

    data = []

    data.extend(
        extract_google_ads_period(
            ga_service,
            "THIS_MONTH",
            today_date
        )
    )

    data.extend(
        extract_google_ads_period(
            ga_service,
            "LAST_MONTH",
            last_month_date
        )
    )

    df = pd.DataFrame(data)

    # API response validation
    if df.empty:
        raise ValueError("Google Ads API returned zero rows.")

    required_api_columns = [
        "campaign",
        "mtd_spend",
        "reporting_year",
        "reporting_month",
        "source"
    ]

    missing_api_columns = [
        col for col in required_api_columns
        if col not in df.columns
    ]

    if missing_api_columns:
        raise ValueError(
            f"Google Ads API response missing columns: {missing_api_columns}"
        )

    logger.info("Google Ads API response validation passed.")

    df = df.sort_values(
        by=["reporting_year", "reporting_month", "mtd_spend"],
        ascending=[True, True, False]
    )

    df.to_csv(MTD_SPEND_FILE, index=False)

    logger.info(f"Google Ads spend exported: {MTD_SPEND_FILE}")
    logger.info(f"Google Ads extracted rows: {len(df)}")

    return df


def extract_files():
    logger.info("Reading cleaned leads and historic spend files...")

    leads_df = pd.read_excel(LEADS_FILE)
    historic_spend_df = pd.read_excel(HISTORIC_SPEND_FILE)

    leads_df.columns = leads_df.columns.str.strip()
    historic_spend_df.columns = historic_spend_df.columns.str.strip()

    return leads_df, historic_spend_df


# -----------------------------
# TRANSFORM
# -----------------------------

def create_program_spend_file(spend_df):
    logger.info("Normalizing Google Ads campaign names...")

    spend_df["Program"] = spend_df["campaign"].apply(extract_program)
    spend_df["Fiscal Year"] = spend_df["reporting_year"]
    spend_df["Month"] = spend_df["reporting_month"]
    spend_df["Source"] = spend_df["source"]

    program_summary = (
        spend_df
        .groupby(["Fiscal Year", "Month", "Program", "Source"], as_index=False)["mtd_spend"]
        .sum()
        .rename(columns={"mtd_spend": "Spend"})
    )

    program_summary["ID"] = (
        program_summary["Month"] + " " +
        program_summary["Fiscal Year"].astype(str) + " " +
        program_summary["Program"] + " " +
        program_summary["Source"]
    )

    program_summary = program_summary[
        ["Fiscal Year", "Month", "Program", "Source", "Spend", "ID"]
    ]

    program_summary.to_csv(PROGRAM_SPEND_FILE, index=False)

    logger.info(f"Program spend file created: {PROGRAM_SPEND_FILE}")
    logger.info(f"Program spend rows created: {len(program_summary)}")

    return program_summary


def remove_historic_rows_replaced_by_api(historic_spend_df, current_spend_df):
    key_cols = ["Fiscal Year", "Month", "Program", "Source"]

    api_keys = current_spend_df[key_cols].drop_duplicates()

    historic_with_flag = historic_spend_df.merge(
        api_keys,
        on=key_cols,
        how="left",
        indicator=True
    )

    cleaned_historic = (
        historic_with_flag[historic_with_flag["_merge"] == "left_only"]
        .drop(columns=["_merge"])
    )

    removed_count = len(historic_spend_df) - len(cleaned_historic)

    logger.info(
        f"Historic spend rows replaced by fresh Google API spend: {removed_count}"
    )

    return cleaned_historic


def transform_leads_and_spend(leads_df, historic_spend_df, current_spend_df):
    logger.info("Transforming leads and spend data...")

    leads_df["Submission Date"] = pd.to_datetime(
        leads_df["Submission Date"],
        errors="coerce"
    )

    leads_df["reporting_year"] = leads_df["Fiscal Year"]
    leads_df["reporting_month"] = leads_df["Submission Date"].dt.strftime("%B")
    leads_df["normalized_program"] = leads_df["Program"]

    leads_upload = leads_df[[
        "Submission Date",
        "reporting_year",
        "reporting_month",
        "Program",
        "normalized_program",
        "Source"
    ]].rename(columns={
        "Submission Date": "submission_date",
        "Program": "program",
        "Source": "source"
    })

    leads_summary = (
        leads_df
        .groupby(["Fiscal Year", "reporting_month", "Program", "Source"], as_index=False)
        .size()
        .rename(columns={
            "size": "Leads",
            "reporting_month": "Month"
        })
    )

    historic_spend_df = historic_spend_df[[
        "Fiscal Year",
        "Month",
        "Program",
        "Source",
        "Spend"
    ]]

    current_spend_df = current_spend_df[[
        "Fiscal Year",
        "Month",
        "Program",
        "Source",
        "Spend"
    ]]

    historic_spend_df = remove_historic_rows_replaced_by_api(
        historic_spend_df,
        current_spend_df
    )

    all_spend_df = pd.concat(
        [historic_spend_df, current_spend_df],
        ignore_index=True
    )

    spend_summary = (
        all_spend_df
        .groupby(["Fiscal Year", "Month", "Program", "Source"], as_index=False)["Spend"]
        .sum()
    )

    final_df = pd.merge(
        spend_summary,
        leads_summary,
        on=["Fiscal Year", "Month", "Program", "Source"],
        how="outer"
    )

    final_df["Spend"] = final_df["Spend"].fillna(0)
    final_df["Leads"] = final_df["Leads"].fillna(0).astype(int)

    final_df["CPL"] = final_df.apply(
        lambda row: row["Spend"] / row["Leads"] if row["Leads"] > 0 else 0,
        axis=1
    )

    campaign_spend_upload = spend_summary.copy()
    campaign_spend_upload["campaign_name"] = campaign_spend_upload["Program"]

    campaign_spend_upload = campaign_spend_upload.rename(columns={
        "Fiscal Year": "reporting_year",
        "Month": "reporting_month",
        "Program": "normalized_program",
        "Source": "source",
        "Spend": "spend"
    })

    campaign_spend_upload = campaign_spend_upload[[
        "campaign_name",
        "reporting_year",
        "reporting_month",
        "normalized_program",
        "source",
        "spend"
    ]]

    campaign_spend_upload = campaign_spend_upload.drop_duplicates(
        subset=[
            "campaign_name",
            "reporting_year",
            "reporting_month",
            "source"
        ]
    )

    final_df.to_csv(FINAL_OUTPUT_FILE, index=False)

    logger.info(f"Power BI-ready output created: {FINAL_OUTPUT_FILE}")
    logger.info(f"Campaign spend upload rows prepared: {len(campaign_spend_upload)}")

    return leads_upload, campaign_spend_upload, final_df


# -----------------------------
# DATA QUALITY CHECKS
# -----------------------------

def validate_dataframe(df, required_columns, name):
    logger.info(f"Running data quality checks for {name}...")

    missing_cols = [col for col in required_columns if col not in df.columns]
    if missing_cols:
        raise ValueError(f"{name} missing required columns: {missing_cols}")

    null_counts = df[required_columns].isnull().sum()
    if null_counts.sum() > 0:
        raise ValueError(f"{name} has nulls in required columns:\n{null_counts}")

    logger.info(f"{name} passed required column and null checks.")
    logger.info(f"{name} row count: {len(df)}")


def validate_data_types(campaign_spend_upload):
    logger.info("Running data type validation...")

    campaign_spend_upload["reporting_year"] = campaign_spend_upload["reporting_year"].astype(int)
    campaign_spend_upload["spend"] = campaign_spend_upload["spend"].astype(float)

    logger.info(f"reporting_year dtype: {campaign_spend_upload['reporting_year'].dtype}")
    logger.info(f"spend dtype: {campaign_spend_upload['spend'].dtype}")
    logger.info("Data type validation passed.")

    return campaign_spend_upload


def validate_referential_integrity(leads_upload, campaign_spend_upload):
    logger.info("Running referential integrity checks...")

    lead_programs = set(leads_upload["normalized_program"].dropna())
    spend_programs = set(campaign_spend_upload["normalized_program"].dropna())

    lead_sources = set(leads_upload["source"].dropna())
    spend_sources = set(campaign_spend_upload["source"].dropna())

    missing_programs = spend_programs - lead_programs
    missing_sources = spend_sources - lead_sources

    logger.info(f"Programs in spend not found in leads: {len(missing_programs)}")
    logger.info(f"Sources in spend not found in leads: {len(missing_sources)}")
    logger.info("Referential integrity validation completed.")


def run_quality_checks(leads_upload, campaign_spend_upload, final_df):
    validate_dataframe(
        leads_upload,
        [
            "submission_date",
            "reporting_year",
            "reporting_month",
            "program",
            "normalized_program",
            "source"
        ],
        "leads_upload"
    )

    validate_dataframe(
        campaign_spend_upload,
        [
            "campaign_name",
            "reporting_year",
            "reporting_month",
            "normalized_program",
            "source",
            "spend"
        ],
        "campaign_spend_upload"
    )

    campaign_spend_upload = validate_data_types(campaign_spend_upload)

    if (campaign_spend_upload["spend"] < 0).any():
        raise ValueError("campaign_spend_upload contains negative spend values.")

    duplicate_spend = campaign_spend_upload.duplicated(
        subset=[
            "campaign_name",
            "reporting_year",
            "reporting_month",
            "source"
        ]
    ).sum()

    if duplicate_spend > 0:
        raise ValueError(
            f"Duplicate campaign spend keys found in incoming file: {duplicate_spend}"
        )

    logger.info("Spend duplicate and range validation passed.")

    validate_referential_integrity(leads_upload, campaign_spend_upload)

    validate_dataframe(
        final_df,
        [
            "Fiscal Year",
            "Month",
            "Program",
            "Source",
            "Spend",
            "Leads",
            "CPL"
        ],
        "final_powerbi_output"
    )

    logger.info("All data quality checks completed.")


# -----------------------------
# DATABASE LOAD HELPERS
# -----------------------------

def load_new_dimension_values(engine, df, column_name, table_name):
    existing = pd.read_sql(f"SELECT {column_name} FROM {table_name}", engine)

    new_values = (
        df[[column_name]]
        .drop_duplicates()
        .dropna()
    )

    new_values = new_values[
        ~new_values[column_name].isin(existing[column_name])
    ]

    if len(new_values) > 0:
        new_values.to_sql(table_name, engine, if_exists="append", index=False)
        logger.info(f"Loaded {len(new_values)} new rows into {table_name}.")
    else:
        logger.info(f"No new rows to load into {table_name}.")


def load_incremental_leads(engine, leads_upload):
    logger.info("Loading leads incrementally...")

    leads_upload = leads_upload.copy()

    existing = pd.read_sql(
        """
        SELECT submission_date, program, normalized_program, source
        FROM leads
        """,
        engine
    )

    existing["submission_date"] = pd.to_datetime(existing["submission_date"])
    leads_upload["submission_date"] = pd.to_datetime(leads_upload["submission_date"])

    merged = leads_upload.merge(
        existing,
        on=[
            "submission_date",
            "program",
            "normalized_program",
            "source"
        ],
        how="left",
        indicator=True
    )

    new_leads = merged[merged["_merge"] == "left_only"].drop(columns=["_merge"])

    if len(new_leads) > 0:
        new_leads.to_sql("leads", engine, if_exists="append", index=False)

    logger.info(
        f"Incremental Load - Leads: "
        f"Incoming={len(leads_upload)}, "
        f"New={len(new_leads)}, "
        f"Skipped={len(leads_upload) - len(new_leads)}"
    )


def upsert_campaign_spend(engine, campaign_spend_upload):
    logger.info("Upserting campaign spend records...")

    existing = pd.read_sql(
        """
        SELECT
            campaign_name,
            reporting_year,
            reporting_month,
            source,
            spend
        FROM campaign_spend
        """,
        engine
    )

    key_cols = [
        "campaign_name",
        "reporting_year",
        "reporting_month",
        "source"
    ]

    merged = campaign_spend_upload.merge(
        existing,
        on=key_cols,
        how="left",
        suffixes=("", "_existing"),
        indicator=True
    )

    new_rows = merged[merged["_merge"] == "left_only"].copy()
    matched_rows = merged[merged["_merge"] == "both"].copy()

    changed_rows = matched_rows[
        matched_rows["spend"].round(2) != matched_rows["spend_existing"].round(2)
    ].copy()

    skipped_rows = matched_rows[
        matched_rows["spend"].round(2) == matched_rows["spend_existing"].round(2)
    ].copy()

    if len(new_rows) > 0:
        insert_cols = [
            "campaign_name",
            "reporting_year",
            "reporting_month",
            "normalized_program",
            "source",
            "spend"
        ]

        new_rows[insert_cols].to_sql(
            "campaign_spend",
            engine,
            if_exists="append",
            index=False
        )

    if len(changed_rows) > 0:
        with engine.begin() as conn:
            for _, row in changed_rows.iterrows():
                conn.execute(
                    text(
                        """
                        UPDATE campaign_spend
                        SET spend = :spend,
                            normalized_program = :normalized_program
                        WHERE campaign_name = :campaign_name
                          AND reporting_year = :reporting_year
                          AND reporting_month = :reporting_month
                          AND source = :source
                        """
                    ),
                    {
                        "spend": float(row["spend"]),
                        "normalized_program": row["normalized_program"],
                        "campaign_name": row["campaign_name"],
                        "reporting_year": int(row["reporting_year"]),
                        "reporting_month": row["reporting_month"],
                        "source": row["source"]
                    }
                )

    logger.info(
        f"Campaign Spend Upsert: "
        f"Incoming={len(campaign_spend_upload)}, "
        f"Inserted={len(new_rows)}, "
        f"Updated={len(changed_rows)}, "
        f"Skipped={len(skipped_rows)}"
    )


def load_to_database(leads_upload, campaign_spend_upload):
    logger.info("Connecting to Supabase PostgreSQL...")

    engine = create_engine(DATABASE_URL)

    program_values = pd.DataFrame({
        "normalized_program": pd.concat([
            leads_upload["normalized_program"],
            campaign_spend_upload["normalized_program"]
        ]).drop_duplicates()
    })

    source_values = pd.DataFrame({
        "source": pd.concat([
            leads_upload["source"],
            campaign_spend_upload["source"]
        ]).drop_duplicates()
    })

    load_new_dimension_values(
        engine,
        program_values,
        "normalized_program",
        "program_dim"
    )

    load_new_dimension_values(
        engine,
        source_values,
        "source",
        "source_dim"
    )

    load_incremental_leads(engine, leads_upload)
    upsert_campaign_spend(engine, campaign_spend_upload)

    logger.info("Database loading completed.")


# -----------------------------
# MAIN PIPELINE
# -----------------------------

def main():
    try:
        logger.info("Marketing ETL Week 3 pipeline started.")

        google_spend_df = extract_google_ads_spend()
        leads_df, historic_spend_df = extract_files()

        current_spend_df = create_program_spend_file(google_spend_df)

        leads_upload, campaign_spend_upload, final_df = transform_leads_and_spend(
            leads_df,
            historic_spend_df,
            current_spend_df
        )

        run_quality_checks(
            leads_upload,
            campaign_spend_upload,
            final_df
        )

        load_to_database(
            leads_upload,
            campaign_spend_upload
        )

        logger.info("Marketing ETL Week 3 pipeline completed successfully.")

    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        raise


if __name__ == "__main__":
    main()