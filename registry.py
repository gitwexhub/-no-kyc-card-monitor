"""
Agent registry — auto-discovers and manages provider agents.

Usage:
    registry = AgentRegistry()
    registry.discover()          # scans agents/ for subclasses
    agent = registry.get("ezzocard")
    card = await agent.signup()
"""

import importlib
import pkgutil
from pathlib import Path
from typing import Optional

from agents.base_agent import BaseCardAgent


class AgentRegistry:
    """Registry of all available provider agents."""

    def __init__(self):
        self._agents: dict[str, type[BaseCardAgent]] = {}

    def register(self, agent_cls: type[BaseCardAgent]):
        """Manually register an agent class."""
        name = agent_cls.provider_name.fget(None) if isinstance(
            agent_cls.provider_name, property
        ) else None

        # Instantiate temporarily to get the name
        # (properties need an instance)
        try:
            dummy = object.__new__(agent_cls)
            name = dummy.provider_name
        except Exception:
            name = agent_cls.__name__.lower().replace("agent", "")

        self._agents[name] = agent_cls
        return agent_cls

    def discover(self, package_path: str = None):
        """
        Auto-discover all BaseCardAgent subclasses in the agents/ directory.
        Import every module in the package, then find subclasses.
        """
        agents_dir = Path(package_path or __file__).parent

        for module_info in pkgutil.iter_modules([str(agents_dir)]):
            if module_info.name.startswith("_") or module_info.name in (
                "base_agent", "registry"
            ):
                continue
            try:
                mod = importlib.import_module(f"agents.{module_info.name}")
            except ImportError as e:
                print(f"Warning: Could not import agents.{module_info.name}: {e}")
                continue

            for attr_name in dir(mod):
                attr = getattr(mod, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, BaseCardAgent)
                    and attr is not BaseCardAgent
                ):
                    self.register(attr)

    def get(
        self, provider_name: str, config: dict = None
    ) -> Optional[BaseCardAgent]:
        """Get an instantiated agent by provider name."""
        cls = self._agents.get(provider_name)
        if cls:
            return cls(config=config or {})
        return None

    def list_providers(self) -> list[str]:
        """Return all registered provider names."""
        return sorted(self._agents.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._agents

    def __len__(self) -> int:
        return len(self._agents)

    def __repr__(self) -> str:
        return f"<AgentRegistry providers={self.list_providers()}>"
