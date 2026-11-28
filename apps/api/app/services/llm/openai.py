"""OpenAI adapter (PAID, amended D14 2026-11-28): the same chat completions API as Groq.

Used as the backup after Groq (`LLM_PROVIDERS=groq,openai,template`), so it is billed only when
Groq is busy or down. Model IDs come from OPENAI_MODEL_FAST / OPENAI_MODEL_MAIN; keep both on
the cheapest current model and keep OPENAI_RPD_LIMIT set as a daily spending cap.
"""

from app.services.llm.groq import GroqLLM

OPENAI_BASE_URL = "https://api.openai.com/v1"


class OpenAILLM(GroqLLM):
    name = "openai"
    label = "OpenAI"
    base_url = OPENAI_BASE_URL
    send_temperature = False  # gpt-5 family models reject any temperature but the default
