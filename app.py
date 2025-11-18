import os
import urllib.parse
import requests

from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from flask import Flask, request

# ---------- Environment Variables ----------
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]
MAPBOX_TOKEN = os.environ["MAPBOX_TOKEN"]  # your Mapbox "pk..." token
UBER_CLIENT_ID = os.environ.get("UBER_CLIENT_ID", "fare-bot")


# ---------- Slack/Bolt App ----------
app = App(
    token=SLACK_BOT_TOKEN,
    signing_secret=SLACK_SIGNING_SECRET,
)

flask_app = Flask(__name__)
handler = SlackRequestHandler(app)


# ---------- Mapbox Geocoding ----------
def geocode_with_mapbox(address: str):
    """
    Use Mapbox to turn a text address into coordinates.

    Returns:
        {"lat": float, "lng": float} or None if not found.
    """
    url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{urllib.parse.quote(address)}.json"
    params = {
        "access_token": MAPBOX_TOKEN,
        "limit": 1,
    }

    resp = requests.get(url, params=params)
    if not resp.ok:
        return None

    data = resp.json()
    features = data.get("features")
    if not features:
        return None

    # Mapbox returns [lng, lat]
    lng, lat = features[0]["center"]
    return {"lat": lat, "lng": lng}


# ---------- Deep Link Helpers ----------
def make_uber_deeplink(
    pickup_lat,
    pickup_lng,
    drop_lat,
    drop_lng,
    pickup_address,
    dropoff_address,
):
    """
    Build an Uber deeplink with coordinates + formatted addresses.
    Uses m.uber.com/ul for cross-platform behavior.
    """
    params = {
        "action": "setPickup",
        "client_id": UBER_CLIENT_ID,
        "pickup[latitude]": pickup_lat,
        "pickup[longitude]": pickup_lng,
        "pickup[formatted_address]": pickup_address,
        "dropoff[latitude]": drop_lat,
        "dropoff[longitude]": drop_lng,
        "dropoff[formatted_address]": dropoff_address,
    }
    return "https://m.uber.com/ul/?" + urllib.parse.urlencode(params)


def make_lyft_deeplink(
    pickup_lat,
    pickup_lng,
    drop_lat,
    drop_lng,
    pickup_address,
    dropoff_address,
):
    """
    Build a Lyft deeplink with coordinates + addresses.
    """
    params = {
        "id": "lyft",
        "pickup[latitude]": pickup_lat,
        "pickup[longitude]": pickup_lng,
        "pickup[address]": pickup_address,
        "destination[latitude]": drop_lat,
        "destination[longitude]": drop_lng,
        "destination[address]": dropoff_address,
    }
    return "lyft://ridetype?" + urllib.parse.urlencode(params)


# ---------- Slash Command Handler ----------
@app.command("/fare")
def handle_fare(ack, say, command):
    """
    Usage in Slack:
        /fare 45 2nd St San Francisco to SFO
    """
    # Acknowledge so Slack doesn’t time out
    ack()

    text = (command.get("text") or "").strip()
    if " to " not in text:
        say("Format: `/fare pickup address to dropoff address`")
        return

    pickup_address, dropoff_address = text.split(" to ", 1)
    pickup_address = pickup_address.strip()
    dropoff_address = dropoff_address.strip()

    if not pickup_address or not dropoff_address:
        say("I need both a pickup and a dropoff address.")
        return

    # Geocode both addresses with Mapbox
    pickup_coords = geocode_with_mapbox(pickup_address)
    dropoff_coords = geocode_with_mapbox(dropoff_address)

    if not pickup_coords or not dropoff_coords:
        say("I couldn't find one of those locations. Try being more specific.")
        return

    uber_url = make_uber_deeplink(
        pickup_coords["lat"],
        pickup_coords["lng"],
        dropoff_coords["lat"],
        dropoff_coords["lng"],
        pickup_address,
        dropoff_address,
    )

    lyft_url = make_lyft_deeplink(
        pickup_coords["lat"],
        pickup_coords["lng"],
        dropoff_coords["lat"],
        dropoff_coords["lng"],
        pickup_address,
        dropoff_address,
    )

    say(
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
                        "text": f"*Uber*\n<{uber_url}|Open in Uber>",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Lyft*\n<{lyft_url}|Open in Lyft>",
                    },
                ],
            },
        ]
    )


# ---------- Flask Routing ----------
@flask_app.route("/slack/fare", methods=["POST"])
def slack_fare():
    """
    This is the endpoint Slack calls for the /fare command.
    Request URL in Slack should be:
        https://YOUR-RENDER-URL.onrender.com/slack/fare
    """
    return handler.handle(request)


# ---------- Local Run (optional) ----------
if __name__ == "__main__":
    # For local testing only; on Render, gunicorn runs flask_app.
    flask_app.run(host="0.0.0.0", port=3000)
