"""Import shim so ragas 0.4.x loads against langchain-community 0.4.x.

`ragas.llms.base` does an unconditional

    from langchain_community.chat_models.vertexai import ChatVertexAI

but that module was deleted when langchain-community split its integrations out
into standalone packages, so *any* `import ragas` raises ModuleNotFoundError.
Upstream tracks this as explodinggradients/ragas#2753 (still open).

The symbol is only used in a `MULTIPLE_COMPLETION_SUPPORTED` isinstance list, so
a placeholder class is sufficient: we never pass a Vertex model, the isinstance
check correctly returns False, and nothing else touches it.

Delete this module once ragas makes the import lazy.

Import it *before* anything imports ragas:

    from tests.eval import ragas_compat  # noqa: F401

NOTE: The langchain-community deprecation warning is expected and harmless.
It comes from ragas's internal imports, not our code.
"""

import sys
import types


def install() -> None:
    name = "langchain_community.chat_models.vertexai"
    if name in sys.modules:
        return
    try:
        __import__(name)
        return  # Upstream fixed it, or the real module is back.
    except ImportError:
        pass

    module = types.ModuleType(name)

    class ChatVertexAI:  # noqa: N801 - mirrors the upstream class name
        """Placeholder for the removed langchain-community Vertex chat model."""

    module.ChatVertexAI = ChatVertexAI
    sys.modules[name] = module


install()
