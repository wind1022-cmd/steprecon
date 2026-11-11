"""Command-line options shared by run.py and eval_batch.py (choose Claude API or a local model)."""
import os

from . import llm


def add_llm_args(ap):
    g = ap.add_argument_group("LLM backend")
    g.add_argument("--backend", default=os.environ.get("STEPRECON_BACKEND", "anthropic"),
                   choices=["anthropic", "openai"],
                   help="anthropic = Claude API; openai = any OpenAI-compatible server (Ollama, LM Studio, vLLM...)")
    g.add_argument("--model", default=None, help="model name (default: claude-opus-5-5 for anthropic, qwen3:8b for openai/Ollama)")
    g.add_argument("--base-url", default=None,
                   help="openai backend only; default http://localhost:11434/v1 (Ollama). LM Studio: "
                        "http://localhost:1234/v1, vLLM: http://localhost:8000/v1")
    g.add_argument("--tool-mode", default="auto", choices=["auto", "native", "text"],
                   help="openai backend: native function calling, JSON-in-text protocol, or auto-detect (default)")
    g.add_argument("--profile", default=None, choices=["full", "basic"],
                   help="tool set: full (24 tools, long prompt) or basic (9 tools, short prompt for small local "
                        "models). Default: full for anthropic, basic for openai")
    g.add_argument("--max-faces-prompt", type=int, default=None,
                   help="faces listed in the prompt (default 80; 30 is kinder to small context windows)")
    g.add_argument("--temperature", type=float, default=0.2, help="openai backend sampling temperature")
    return g


def backend_from_args(a):
    if a.backend == "anthropic":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise SystemExit("ANTHROPIC_API_KEY is not set (or use --backend openai with a local model)")
        return llm.make_backend("anthropic", model=a.model)
    return llm.make_backend("openai", model=a.model, base_url=a.base_url, tool_mode=a.tool_mode,
                            temperature=a.temperature)


def run_kwargs(a):
    profile = a.profile or ("full" if a.backend == "anthropic" else "basic")
    kw = {"profile": profile}
    if a.max_faces_prompt:
        kw["max_faces"] = a.max_faces_prompt
    elif a.backend == "openai":
        kw["max_faces"] = 40
    return kw
