# Mississippi Weather Desk

Production-grade automation that pulls free U.S. government weather data (NWS, SPC, WPC, NHC), analyzes it for all of Mississippi, and emails a long-form weather briefing 3x daily.

## Features

- **Comprehensive Coverage**: All 82 Mississippi counties organized into 8 regions
- **Multiple Data Sources**: NWS alerts/forecasts, SPC severe outlooks, WPC rainfall/flood outlooks, NHC tropical data
- **AI-Powered Summaries**: Long-form AP-style articles via OpenAI
- **Automated Delivery**: 3x daily emails (6:30 AM, 1:30 PM, 8:30 PM CT)
- **Graceful Degradation**: Partial data still produces useful briefings

## Quick Start

### 1. Clone and Install

```powershell
cd c:\Users\myers\OneDrive\Desktop\MississippiWeather
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configure Environment

Create a `.env` file:

```env
OPENAI_API_KEY=your-openai-api-key
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-app-password
EMAIL_FROM=your-email@gmail.com
EMAIL_TO=recipient@example.com
```

### 3. Run Locally

```powershell
python -m src.run --mode once
```

## Project Structure

```
MississippiWeather/
├── src/
│   ├── run.py           # Main orchestrator
│   ├── fetch_nws.py     # NWS API fetcher
│   ├── fetch_spc.py     # SPC outlooks
│   ├── fetch_wpc.py     # WPC rainfall/flood
│   ├── fetch_nhc.py     # NHC tropical
│   ├── geo.py           # Geospatial intersection
│   ├── analyze.py       # Build briefing JSON
│   ├── llm.py           # OpenAI article generation
│   ├── emailer.py       # SMTP email sender
│   └── models.py        # Data models
├── config/
│   ├── ms_counties.json # 82 counties with FIPS, coords, region
│   └── anchors.json     # 8 regional anchor points
├── data/
│   └── ms_counties.geojson  # County polygons
├── tests/               # Unit tests
├── .github/workflows/   # GitHub Actions
└── .env.example         # Environment template
```

## Data Sources

| Source | Endpoint | Data |
|--------|----------|------|
| NWS API | `api.weather.gov` | Active alerts, grid forecasts |
| SPC | NOAA MapServer | Day 1-3 severe outlooks |
| WPC | NOAA MapServer | ERO, QPF guidance |
| NHC | `nhc.noaa.gov` | Tropical systems JSON |

## Schedule (America/Chicago)

| Time | UTC | Email Subject |
|------|-----|---------------|
| 6:30 AM CT | 12:30 UTC | Morning |
| 1:30 PM CT | 19:30 UTC | Afternoon |
| 8:30 PM CT | 02:30 UTC+1 | Evening |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key for article generation |
| `SMTP_HOST` | SMTP server (default: smtp.gmail.com) |
| `SMTP_PORT` | SMTP port (default: 587) |
| `SMTP_USER` | SMTP username/email |
| `SMTP_PASS` | SMTP password or App Password |
| `EMAIL_FROM` | Sender email address |
| `EMAIL_TO` | Recipient email address |

## Testing

```powershell
python -m pytest tests/ -v
```

## Troubleshooting

**Email not sending?**
- Verify Gmail App Password (not your regular password)
- Ensure 2FA is enabled on Gmail account

**API errors?**
- NWS API rate limits: includes User-Agent for identification
- Check network connectivity

**Partial data?**
- System handles gracefully; check "Data Gaps" section in email
