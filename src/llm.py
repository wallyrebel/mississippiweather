"""
OpenAI LLM integration for Mississippi Weather Desk.

Generates long-form weather articles from structured briefing data.
"""

import json
import logging
import os
from typing import Dict, Any, Tuple, Optional, List

from openai import OpenAI

from .models import WeatherBriefing

logger = logging.getLogger(__name__)

# Model preference order - try each until one works
MODEL_CHAIN = [
    "gpt-5-mini",      # Primary - superior quality
    "gpt-4.1-nano",    # Fallback 1 - cost effective
    "gpt-4o-mini",     # Fallback 2 - widely available
    "gpt-4o",          # Fallback 3 - high quality
    "gpt-4",           # Fallback 4 - stable
]


def get_client() -> OpenAI:
    """Get OpenAI client with API key from environment."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")
    return OpenAI(api_key=api_key)


SYSTEM_PROMPT_MORNING = """You are an expert meteorologist and weather writer for the Mississippi Weather Desk. 
Your job is to write professional, accurate, AP-style weather briefings for the state of Mississippi.

THIS IS THE MORNING EDITION - Write a COMPREHENSIVE, FULL weather briefing.

STYLE GUIDELINES:
- Use AP newsroom style: factual, clear, no sensationalism
- Write in third person
- Use Central Time (CT) for all times
- Be specific about locations and counties when relevant
- Clearly separate official NWS WARNINGS/WATCHES/ADVISORIES from SPC/WPC guidance/outlooks
- When uncertainty is high, say so explicitly
- No external hyperlinks in the article text
- Do not invent data; only use what is provided
- Make forecasts easy to read and understand for general audiences
- Use clear temperature and precipitation language

MANDATORY ARTICLE STRUCTURE (YOU MUST INCLUDE ALL SECTIONS IN THIS ORDER):
1. HEADLINE: One compelling line summarizing the key weather story
2. HIGHLIGHTS: Exactly 5 bullet points with the most important takeaways

Then include ALL of these sections with these EXACT headers:

## Watches, Warnings & Advisories
List ALL active NWS watches, warnings, and advisories. If none, state "No active watches, warnings, or advisories for Mississippi."

## Current Conditions
What's happening RIGHT NOW across the 8 regions - temperature, sky conditions, wind for each region.

## Today's Forecast
Detailed look at today's weather including highs, lows, precipitation chances for each region.

## 3-Day Outlook
Day-by-day breakdown for the next 3 days with temperatures and conditions.

## 7-Day Forecast
Extended outlook showing the weather trend through the week, noting any significant changes.

## Regional Details
Specific forecasts for each of the 8 regions (Northwest, Northeast, Delta, Central, Southwest, Pine Belt, Gulf Coast West, Gulf Coast East).

## Hazards
Include severe weather, flooding, winter weather, or tropical threats if applicable. If none, state "No significant weather hazards expected."

## Timing & Confidence
When will weather changes occur? How confident are we in the forecast?

## Sources
List all NWS, SPC, WPC, NHC products used.

TARGET LENGTH: 1500-2500 words (this is the main daily briefing)."""


SYSTEM_PROMPT_UPDATE = """You are an expert meteorologist and weather writer for the Mississippi Weather Desk.
Your job is to write weather UPDATE briefings for Mississippi.

THIS IS AN UPDATE EDITION - Focus on CHANGES and KEY UPDATES since the morning briefing.

STYLE GUIDELINES:
- Use AP newsroom style: factual, clear, no sensationalism
- Write in third person
- Use Central Time (CT) for all times
- Focus on what has CHANGED or is NEW since the morning
- If conditions are stable with no changes, keep the update brief
- Highlight any new watches, warnings, or changes in the forecast

UPDATE ARTICLE STRUCTURE:
1. HEADLINE: One line summarizing any changes or the current situation
2. HIGHLIGHTS: 3-5 bullet points with the most important updates

Then include these sections (can be shorter if no significant changes):

## Watches, Warnings & Advisories
List any NEW or UPDATED alerts. Note if unchanged from this morning.

## Current Conditions
Brief update on conditions across the state - can be condensed if similar to morning.

## Forecast Update
Note any changes to today's or this week's forecast. If unchanged, state "No significant changes to the forecast."

## Hazards Update
Any new or developing hazards. If none, keep it brief.

## Looking Ahead
Brief note on what to watch for overnight/tomorrow.

## Sources
List data sources used.

TARGET LENGTH: 500-1000 words (shorter update, focus on changes)."""


def get_system_prompt(time_of_day: str) -> str:
    """Get the appropriate system prompt based on edition type."""
    if time_of_day == "Morning":
        return SYSTEM_PROMPT_MORNING
    else:
        return SYSTEM_PROMPT_UPDATE


def build_llm_prompt(briefing: WeatherBriefing) -> str:
    """
    Build the prompt for the LLM from briefing data.
    
    Args:
        briefing: WeatherBriefing object
        
    Returns:
        Prompt string for the LLM
    """
    # Convert briefing to JSON for LLM consumption
    briefing_json = json.dumps(briefing.to_dict(), indent=2, default=str)
    
    # Build alert summary for emphasis
    alert_summary = "NO ACTIVE ALERTS"
    if briefing.alerts:
        alert_list = []
        for event_type, alerts in briefing.alerts_by_type.items():
            counties = []
            for a in alerts:
                counties.extend(a.affected_counties)
            alert_list.append(f"- {event_type}: {', '.join(set(counties)[:5])}")
        alert_summary = "\n".join(alert_list)
    
    prompt = f"""Generate a comprehensive Mississippi Weather Briefing article.

BRIEFING DATE: {briefing.valid_date}
TIME OF DAY: {briefing.time_of_day} Edition
GENERATED AT: {briefing.generated_at.strftime("%I:%M %p CT")}

=== ACTIVE NWS ALERTS (MUST BE INCLUDED IN WATCHES/WARNINGS SECTION) ===
{alert_summary}

=== FULL WEATHER DATA ===
{briefing_json}

=== MANDATORY INSTRUCTIONS ===
Write a complete weather briefing with ALL required sections in order:

1. Start with "HEADLINE:" followed by the headline
2. Then "HIGHLIGHTS:" followed by exactly 5 bullet points (use • for bullets)
3. Then write the article with ALL of these section headers IN ORDER:
   - ## Watches, Warnings & Advisories
   - ## Current Conditions
   - ## Today's Forecast
   - ## 3-Day Outlook
   - ## 7-Day Forecast
   - ## Regional Details
   - ## Hazards
   - ## Timing & Confidence
   - ## Sources

CRITICAL: 
- You MUST include ALL sections even if data is limited
- Use the daily_forecasts data for 7-day outlook
- Include temperature data for EACH of the 8 regions
- List actual NWS alerts in the Watches/Warnings section
- If no alerts, explicitly state "No active watches, warnings, or advisories"
"""

    return prompt


def try_generate_with_model(
    client: OpenAI,
    model: str,
    prompt: str,
    system_prompt: str
) -> Optional[str]:
    """
    Try to generate article with a specific model.
    
    Returns:
        Generated content or None if failed
    """
    try:
        logger.info(f"Trying model: {model}")
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            max_tokens=6000,
            temperature=0.7,
        )
        
        content = response.choices[0].message.content
        logger.info(f"Success with {model}: {len(content)} characters generated")
        return content
        
    except Exception as e:
        logger.warning(f"Model {model} failed: {type(e).__name__}: {str(e)[:100]}")
        return None


def generate_article(briefing: WeatherBriefing) -> Tuple[str, str, list]:
    """
    Generate weather article from briefing using OpenAI with model fallback chain.
    
    Args:
        briefing: WeatherBriefing object
        
    Returns:
        Tuple of (headline, article_body, highlights_list)
    """
    logger.info(f"Generating {briefing.time_of_day} edition article with OpenAI...")
    
    client = get_client()
    
    # Check for environment override
    env_model = os.getenv("OPENAI_MODEL")
    if env_model:
        models_to_try = [env_model] + MODEL_CHAIN
    else:
        models_to_try = MODEL_CHAIN
    
    # Get the appropriate prompt for this edition
    system_prompt = get_system_prompt(briefing.time_of_day)
    prompt = build_llm_prompt(briefing)
    
    # Try each model in order
    content = None
    for model in models_to_try:
        content = try_generate_with_model(client, model, prompt, system_prompt)
        if content:
            break

    
    if content:
        # Parse the response
        headline, highlights, body = parse_article_response(content)
        
        # Validate required sections
        body = ensure_required_sections(body, briefing)
        
        logger.info(f"Article generated: {len(body)} characters, headline: {headline[:50] if headline else 'None'}...")
        
        return headline, body, highlights
    
    # All models failed - use fallback
    logger.error("All OpenAI models failed, using fallback article")
    return generate_fallback_article(briefing)


def ensure_required_sections(body: str, briefing: WeatherBriefing) -> str:
    """
    Ensure all required sections exist in the article.
    Add missing sections with basic content.
    """
    required_sections = [
        ("## Watches, Warnings & Advisories", build_watches_section(briefing)),
        ("## Current Conditions", None),
        ("## Today's Forecast", None),
        ("## 3-Day Outlook", None),
        ("## 7-Day Forecast", None),
        ("## Regional Details", None),
        ("## Hazards", None),
        ("## Timing & Confidence", None),
        ("## Sources", build_sources_section(briefing)),
    ]
    
    for section_header, fallback_content in required_sections:
        if section_header.lower() not in body.lower():
            logger.warning(f"Missing section: {section_header}")
            if fallback_content:
                body += f"\n\n{section_header}\n\n{fallback_content}"
    
    return body


def build_watches_section(briefing: WeatherBriefing) -> str:
    """Build the watches/warnings section from alerts."""
    if not briefing.alerts:
        return "No active watches, warnings, or advisories for Mississippi at this time."
    
    lines = []
    for event_type, alerts in briefing.alerts_by_type.items():
        for alert in alerts:
            counties = ", ".join(alert.affected_counties[:5])
            if len(alert.affected_counties) > 5:
                counties += f" and {len(alert.affected_counties) - 5} more"
            lines.append(f"**{event_type}**: {counties}")
            if alert.headline:
                lines.append(f"  {alert.headline}")
    
    return "\n\n".join(lines) if lines else "No active watches, warnings, or advisories for Mississippi at this time."


def build_sources_section(briefing: WeatherBriefing) -> str:
    """Build the sources section."""
    if briefing.sources_used:
        return "This briefing uses data from: " + ", ".join(briefing.sources_used)
    return "This briefing uses data from: NWS, SPC, WPC, NHC"


def parse_article_response(content: str) -> Tuple[str, list, str]:
    """
    Parse the LLM response into headline, highlights, and body.
    
    Args:
        content: Raw LLM response
        
    Returns:
        Tuple of (headline, highlights_list, article_body)
    """
    lines = content.strip().split("\n")
    
    headline = ""
    highlights = []
    body_lines = []
    
    in_highlights = False
    past_highlights = False
    
    for line in lines:
        line_stripped = line.strip()
        
        # Extract headline
        if line_stripped.upper().startswith("HEADLINE:"):
            headline = line_stripped[9:].strip().lstrip("#").strip()
            continue
        
        # Detect highlights section
        if line_stripped.upper().startswith("HIGHLIGHTS:"):
            in_highlights = True
            continue
        
        # Collect highlights (bullet points)
        if in_highlights and not past_highlights:
            if line_stripped.startswith("•") or line_stripped.startswith("-") or line_stripped.startswith("*"):
                bullet = line_stripped.lstrip("•-* ").strip()
                if bullet:
                    highlights.append(bullet)
            elif line_stripped.startswith("##") or (line_stripped and len(highlights) >= 5):
                past_highlights = True
                in_highlights = False
                body_lines.append(line)
            elif not line_stripped:
                if len(highlights) >= 5:
                    past_highlights = True
                    in_highlights = False
            continue
        
        # Everything else is body
        body_lines.append(line)
    
    body = "\n".join(body_lines).strip()
    
    # Clean up headline if needed
    if not headline and body_lines:
        for i, line in enumerate(body_lines):
            if line.strip() and len(line.strip()) < 150 and not line.strip().startswith("##"):
                headline = line.strip()
                body = "\n".join(body_lines[i+1:]).strip()
                break
    
    # Ensure we have at least 5 highlights
    while len(highlights) < 5:
        highlights.append("See detailed forecast below")
    
    return headline, highlights[:5], body


def generate_fallback_article(briefing: WeatherBriefing) -> Tuple[str, str, list]:
    """
    Generate a complete article when LLM fails, ensuring all required sections.
    
    Args:
        briefing: WeatherBriefing object
        
    Returns:
        Tuple of (headline, article_body, highlights_list)
    """
    headline = f"Mississippi Weather Update — {briefing.time_of_day} {briefing.valid_date}"
    
    highlights = [
        briefing.statewide_overview[:100] + "..." if len(briefing.statewide_overview or "") > 100 
            else (briefing.statewide_overview or "See forecast details below"),
        f"{len(briefing.alerts)} active NWS alerts" if briefing.alerts else "No active weather alerts",
        briefing.severe_summary or "No severe weather expected",
        briefing.rainfall_summary or "Light or no rainfall expected",
        "See extended forecast and regional details below",
    ]
    
    body_parts = []
    
    # Watches, Warnings & Advisories
    body_parts.append("## Watches, Warnings & Advisories\n")
    if briefing.alerts:
        for event_type, alerts in briefing.alerts_by_type.items():
            body_parts.append(f"**{event_type}**")
            for alert in alerts[:3]:
                body_parts.append(f"- {alert.headline}")
    else:
        body_parts.append("No active watches, warnings, or advisories for Mississippi at this time.")
    body_parts.append("")
    
    # Current Conditions
    body_parts.append("## Current Conditions\n")
    for summary in briefing.regional_summaries:
        temp_str = f"{summary.current_temp}°F" if summary.current_temp else "N/A"
        body_parts.append(f"**{summary.region} ({summary.anchor_city})**: {temp_str}, {summary.current_conditions or 'data pending'}")
    body_parts.append("")
    
    # Today's Forecast
    body_parts.append("## Today's Forecast\n")
    for summary in briefing.regional_summaries:
        high = f"High {summary.high_temp}°F" if summary.high_temp else ""
        low = f"Low {summary.low_temp}°F" if summary.low_temp else ""
        temp_range = f"{high}, {low}".strip(", ") or "Temps pending"
        pop = f", {summary.pop}% chance of precipitation" if summary.pop else ""
        body_parts.append(f"**{summary.region}**: {temp_range}{pop}")
    body_parts.append("")
    
    # 3-Day Outlook
    body_parts.append("## 3-Day Outlook\n")
    for summary in briefing.regional_summaries:
        if summary.daily_forecasts:
            days_str = []
            for day in summary.daily_forecasts[:3]:
                high = day.high_temp or "N/A"
                cond = day.conditions or ""
                days_str.append(f"{day.day_name}: {high}°F {cond}")
            body_parts.append(f"**{summary.region}**: " + " | ".join(days_str))
    body_parts.append("")
    
    # 7-Day Forecast
    body_parts.append("## 7-Day Forecast\n")
    for summary in briefing.regional_summaries:
        if summary.daily_forecasts:
            days_str = []
            for day in summary.daily_forecasts[:7]:
                high = day.high_temp or "?"
                days_str.append(f"{day.day_name[:3]}: {high}°")
            body_parts.append(f"**{summary.region}**: " + " | ".join(days_str))
    body_parts.append("")
    
    # Regional Details
    body_parts.append("## Regional Details\n")
    for summary in briefing.regional_summaries:
        body_parts.append(f"**{summary.region} ({summary.anchor_city})**")
        body_parts.append(f"Today: High {summary.high_temp}°F, {summary.conditions_summary or 'details pending'}")
        if summary.daily_forecasts:
            for day in summary.daily_forecasts[1:4]:
                body_parts.append(f"- {day.day_name}: High {day.high_temp}°F, {day.conditions or ''}")
        body_parts.append("")
    
    # Hazards
    body_parts.append("## Hazards\n")
    hazards = []
    if briefing.severe_summary:
        hazards.append(f"**Severe Weather**: {briefing.severe_summary}")
    if briefing.rainfall_summary:
        hazards.append(f"**Heavy Rain/Flooding**: {briefing.rainfall_summary}")
    if briefing.winter_summary:
        hazards.append(f"**Winter Weather**: {briefing.winter_summary}")
    if briefing.tropical_summary:
        hazards.append(f"**Tropical**: {briefing.tropical_summary}")
    if hazards:
        body_parts.extend(hazards)
    else:
        body_parts.append("No significant weather hazards expected for Mississippi at this time.")
    body_parts.append("")
    
    # Timing & Confidence
    body_parts.append("## Timing & Confidence\n")
    body_parts.append("Forecast confidence is moderate for the next 3 days and decreases for days 4-7. Check back for updates.")
    body_parts.append("")
    
    # Sources
    body_parts.append("## Sources\n")
    if briefing.sources_used:
        body_parts.append("This briefing uses data from: " + ", ".join(briefing.sources_used))
    else:
        body_parts.append("This briefing uses data from: NWS, SPC, WPC, NHC")
    
    # Data gaps
    if briefing.data_gaps:
        body_parts.append("")
        body_parts.append("**Data Gaps**: " + ", ".join(briefing.data_gaps))
    
    body = "\n".join(body_parts)
    
    return headline, body, highlights
