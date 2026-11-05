"""A meeting's job that died without saying so: killed (out of memory, say), or its host lost for good. Its meeting
fails now, so the app offers Send again within minutes, not after the API's three hours (STALE). EventBridge calls
this with Batch's own event for a failed job. A job that failed on its own has said so already, and a meeting that's
another job's now isn't this one's to change: both are left as they are.
"""

import contextlib
import os
import re
from datetime import UTC, datetime

import boto3

KEY = re.compile(r"^users/([A-Za-z0-9_-]{1,128})/meetings/([0-9A-HJKMNP-TV-Z]{26})/audio\.(m4a|mp3|wav)$")
FAILED = "Something went wrong while summarising it."  # the job's own words: the apps offer Send again

meetings = boto3.resource("dynamodb").Table(os.environ["TALLY_MEETINGS_TABLE"])


def handler(event, _context):
    detail = event["detail"]
    match = KEY.match((detail.get("parameters") or {}).get("key", ""))
    if not match:  # a summary's rewrite: the API stops waiting for one by itself (REWRITE_WAIT)
        return
    print(f"job {detail['jobId']} failed: {detail.get('statusReason')}, exit code {(detail.get('container') or {}).get('exitCode')}")
    with contextlib.suppress(meetings.meta.client.exceptions.ConditionalCheckFailedException):
        meetings.update_item(Key={"owner": match.group(1), "meeting_id": match.group(2)},
                             UpdateExpression="SET #s = :failed, #e = :e, updated_at = :t",
                             ConditionExpression="#s = :processing AND job_id = :job", ExpressionAttributeNames={"#s": "state", "#e": "error"},
                             ExpressionAttributeValues={":failed": "failed", ":e": FAILED, ":t": datetime.now(UTC).isoformat(timespec="seconds"),
                                                        ":processing": "processing", ":job": detail["jobId"]})
