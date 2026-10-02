"""Shared pieces of the codemod families: vocabulary, module names, prompt voices."""
from __future__ import annotations

MODULE_NAMES = [
    "bakery", "harbor", "clinic", "orchard", "garage", "theatre", "library", "foundry", "apiary", "kiln", "lantern", "mill", "nursery",
    "observatory", "pantry", "quarry", "ropewalk", "salon", "tannery", "vineyard", "workshop", "stable", "atelier", "brewery", "creamery",
    "depot", "estate", "fishery", "glasshouse", "hatchery", "inn", "joinery", "kennel", "laundry", "market", "smithy", "tavern", "chandlery",
    "dairy", "cooperage",
]
ITEMS = ["widget", "bolt", "loaf", "ticket", "plank", "candle", "rope", "lens", "tile", "jar", "spool", "barrel", "wheel", "badge", "ribbon",
         "crate", "needle", "lamp", "anvil", "scroll"]
UNITS = ["kg", "l", "pc", "m", "box", "g"]
KINDS = ["fresh", "dried", "spare", "bulk", "loose", "sealed"]
REGIONS = ["north", "south", "east", "west", "coast", "hills"]
WORDS = ["amber copper", "silver birch", "old harbour", "red lantern", "quiet mill", "grand market", "tin roof", "salt marsh", "iron gate", "blue door"]
