from typing import Any
from collections import defaultdict
import httpx
from urllib.parse import quote
from mcp.server.fastmcp import FastMCP
from os import getenv

# Initialize FastMCP server
mcp = FastMCP("finance")

# Constants
FMP_API_BASE = "https://financialmodelingprep.com/api/v3"
API_KEY = getenv("API_KEY")

NEWS_API_BASE = "https://newsapi.org/v2"
NEWS_API_KEY = getenv("NEWS_API_KEY")

# Make calls
async def make_fmp_request(url: str) -> dict[str, Any] | None:
    """Make a request to the Financial Modeling Prep API with error handling."""
    headers = {
        "Accept": "application/json"
    }
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

async def make_news_request(url: str) -> dict[str, Any] | None:
    """Make a request to NewsAPI with error handling."""
    headers = {
        "Accept": "application/json"
    }
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, headers=headers, timeout=30.0)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return None
#helpers:
def extract_year(date_str: str) -> str:
    """Extract the year from an ISO date string."""
    return date_str.split("-")[0] if date_str else "Unknown"

# format functions
def format_company(company: dict) -> str:
    """Format a single company entry into a readable string."""
    return f"""
Ticker: {company.get("symbol", "Unknown")}
Name:   {company.get("companyName", "Unknown")}
Industry: {company.get("industry", "Unknown")}
"""

def format_financial_entry(entry: dict) -> str:
    """Turn one year’s income‐statement into a human‐readable block."""
    year = entry.get("calendarYear") or entry.get("date", "Unknown Year")
    revenue = entry.get("revenue", "N/A")
    net_income = entry.get("netIncome", "N/A")
    eps = entry.get("eps", "N/A")
    return f"""
Year: {year}
  • Revenue: ${revenue:,}
  • Net Income: ${net_income:,}
  • EPS: {eps}
"""
def format_article(article: dict) -> str:
    """Format a single news article into a readable string."""
    src = article.get("source", {}).get("name", "Unknown Source")
    title = article.get("title", "No title")
    date = article.get("publishedAt", "").split("T")[0] or "Unknown date"
    desc = article.get("description", "No description available")
    url = article.get("url", "")
    return f"""
Source: {src}
Date:   {date}
Title:  {title}
Summary:{desc}
Link:   {url}
"""


#tools
@mcp.tool()
async def get_companies_in_sector(sector: str) -> str:
    """Get a list of major publicly traded companies in a given sector.

    Args:
        sector: Name of the sector (e.g., 'Cosmetics', 'Technology')
    """
    encoded = quote(sector)
    url = (
        f"{FMP_API_BASE}/stock-screener"
        f"?sector={encoded}"
        f"&limit=10"
        f"&apikey={API_KEY}"
    )
    data = await make_fmp_request(url)

    if not data:
        return f"Unable to fetch companies for sector '{sector}', or no companies found."

    entries = [format_company(c) for c in data]
    return "\n---\n".join(entries)
@mcp.tool()
async def get_company_financials(ticker: str) -> str:
    """Get the last 4 years of income‐statement data for a given company.

    Args:
        ticker: Stock ticker symbol (e.g. "AAPL", "EL")
    """
    t = quote(ticker.upper())
    url = f"{FMP_API_BASE}/income-statement/{t}?limit=4&apikey={API_KEY}"
    data = await make_fmp_request(url)

    if not data:
        return f"Unable to fetch financials for '{ticker}', or no data found."

    entries = [format_financial_entry(e) for e in data]
    return "\n---\n".join(entries)

@mcp.tool()
async def get_company_news(company: str) -> str:
    """Get recent news articles for a given company.

    Args:
        company: Company name or ticker (e.g., "Apple", "AAPL")
    """
    q = quote(company)
    url = (
        f"{NEWS_API_BASE}/everything"
        f"?q={q}"
        f"&pageSize=5"
        f"&sortBy=publishedAt"
        f"&apiKey={NEWS_API_KEY}"
    )
    data = await make_news_request(url)

    if not data or "articles" not in data:
        return f"Unable to fetch news for '{company}', or no articles found."

    articles = data["articles"]
    if not articles:
        return f"No recent news articles found for '{company}'."

    formatted = [format_article(a) for a in articles]
    return "\n---\n".join(formatted)

@mcp.tool()
async def get_sector_financial_trends(sector: str, company_limit: int = 5) -> str:
    """Get aggregated financial trends for the top N companies in a given sector.

    Args:
        sector: Name of the sector (e.g. "Cosmetics")
        company_limit: Number of companies to include (default: 5)
    """
    # 1) Fetch top companies in sector
    sec = quote(sector)
    screener_url = (
        f"{FMP_API_BASE}/stock-screener"
        f"?sector={sec}"
        f"&limit={company_limit}"
        f"&apikey={API_KEY}"
    )
    companies = await make_fmp_request(screener_url)
    if not companies:
        return f"Unable to fetch companies for sector '{sector}'."

    tickers = [c.get("symbol", "") for c in companies]
    if not tickers:
        return f"No companies found in sector '{sector}'."

    # 2) Collect financials per year
    revs_by_year: dict[str, list[float]] = defaultdict(list)
    net_by_year: dict[str, list[float]] = defaultdict(list)

    for t in tickers:
        tkr = quote(t.upper())
        url = f"{FMP_API_BASE}/income-statement/{tkr}?limit=4&apikey={API_KEY}"
        data = await make_fmp_request(url)
        if not data:
            continue
        for entry in data:
            year = extract_year(entry.get("date", ""))
            rev = entry.get("revenue") or 0.0
            ni  = entry.get("netIncome") or 0.0
            revs_by_year[year].append(rev)
            net_by_year[year].append(ni)

    if not revs_by_year:
        return f"No financial data available for companies in '{sector}'."

    # 3) Compute averages and year-over-year growth
    years = sorted(revs_by_year.keys())
    avg_rev = { y: sum(revs_by_year[y]) / len(revs_by_year[y]) for y in years }
    avg_net = { y: sum(net_by_year[y]) / len(net_by_year[y]) for y in years }

    # Build summary strings
    summary_lines = ["Sector Financial Trends:"]
    for y in years:
        summary_lines.append(
            f"{y}: Avg Revenue = ${avg_rev[y]:,.2f}, "
            f"Avg Net Income = ${avg_net[y]:,.2f}"
        )

    # Year-over-year growth
    gow_rev = []
    gow_net = []
    for i in range(1, len(years)):
        prev, curr = years[i-1], years[i]
        gr = (avg_rev[curr] - avg_rev[prev]) / avg_rev[prev] * 100 if avg_rev[prev] else 0
        gn = (avg_net[curr] - avg_net[prev]) / avg_net[prev] * 100 if avg_net[prev] else 0
        gow_rev.append(f"{prev}→{curr} Rev Δ: {gr:+.1f}%")
        gow_net.append(f"{prev}→{curr} Net Δ: {gn:+.1f}%")

    summary_lines.append("\nRevenue Growth:")
    summary_lines.extend(gow_rev)
    summary_lines.append("\nNet Income Growth:")
    summary_lines.extend(gow_net)

    return "\n".join(summary_lines)


if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport="stdio")
