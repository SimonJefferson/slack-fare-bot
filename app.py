import os
import urllib.parse

from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from flask import Flask, request

# ---------- Environment Variables ----------
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]
UBER_CLIENT_ID = os.environ.get("UBER_CLIENT_ID", "fare-bot")


# ---------- Slack/Bolt App ----------
app = App(
    token=SLACK_BOT_TOKEN,
    signing_secret=SLACK_SIGNING_SECRET,
)

flask_app = Flask(__name__)
handler = SlackRequestHandler(app)


# ---------- Deep Link Helpers (address-only, no APIs) ----------
def make_uber_deeplink_from_addresses(pickup_address: str, dropoff_address: str) -> str:
    """
    Create an Uber deep link using plain text addresses.
    Note: Uber may or may not prefill pickup/dropoff, but this will at least open Uber
    with our intent.
    """
    params = {
        "action": "setPickup",
        "client_id": UBER_CLIENT_ID,
        "pickup[formatted_address]": pickup_address,
        "dropoff[formatted_address]": dropoff_address,
    }
    query = urllib.parse.urlencode(params)
    return f"https://m.uber.com/ul/?{query}"


def make_lyft_deeplink_from_addresses(pickup_address: str, dropoff_address: str) -> str:
    """
    Create a Lyft deep link using plain text addresses.
    """
    params = {
        "id": "lyft",
        "pickup[address]": pickup_address,
        "destination[address]": dropoff_address,
    }
    query = urllib.parse.urlencode(params)
    return f"lyft://ridetype?{query}"


# ---------- Slash Command Handler ----------
@app.command("/fare")
def handle_fare(ack, respond, command):
    """
    Usage in Slack:
        /fare 45 2nd St San Francisco to SFO
    """
    # Acknowledge immediately so Slack doesn't time out
    ack()

    text = (command.get("text") or "").strip()
    print(f"/fare called with text: {text}", flush=True)

    if " to " not in text:
        respond(
            response_type="ephemeral",
            text="Format: `/fare pickup address to dropoff address`",
        )
        return

    pickup, dropoff = text.split(" to ", 1)
    pickup = pickup.strip()
    dropoff = dropoff.strip()

    if not pickup or not dropoff:
        respond(
            response_type="ephemeral",
            text="I need both a pickup and a dropoff address.",
        )
        return

    uber_url = make_uber_deeplink_from_addresses(pickup, dropoff)
    lyft_url = make_lyft_deeplink_from_addresses(pickup, dropoff)

    # Public message for everyone in the channel, with buttons
    respond(
        response_type="in_channel",
        blocks=[
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🚕 Fare helper",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*From:* {pickup}\n*To:* {dropoff}",
                },
            },
            {"type": "divider"},
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Open in Uber",
                            "emoji": True,
                        },
                        "url": uber_url,
                        "action_id": "open_uber",
                        "style": "primary",
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Open in Lyft",
                            "emoji": True,
                        },
                        "url": lyft_url,
                        "action_id": "open_lyft",
                    },
                ],
            },
        ],
    )


# ---------- Flask Routing ----------
@flask_app.route("/slack/fare", methods=["POST"])
def slack_fare():
    """
    This is the endpoint Slack calls for the /fare command.
    Request URL in Slack must be:
        https://YOUR-RENDER-URL.onrender.com/slack/fare
    """
    return handler.handle(request)


# ---------- Local Run (optional) ----------
if __name__ == "__main__":
    # For local testing only; on Render, gunicorn runs flask_app.
    flask_app.run(host="0.0.0.0", port=3000)
