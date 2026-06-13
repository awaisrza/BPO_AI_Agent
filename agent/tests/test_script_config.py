from app.config import ScriptConfig


def test_from_script_json_maps_dashboard_shape():
    raw = {
        "label": "Medicare v2",
        "greeting": "Hi, this is Sarah.",
        "pitch": "Quick Medicare review.",
        "qualifying_questions": [
            "Do you have Part A and B?",
            "Are you 65 or older?",
        ],
        "transfer_line": "Connecting you now.",
        "not_interested_line": "Goodbye.",
        "transfer_preset": "closers-01",
        "knowledge_base": [
            {
                "topic": "Who is calling?",
                "triggers": ["who are you"],
                "answer": "Sarah from ABC Benefits.",
            }
        ],
    }
    script = ScriptConfig.from_script_json(raw)
    assert script.greeting == "Hi, this is Sarah."
    assert script.pitch == "Quick Medicare review."
    assert len(script.qualifying_questions) == 2
    assert script.transfer_preset == "closers-01"
    assert len(script.knowledge_base) == 1
    assert script.knowledge_base[0].answer == "Sarah from ABC Benefits."


def test_from_script_json_strips_empty_questions():
    raw = {
        "greeting": "Hi",
        "pitch": "Pitch",
        "qualifying_questions": ["Q1", "  ", ""],
        "transfer_line": "T",
        "not_interested_line": "N",
    }
    script = ScriptConfig.from_script_json(raw)
    assert script.qualifying_questions == ["Q1"]
