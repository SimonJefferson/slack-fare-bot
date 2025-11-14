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


# ---------- Deep Link Helpers (address-only) ----------
def make_uber_deeplink_from_addresses(pickup_address: str, dropoff_address: str) -> str:
    """
    Create an Uber deep link using plain text addresses.
    Uses m.uber.com/ul which works cross-platform.
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
    Uses the native lyft:// scheme.
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
    # Acknowledge the command so Slack doesn’t time out
    ack()

    text = (command.get("text") or "").strip()

    # Expect: "pickup address to dropoff address"
    if " to " not in text:
        respond("Format must be: `/fare pickup address to dropoff address`")
        return

    pickup_address, dropoff_address = text.split(" to ", 1)
    pickup_address = pickup_address.strip()
    dropoff_address = dropoff_address.strip()

    if not pickup_address or not dropoff_address:
        respond("I need both a pickup and dropoff address.")
        return

    uber_link = make_uber_deeplink_from_addresses(pickup_address, dropoff_address)
    lyft_link = make_lyft_deeplink_from_addresses(pickup_address, dropoff_address)

    # Respond with a Block Kit message
    respond(
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*From:* {pickup_address}\n*To:* {dropoff_address}",
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Uber*\n<{uber_link}|Open in Uber>",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Lyft*\n<{lyft_link}|Open in Lyft>",
                    },
                ],
            },
        ]
    )


# ---------- Flask Routing ----------
@flask_app.route("/slack/fare", methods=["POST"])
def slack_fare():
    return handler.handle(request)


# ---------- Local Run (optional) ----------
if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=3000)

