from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel

from src.graph.graph import Graph


def test_short_marketplace_question_returns_readable_guidance():
    graph = Graph(config={})
    graph.compile()
    result = graph.invoke(
        "Hello",
        ctx=InvocationContext(caller_trust_level=TrustLevel.VERIFIED_EXTERNAL),
        input_context={"conversation_history": []},
    )
    assert result["status"] == "success"
    assert result["output"].startswith("Career support request could not be processed.")
    assert "too short" in result["output"]


def test_success_marketplace_output_is_readable_but_api_stays_structured():
    graph = Graph(config={})
    formatted_output = {
        "route": "interview_preparation",
        "response": {
            "introduction": "Use this checklist to prepare for your interview.",
            "checklist_items": [{"item": "Research the employer", "rationale": "Shows preparation."}],
        },
        "citations": [{"citation": "Career Guide section 3"}],
        "warnings": [],
        "advisory_notice": "Advisory career-centre support only.",
    }
    api_result = graph.get_output({"formatted_output": formatted_output})
    marketplace_result = graph.get_output(
        {"formatted_output": formatted_output, "input_context": {"conversation_history": []}}
    )
    assert api_result.get("output", api_result.get("formatted_output")) == formatted_output
    assert marketplace_result["output"].startswith("Career support guidance prepared.")
    assert "Research the employer" in marketplace_result["output"]
    assert isinstance(marketplace_result["output"], str)
