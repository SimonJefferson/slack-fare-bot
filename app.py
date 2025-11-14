import os
import urllib.parse
import requests

from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from flask import Flask, request

# ---------- Environment Variables ----------
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]
GOOGLE_MAPS_API_KEY = os.environ["GOOGLE_MAPS_API_KEY"]
UBER_CLIENT_ID = os.environ.get("UBER_CLIENT_ID", "fare-bot")


# ---------- Slack/Bolt App ----------
app = App(
    token=SLACK_BOT_TOKEN,
    signing_secret=SLACK_SIGNING_SECRET,
)

flask_app = Flask(__name__)
handler = SlackRequestHandler(app)


# ---------- Geocode Helper ----------
def geocode(address: str):
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": address,
        "key": GOOGLE_MAPS_API_KEY,
    }
    resp = requests.get(url, params=params)
    data = resp.json()

    if data.get("status") != "OK" or not data.get("results"):
        return None

    loc = data["results"][0]["geometry"]["location"]
    return {"lat": loc["lat"], "lng": loc["lng"]}


# ---------- Deep Link Helpers ----------
def make_uber_deeplink(pickup, dropoff):
    params = {
        "action": "setPickup",
        "client_id": UBER_CLIENT_ID,
        "pickup[latitude]": pickup["lat"],
        "pickup[longitude]": pickup["lng"],
        "dropoff[latitude]": dropoff["lat"],
        "dropoff[longitude]": dropoff["lng"],
    }
    query = urllib.parse.urlencode(params)
    return f"https://m.uber.com/ul/?{query}"


def make_lyft_deeplink(pickup, dropoff):
    params = {
        "id": "lyft",
        "pickup[latitude]": pickup["lat"],
        "pickup[longitude]": pickup["lng"],
        "destination[latitude]": dropoff["lat"],
        "destination[longitude]": dropoff["lng"],
    }
    query = urllib.parse.urlencode(params)
    return f"lyft://ridetype?{query}"


# ---------- Slash Command Handler ----------
@app.command("/fare")
def handle_fare(ack, respond, command):
    ack()

    text = (command.get("text") or "").strip()

    if " to " not in text:
        respond("Format must be: `/fare pickup address to dropoff address`")
        return

    pickup_address, dropoff_address = text.split(" to ", 1)

    pickup = geocode(pickup_address)
    dropoff = geocode(dropoff_address)

    if not pickup or not dropoff:
        respond("I couldn’t geocode one of those addresses.")
        return

    uber_link = make_uber_deeplink(pickup, dropoff)
    lyft_link = make_lyft_deeplink(pickup, dropoff)

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
