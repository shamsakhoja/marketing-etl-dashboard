import os
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

import dash
from dash import dcc, html, dash_table, Input, Output
import dash_bootstrap_components as dbc
import plotly.express as px

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)


def load_data():
    query = """
    WITH leads_agg AS (
        SELECT
            normalized_program AS program,
            source,
            reporting_year AS fiscal_year,
            reporting_month AS month,
            COUNT(lead_id) AS leads
        FROM leads
        GROUP BY normalized_program, source, reporting_year, reporting_month
    ),
    spend_agg AS (
        SELECT
            normalized_program AS program,
            source,
            reporting_year AS fiscal_year,
            reporting_month AS month,
            SUM(spend) AS spend
        FROM campaign_spend
        GROUP BY normalized_program, source, reporting_year, reporting_month
    )
    SELECT
        COALESCE(l.program, s.program) AS program,
        COALESCE(l.source, s.source) AS source,
        COALESCE(l.fiscal_year, s.fiscal_year) AS fiscal_year,
        COALESCE(l.month, s.month) AS month,
        COALESCE(l.leads, 0) AS leads,
        COALESCE(s.spend, 0) AS spend
    FROM leads_agg l
    FULL OUTER JOIN spend_agg s
        ON l.program = s.program
        AND l.source = s.source
        AND l.fiscal_year = s.fiscal_year
        AND l.month = s.month
    """
    return pd.read_sql(text(query), engine)


df = load_data()

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server
app.title = "COB Marketing Analytics Dashboard"

app.layout = dbc.Container([
    html.H2("COB Google Ads Performance Pulse", className="text-center mt-4 mb-4"),

    dbc.Row([
        dbc.Col(dcc.Dropdown(
            id="source_filter",
            options=[{"label": x, "value": x} for x in sorted(df["source"].dropna().unique())],
            value="Google" if "Google" in df["source"].unique() else None,
            placeholder="Select source"
        ), width=4),

        dbc.Col(dcc.Dropdown(
            id="year_filter",
            options=[{"label": x, "value": x} for x in sorted(df["fiscal_year"].dropna().unique())],
            value=2026 if 2026 in df["fiscal_year"].unique() else None,
            placeholder="Select fiscal year"
        ), width=4),

        dbc.Col(dcc.Dropdown(
            id="month_filter",
            options=[{"label": x, "value": x} for x in sorted(df["month"].dropna().unique())],
            value=None,
            placeholder="Select month"
        ), width=4),
    ], className="mb-4"),

    dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody([
            html.H5("Total Leads"),
            html.H2(id="total_leads")
        ])), width=4),

        dbc.Col(dbc.Card(dbc.CardBody([
            html.H5("Total Spend"),
            html.H2(id="total_spend")
        ])), width=4),

        dbc.Col(dbc.Card(dbc.CardBody([
            html.H5("Cost per Lead"),
            html.H2(id="cpl")
        ])), width=4),
    ], className="mb-4"),

    dbc.Row([
        dbc.Col(dcc.Graph(id="leads_by_program"), width=6),
        dbc.Col(dcc.Graph(id="spend_by_program"), width=6),
    ]),

    dbc.Row([
        dbc.Col(html.H4("Program Performance Table", className="mt-4")),
        dbc.Col(dash_table.DataTable(
            id="program_table",
            page_size=10,
            sort_action="native",
            style_table={"overflowX": "auto"},
            style_cell={"textAlign": "left", "padding": "8px"},
            style_header={"fontWeight": "bold"}
        ), width=12)
    ])
], fluid=True)


@app.callback(
    Output("total_leads", "children"),
    Output("total_spend", "children"),
    Output("cpl", "children"),
    Output("leads_by_program", "figure"),
    Output("spend_by_program", "figure"),
    Output("program_table", "data"),
    Output("program_table", "columns"),
    Input("source_filter", "value"),
    Input("year_filter", "value"),
    Input("month_filter", "value")
)
def update_dashboard(source, year, month):
    dff = df.copy()

    if source:
        dff = dff[dff["source"] == source]
    if year:
        dff = dff[dff["fiscal_year"] == year]
    if month:
        dff = dff[dff["month"] == month]

    total_leads = int(dff["leads"].sum())
    total_spend = float(dff["spend"].sum())
    cpl_value = total_spend / total_leads if total_leads > 0 else 0

    program_summary = (
        dff.groupby("program", as_index=False)
        .agg({"leads": "sum", "spend": "sum"})
    )
    program_summary["cpl"] = program_summary.apply(
        lambda row: row["spend"] / row["leads"] if row["leads"] > 0 else 0,
        axis=1
    )

    top_leads = program_summary.sort_values("leads", ascending=False).head(10)
    top_spend = program_summary.sort_values("spend", ascending=False).head(10)

    fig_leads = px.bar(
        top_leads,
        x="leads",
        y="program",
        orientation="h",
        title="Top Programs by Leads",
        labels={"leads": "Leads", "program": "Program"}
    )
    fig_leads.update_layout(yaxis={"categoryorder": "total ascending"})

    fig_spend = px.bar(
        top_spend,
        x="spend",
        y="program",
        orientation="h",
        title="Top Programs by Spend",
        labels={"spend": "Spend ($)", "program": "Program"}
    )
    fig_spend.update_layout(yaxis={"categoryorder": "total ascending"})

    table_df = program_summary.sort_values("leads", ascending=False)
    table_df["spend"] = table_df["spend"].round(2)
    table_df["cpl"] = table_df["cpl"].round(2)

    columns = [{"name": col.title(), "id": col} for col in table_df.columns]

    return (
        f"{total_leads:,}",
        f"${total_spend:,.0f}",
        f"${cpl_value:,.2f}",
        fig_leads,
        fig_spend,
        table_df.to_dict("records"),
        columns
    )


if __name__ == "__main__":
    app.run(debug=True)