"""
Main orchestrator for Mississippi Weather Desk.

Provides CLI for running the weather briefing pipeline.
"""

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from .analyze import build_briefing
from .llm import generate_article
from .emailer import send_email

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


def get_project_root() -> Path:
    """Get the project root directory."""
    # This file is in src/, so parent is project root
    return Path(__file__).parent.parent


def run_once():
    """
    Run a single weather briefing cycle.
    
    Fetches data, builds briefing, generates article, and sends email.
    """
    logger.info("Starting Mississippi Weather Desk...")
    
    # Load environment variables
    project_root = get_project_root()
    env_path = project_root / ".env"
    
    if env_path.exists():
        load_dotenv(env_path)
        logger.info(f"Loaded environment from {env_path}")
    else:
        logger.warning(f".env file not found at {env_path}")
    
    # Set up paths
    config_dir = project_root / "config"
    data_dir = project_root / "data"
    
    # Ensure directories exist
    config_dir.mkdir(exist_ok=True)
    data_dir.mkdir(exist_ok=True)
    
    try:
        # Build briefing from all data sources
        briefing = build_briefing(config_dir, data_dir)
        
        # Generate article using LLM
        headline, article_body, highlights = generate_article(briefing)
        
        # Send email
        success = send_email(
            headline=headline,
            highlights=highlights,
            article_body=article_body,
            time_of_day=briefing.time_of_day,
            date_str=briefing.valid_date,
            data_gaps=briefing.data_gaps,
            sources=briefing.sources_used,
        )
        
        if success:
            logger.info("✓ Weather briefing sent successfully!")
            return 0
        else:
            logger.error("✗ Failed to send weather briefing email")
            return 1
            
    except Exception as e:
        logger.exception(f"Fatal error during briefing generation: {e}")
        return 1


def run_test():
    """
    Run in test mode - generate briefing but don't send email.
    """
    logger.info("Running in TEST mode (no email will be sent)...")
    
    # Load environment variables
    project_root = get_project_root()
    env_path = project_root / ".env"
    
    if env_path.exists():
        load_dotenv(env_path)
    
    config_dir = project_root / "config"
    data_dir = project_root / "data"
    
    try:
        # Build briefing
        briefing = build_briefing(config_dir, data_dir)
        
        # Generate article
        headline, article_body, highlights = generate_article(briefing)
        
        # Print results instead of emailing
        print("\n" + "=" * 60)
        print("TEST MODE - Email Preview")
        print("=" * 60)
        print(f"\nSubject: Mississippi Weather Briefing — {briefing.time_of_day} — {briefing.valid_date}")
        print(f"\nHeadline: {headline}")
        print("\nHighlights:")
        for i, h in enumerate(highlights, 1):
            print(f"  {i}. {h}")
        print("\n" + "-" * 60)
        print("Article Body:")
        print("-" * 60)
        print(article_body[:2000])  # First 2000 chars
        if len(article_body) > 2000:
            print(f"\n... [{len(article_body) - 2000} more characters]")
        print("\n" + "=" * 60)
        
        return 0
        
    except Exception as e:
        logger.exception(f"Error in test mode: {e}")
        return 1


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Mississippi Weather Desk - Automated Weather Briefings",
        prog="python -m src.run",
    )
    
    parser.add_argument(
        "--mode",
        choices=["once", "test"],
        default="once",
        help="Run mode: 'once' sends email, 'test' prints preview",
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    if args.mode == "once":
        sys.exit(run_once())
    elif args.mode == "test":
        sys.exit(run_test())


if __name__ == "__main__":
    main()
