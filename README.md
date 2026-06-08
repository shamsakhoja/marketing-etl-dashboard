# Marketing ETL & Dash Analytics Dashboard

## Project Overview

This project demonstrates an end-to-end data engineering and analytics workflow:

1. Extract marketing spend data from Google Ads.
2. Extract lead data from source files.
3. Perform data transformation and quality validation.
4. Load data into Supabase PostgreSQL.
5. Visualize business insights through an interactive Dash dashboard.

## Technology Stack

* Python
* Pandas
* SQLAlchemy
* Supabase PostgreSQL
* Dash
* Plotly

## Repository Structure

```text
dashboard/
etl/
sql/
docs/
diagrams/
presentation/
data/
```

## Running the ETL Pipeline

```bash
python etl/marketing_etl_week3_pipeline.py
```

## Running the Dashboard

```bash
python dashboard/app.py
```

## Business Insights

The dashboard provides:

* Lead volume by program
* Marketing spend by program
* Cost per Lead (CPL)
* Interactive filtering by source, year, and month

## Data Privacy

Raw source data, credentials, and environment files are excluded from the repository.
