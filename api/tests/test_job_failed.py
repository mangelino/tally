"""A job killed without a word fails its meeting, and only one that's still its own."""

import os

os.environ.setdefault("AWS_DEFAULT_REGION", "eu-north-1")
os.environ.setdefault("TALLY_MEETINGS_TABLE", "m")
import job_failed  # noqa: E402

KEY = "users/0b6e4f2a-5c1d-4e8b-9a3f-7d2c6e1b4a90/meetings/01M5JHFTFH01KXC4V2P9JNFA54/audio.m4a"
ROW = ("0b6e4f2a-5c1d-4e8b-9a3f-7d2c6e1b4a90", "01M5JHFTFH01KXC4V2P9JNFA54")


class ConditionalCheckFailedException(Exception):
    pass


class FakeMeetings:
    meta = type("Meta", (), {"client": type("Client", (), {"exceptions": type("E", (), {"ConditionalCheckFailedException": ConditionalCheckFailedException})})})

    def __init__(self, **row):
        self.row = row

    def update_item(self, Key, ExpressionAttributeValues, ConditionExpression, **_):
        assert (Key["owner"], Key["meeting_id"]) == ROW
        if (self.row["state"], self.row["job_id"]) != ("processing", ExpressionAttributeValues[":job"]):
            raise ConditionalCheckFailedException()
        self.row |= {"state": "failed", "error": ExpressionAttributeValues[":e"]}


def failed(job, key=KEY):
    return {"detail": {"jobId": job, "status": "FAILED", "statusReason": "Essential container in task exited", "parameters": {"key": key},
                       "container": {"exitCode": 137}}}


def test_a_killed_job_fails_its_meeting(monkeypatch):
    monkeypatch.setattr(job_failed, "meetings", table := FakeMeetings(state="processing", job_id="j1"))
    job_failed.handler(failed("j1"), None)
    assert table.row["state"] == "failed" and table.row["error"].startswith("Something went wrong")


def test_a_meeting_another_job_has_or_one_already_done_is_left_alone(monkeypatch):
    monkeypatch.setattr(job_failed, "meetings", table := FakeMeetings(state="processing", job_id="j2"))
    job_failed.handler(failed("j1"), None)  # sent again meanwhile: j2's now
    assert table.row["state"] == "processing"
    monkeypatch.setattr(job_failed, "meetings", table := FakeMeetings(state="ready", job_id="j1"))
    job_failed.handler(failed("j1"), None)
    assert table.row["state"] == "ready"


def test_a_rewrite_is_not_a_meetings_run(monkeypatch):
    monkeypatch.setattr(job_failed, "meetings", None)  # not touched
    job_failed.handler(failed("j1", KEY.replace("audio.m4a", "rewrite")), None)
