"""
Configuration loader for unified betting scraper.
Loads settings from YAML files.
"""

import logging
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

# Default config directory (src/config.py -> src -> 1UP_calc -> config)
CONFIG_DIR = Path(__file__).parent.parent / "config"


class ConfigLoader:
    """Loads and manages configuration from YAML files."""

    def get_enabled_engines(self) -> list:
        """Return list of enabled engine class names from engine.yaml config."""
        config = self.load_engine_config()
        engines = config.get('engines', {})
        return [name for name, enabled in engines.items() if enabled]

    def __init__(self, config_dir: Optional[Path] = None):
        """
        Initialize config loader.
        
        Args:
            config_dir: Path to config directory (default: project/config/)
        """
        self.config_dir = Path(config_dir) if config_dir else CONFIG_DIR
        self._settings = None
        self._tournaments = None
        self._markets = None
    
    def load_settings(self) -> dict:
        """Load settings.yaml configuration."""
        if self._settings is None:
            path = self.config_dir / "settings.yaml"
            self._settings = self._load_yaml(path)
        return self._settings
    
    def load_tournaments(self) -> list[dict]:
        """Load enabled tournaments from tournaments.yaml."""
        if self._tournaments is None:
            path = self.config_dir / "tournaments.yaml"
            data = self._load_yaml(path)
            self._tournaments = [
                t for t in data.get("tournaments", [])
                if t.get("enabled", True)
            ]
        return self._tournaments
    
    def load_markets(self) -> list[dict]:
        """Load enabled markets from markets.yaml."""
        if self._markets is None:
            path = self.config_dir / "markets.yaml"
            data = self._load_yaml(path)
            self._markets = [
                m for m in data.get("markets", [])
                if m.get("enabled", True)
            ]
        return self._markets
    
    def _load_yaml(self, path: Path) -> dict:
        """Load a YAML file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.error(f"Config file not found: {path}")
            return {}
        except yaml.YAMLError as e:
            logger.error(f"Error parsing YAML file {path}: {e}")
            return {}
    
    # ==========================================
    # Convenience Methods
    # ==========================================
    
    def get_db_path(self) -> str:
        """Get database path from settings (always relative to project root)."""
        settings = self.load_settings()
        relative_path = settings.get("database", {}).get("path", "data/datas.db")
        # Make absolute relative to project root
        return str(self.config_dir.parent / relative_path)
    
    def get_sporty_market_ids(self) -> set[str]:
        """Get set of enabled Sportybet market IDs."""
        markets = self.load_markets()
        return {m["sporty_id"] for m in markets if m.get("sporty_id")}
    
    def get_pawa_market_ids(self) -> set[str]:
        """Get set of enabled Betpawa market IDs."""
        markets = self.load_markets()
        return {m["pawa_id"] for m in markets if m.get("pawa_id")}
    
    def get_market_mapping(self) -> dict:
        """
        Get mapping from Sportybet market ID to market info.
        
        Returns:
            Dict: {sporty_id: {pawa_id, name, has_specifier, pawa_handicap_scale}}
        """
        markets = self.load_markets()
        mapping = {}
        for m in markets:
            sporty_id = m.get("sporty_id")
            if sporty_id:
                mapping[sporty_id] = {
                    "pawa_id": m.get("pawa_id"),
                    "name": m.get("name"),
                    "has_specifier": m.get("has_specifier", False),
                    "specifier_key": m.get("specifier_key"),
                    "pawa_handicap_scale": m.get("pawa_handicap_scale", 4),
                }
        return mapping
    
    def get_enabled_tournaments(self) -> list[dict]:
        """Get list of enabled tournaments with both Sporty and Pawa IDs."""
        # Include tournaments that are enabled and have at least one configured
        # bookmaker source (Pawa or Bet9ja). Previously this returned only
        # tournaments with a `pawa_competition_id` which prevented Bet9ja-only
        # tournaments from being included in the unified scraping run.
        tournaments = self.load_tournaments()
        return [
            t for t in tournaments
            if t.get("enabled", True) and (
                t.get("pawa_competition_id") or t.get("bet9ja_group_id")
            )
        ]
    
    def get_all_enabled_tournaments(self) -> list[dict]:
        """Get all enabled tournaments (even without Pawa ID)."""
        return self.load_tournaments()

    # ==========================================
    # Scraper Concurrency Settings
    # ==========================================

    def get_concurrency_settings(self) -> dict:
        """
        Get concurrency settings for scrapers.

        Returns:
            Dict with 'pawa', 'sporty', 'bet9ja', 'tournaments' max concurrent values
        """
        settings = self.load_settings()
        concurrency = settings.get("scraper", {}).get("concurrency", {})
        return {
            "pawa": concurrency.get("pawa", 10),
            "sporty": concurrency.get("sporty", 10),
            "bet9ja": concurrency.get("bet9ja", 10),
            "tournaments": concurrency.get("tournaments", 3),
        }

    # ==========================================
    # Engine Configuration
    # ==========================================
    
    def load_engine_config(self) -> dict:
        """Load engine.yaml configuration for 1UP calculator."""
        path = self.config_dir / "engine.yaml"
        return self._load_yaml(path)
    
    def get_engine_margin(self) -> dict:
        """
        Get margin settings for 1UP engine.
        
        Returns:
            Dict with 'default', 'home', 'draw', 'away' margin values
        """
        config = self.load_engine_config()
        margin = config.get("margin", {})
        default = margin.get("default", 0.05)
        return {
            "default": default,
            "home": margin.get("home") if margin.get("home") is not None else default,
            "draw": margin.get("draw") if margin.get("draw") is not None else default,
            "away": margin.get("away") if margin.get("away") is not None else default,
        }
    
    def get_engine_test_margins(self) -> list[float]:
        """
        Get list of margin values to test for optimization.
        
        Returns:
            List of margin values (e.g., [0.03, 0.04, 0.05, 0.06])
        """
        config = self.load_engine_config()
        margin = config.get("margin", {})
        test_values = margin.get("test_values")
        
        if test_values and isinstance(test_values, list):
            return [float(v) for v in test_values]
        
        # Fallback to just the default value
        return [margin.get("default", 0.05)]
    
    def get_engine_simulation_settings(self) -> dict:
        """
        Get simulation settings for 1UP engine.
        
        Returns:
            Dict with 'n_sims' and 'match_minutes'
        """
        config = self.load_engine_config()
        simulation = config.get("simulation", {})
        return {
            "n_sims": simulation.get("n_sims", 30000),
            "match_minutes": simulation.get("match_minutes", 95),
        }
    
    def get_engine_output_settings(self) -> dict:
        """
        Get output formatting settings.
        
        Returns:
            Dict with 'odds_precision' and 'prob_precision'
        """
        config = self.load_engine_config()
        output = config.get("output", {})
        return {
            "odds_precision": output.get("odds_precision", 2),
            "prob_precision": output.get("prob_precision", 1),
        }


# Global config instance
config = ConfigLoader()
