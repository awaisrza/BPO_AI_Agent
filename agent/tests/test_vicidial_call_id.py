from app.vicidial import ViciDialClient, looks_like_vicidial_call_id


def test_looks_like_vicidial_call_id():
    assert looks_like_vicidial_call_id("Y0315201639000402027")
    assert looks_like_vicidial_call_id("V123456789012345678")
    assert not looks_like_vicidial_call_id("6666")
    assert not looks_like_vicidial_call_id("Thank you")


def test_extract_call_id_from_logged_in_agents_csv():
    sample = (
        "user,status,callerid\n"
        "6666,INCALL,Y0315201639000402027\n"
        "7777,PAUSED,\n"
    )
    cid = ViciDialClient._extract_call_id_from_api_text(sample, agent_user="6666")
    assert cid == "Y0315201639000402027"
