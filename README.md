# ⛏️ Mosra Energy — Executive Operations Dashboard

An interactive, multi-site executive dashboard built with **Streamlit**, **Plotly**, and **PostgreSQL**. Designed for real-time tracking, historical comparison, and operational efficiency analysis of coal mining, inventory sales, and equipment diesel consumption across **TRCM** and **IFCM** mining sites.

---

## 🌟 Key Features

* **Multi-Site Analytics (`TRCM` vs `IFCM`):** Side-by-side executive summary and dedicated detailed views for each operating site.
* **Flexible Comparison Modes:**
  * **WoW (Week vs. Week):** Direct period-over-period comparison against prior week metrics.
  * **MoM (Month-to-Date vs. Prior MTD):** Tracks cumulative monthly progress.
  * **YTD (Year-to-Date):** Aggregated metrics from the start of the current year.
  * **YoY (Year-over-Year):** Evaluates YTD performance against the prior year's period.
* **Mining Efficiency Matrix (Scatterplot Analysis):** Full-width **BCM Excavated vs. Coal Mined** scatterplot highlighting high stripping-ratio weeks in red to immediately surface low-efficiency operations.
* **Granular Equipment Fleet Telemetry:** Interactive, filterable, and downloadable table breakdown of diesel consumption by equipment ID and type.
* **Automated Weekly Report Ingestion:** Clean parsing pipeline to handle operational report PDFs and update core metrics via SQL upsert logic.

---

## 🏗️ Repository Architecture

```text
.
├── app.py                      # Main Streamlit application entry point
├── pages/
│   ├── 1_Dashboard.py          # Executive Operations Dashboard (KPIs, Charts, Scatterplots)
│   ├── 2_Data_Ingestion.py     # PDF report parser and database loader interface
│   └── ...
├── utils/
│   ├── db.py                   # PostgreSQL / Neon database connection & query execution helpers
│   └── parsers.py              # PDF extraction utilities for coal, BCM, and diesel reports
├── sql/
│   └── schema.sql              # PostgreSQL schema definition & migration scripts
├── requirements.txt            # Python dependencies
└── README.md                   # Project documentation
