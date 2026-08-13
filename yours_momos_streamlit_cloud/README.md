# Yours Momos — Streamlit Cloud Edition

This version uses a **remote PostgreSQL database**, so business data is not stored in the Streamlit Cloud app filesystem.

Streamlit's documentation explicitly warns that local file storage on Community Cloud is not guaranteed to persist, so this project uses PostgreSQL instead.

## Recommended setup

You can use a managed PostgreSQL provider such as Neon or Supabase.

### 1. Create PostgreSQL database

Create a PostgreSQL database and copy its connection string.

It should look similar to:

`postgresql+psycopg2://USERNAME:PASSWORD@HOST:5432/DATABASE`

### 2. Put the files in GitHub

Repository root:

```text
app.py
schema.sql
requirements.txt
README.md
.streamlit/
    secrets.toml.example
```

Do NOT upload a real `secrets.toml` to GitHub.

### 3. Configure Streamlit Cloud

Create the Streamlit app and use:

- Branch: main
- Main file: app.py

In Advanced Settings / Secrets, add:

```toml
[database]
url = "postgresql+psycopg2://USERNAME:PASSWORD@HOST:5432/DATABASE"
```

Streamlit Community Cloud supports storing secrets in the app settings, and secrets should not be committed to GitHub.

### 4. First launch

Open the deployed app.

It will create the required tables automatically and show:

"Create Owner Account"

Create your Owner account.

### Business date

The business date changes at 4:00 AM.

For example:

Friday 6 PM → Saturday 3:59 AM
= Friday Business Date

Saturday 4 AM onward
= Saturday Business Date

### Data persistence

Sales, expenses, menu quantities, rent, withdrawals, users and reports are stored in PostgreSQL.

Restarting/redeploying the Streamlit app does not intentionally recreate or erase the business database.

For real production use, also enable backups/point-in-time recovery at your database provider.

## Features

- Daily cash and online sales
- Total menu quantities
- No flavour-level momo tracking
- Normal expenses
- Bulk/weekly expense allocations
- Separate daily rent
- Owner withdrawals
- Profit before rent
- Profit after rent
- Cash movement
- Bank movement
- Daily/weekly/monthly reports
- Holiday/missed-day management
- Historical entry
- Owner/Staff login
- Audit log
- CSV report download
- Remote PostgreSQL persistence
