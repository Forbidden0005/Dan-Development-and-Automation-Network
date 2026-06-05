"""Token usage and cost tracking for Dan sessions."""

import time
from dataclasses import dataclass, field

# Cost per 1M tokens (input, output) by model name substring.
# Order matters — first match wins. Rates from provider pricing pages.
_RATES: list[tuple[str, float, float]] = [
    # Anthropic
    ("claude-opus-4", 15.00, 75.00),
    ("claude-sonnet-4", 3.00, 15.00),
    ("claude-haiku-3-5", 0.80, 4.00),
    ("claude-haiku-3", 0.25, 1.25),
    # OpenAI
    ("gpt-4o-mini", 0.15, 0.60),
    ("gpt-4o", 5.00, 15.00),
    ("gpt-4-turbo", 10.00, 30.00),
    ("gpt-4", 30.00, 60.00),
    ("gpt-3.5", 0.50, 1.50),
    # Venice / Ollama (local / flat-rate — treat as free for cost display)
    ("llama", 0.00, 0.00),
    ("mistral", 0.00, 0.00),
    ("qwen", 0.00, 0.00),
    ("venice", 0.00, 0.00),
]

_DEFAULT_RATES = (3.00, 15.00)  # fallback


def _get_rates(model: str) -> tuple[float, float]:
    """Return (input_$/1M, output_$/1M) for a model name."""
    model_lower = model.lower()
    for key, inp, out in _RATES:
        if key in model_lower:
            return (inp, out)
    return _DEFAULT_RATES


@dataclass
class SessionCost:
    """Cumulative token and cost tracking for one Dan session."""

    model: str
    session_start: float = field(default_factory=time.time)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    call_count: int = 0

    def record(self, input_tokens: int, output_tokens: int) -> None:
        """Record token usage from one API call."""
        self.total_input_tokens += max(0, input_tokens)
        self.total_output_tokens += max(0, output_tokens)
        self.call_count += 1

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    def estimate_cost(self) -> float:
        """Estimate USD cost for the session so far."""
        rates = _get_rates(self.model)
        return (self.total_input_tokens / 1_000_000) * rates[0] + (
            self.total_output_tokens / 1_000_000
        ) * rates[1]

    def is_free_model(self) -> bool:
        rates = _get_rates(self.model)
        return rates == (0.0, 0.0)

    def summary(self) -> str:
        """Multi-line summary for the /cost command."""
        elapsed = time.time() - self.session_start
        h, rem = divmod(int(elapsed), 3600)
        m, s = divmod(rem, 60)
        duration = f"{h}h {m}m {s}s" if h else (f"{m}m {s}s" if m else f"{s}s")

        cost = self.estimate_cost()
        cost_str = "(local — no charge)" if self.is_free_model() else f"~${cost:.5f}"

        return (
            f"  Model:        {self.model}\n"
            f"  API calls:    {self.call_count}\n"
            f"  Input tokens: {self.total_input_tokens:,}\n"
            f"  Output tokens:{self.total_output_tokens:,}\n"
            f"  Total tokens: {self.total_tokens:,}\n"
            f"  Est. cost:    {cost_str}\n"
            f"  Session time: {duration}"
        )


# ── Module-level singleton ────────────────────────────────────────────────────

_tracker: SessionCost | None = None


def init(model: str) -> SessionCost:
    """Initialise (or reset) the global cost tracker for a new session."""
    global _tracker
    _tracker = SessionCost(model=model)
    return _tracker


def get() -> SessionCost | None:
    """Return the active tracker (None if not yet initialised)."""
    return _tracker


def record(input_tokens: int, output_tokens: int) -> None:
    """Record usage into the global tracker (no-op if uninitialised)."""
    if _tracker is not None:
        _tracker.record(input_tokens, output_tokens)
