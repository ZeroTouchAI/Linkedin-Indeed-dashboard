# Linkedin-Indeed-dashboard

Data center job dashboard (LinkedIn + Indeed, last 30 days), fed by the Make.com scrapers into a Google Sheet.

- `index.html` - the dashboard (single file, no build step)
- `scripts/refresh_data.py` - reads the sheet, keeps the last 30 days, dedupes by job URL, writes `data.json`
- `.github/workflows/refresh.yml` - rebuilds `data.json` on a schedule and deploys to GitHub Pages (data is not committed to git)

## One-time setup
1. Repo -> Settings -> Pages -> Source: **GitHub Actions**
2. Repo -> Settings -> Secrets and variables -> Actions, add:
   - `GCP_SERVICE_ACCOUNT_JSON` - service account key JSON
   - `JOBS_SHEET_ID` - `1K-K5eftIV1hficESS_RuTj0YXLymbktPYQUVpCZAmyA`
3. Share the Google Sheet (Viewer) with the service account's email.

Reject state is stored in your browser only.
