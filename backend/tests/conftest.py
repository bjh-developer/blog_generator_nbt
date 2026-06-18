import os
import tempfile

# isolate data dir before app modules import config
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="bg_test_"))
os.environ.setdefault("PROMPT_CACHE", "0")
# force offline: tests must never hit the network/LLM even if a real key is
# exported in the shell (design._narrate would otherwise 429-retry for minutes)
os.environ["OPENROUTER_API_KEY"] = ""
