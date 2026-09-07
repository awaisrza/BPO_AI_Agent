from app.vicidial import ViciDialClient, looks_like_vicidial_call_id


def test_looks_like_vicidial_call_id():
    assert looks_like_vicidial_call_id("Y0315201639000402027")
    assert looks_like_vicidial_call_id("V123456789012345678")
    assert looks_like_vicidial_call_id("M4050908070000012345")
    assert not looks_like_vicidial_call_id("6666")
    assert not looks_like_vicidial_call_id("Thank you")


def test_extract_call_id_from_agent_status_csv():
    sample = (
        "status,call_id,lead_id,campaign_id,calls_today,full_name\n"
        "INCALL,M4050908070000012345,12345,TESTCAMP,1,Bot Agent\n"
    )
    cid = ViciDialClient._extract_call_id_from_api_text(sample)
    assert cid == "M4050908070000012345"


def test_extract_call_id_from_logged_in_agents_csv():
    sample = (
        "user,campaign_id,session_id,status,lead_id,callerid,calls_today\n"
        "6666,TESTCAMP,8600051,INCALL,1079409,M2260919190001079409,1\n"
        "7777,TESTCAMP,8600052,PAUSED,0,,0\n"
    )
    cid = ViciDialClient._extract_call_id_from_api_text(sample, agent_user="6666")
    assert cid == "M2260919190001079409"
