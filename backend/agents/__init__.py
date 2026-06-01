"""Agent registry for MERGENT.

Each agent exposes an async `run(ctx)` function and follows the same contract:
  - `ctx` is a dict carrying upstream agent outputs.
  - returns a dict that will be merged into ctx.
  - any LLM use goes through services.ai_provider.
  - timing + token-usage attribution is done by the orchestrator, which wraps
    each agent call.
"""
