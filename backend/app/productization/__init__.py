"""Productization assets for the RAG Refinement System (Phase G, C8).

Houses go-to-market and operability utilities that sit alongside the core
retrieval-refinement layer without altering routing, ingestion, or persistence
behavior:

- ``roi_calculator``: projects monthly LLM-spend savings from the documented
  40-70% token-reduction range (PRD §15.1, §21) for sales/GTM modeling.
- ``metrics``: an in-process registry for the four product KPIs (token
  reduction %, answer accuracy, routing latency, fallback rate) exposed at
  ``/metrics`` for scrape-based observability (PRD §21, NFR-009).
"""

from __future__ import annotations
