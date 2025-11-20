import os
import urllib.parse
import requests

from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from flask import Flask, request

# ---------- Environment Variables ----------
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]
MAPBOX_TOKEN = os.environ.get("MAPBOX_TOKEN")  # Mapbox "pk..." token (optional but recommended)
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
        {"lat": float, "lng": float} or None if not found or on error.
    """
    if not MAPBOX_TOKEN:
        print("MAPBOX_TOKEN is not set; skipping geocoding.", flush=True)
        return None

    url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{urllib.parse.quote(address)}.json"
    params = {
        "access_token": MAPBOX_TOKEN,
        "limit": 1,
    }

    try:
        resp = requests.get(url, params=params, timeout=5)
    except Exception as e:
        print(f"Error calling Mapbox for '{address}': {e}", flush=True)
        return None

    if not resp.ok:
        print(f"Mapbox non-200 status {resp.status_code} for '{address}'", flush=True)
        return None

    data = resp.json()
    features = data.get("features")
    if not features:
        print(f"Mapbox found no features for '{address}'", flush=True)
        return None

    # Mapbox returns [lng, lat]
    lng, lat = features[0]["center"]
    return {"lat": lat, "lng": lng}


# ---------- Deep Link Helpers ----------
def make_uber_link(pickup_address, dropoff_address, pickup_coords=None, dropoff_coords=None) -> str:
    """
    Build an Uber deep link. If coords are available, include them; otherwise, use addresses only.
    """
    params = {
        "action": "setPickup",
        "client_id": UBER_CLIENT_ID,
    }

    # Pickup
    if pickup_coords:
        params["pickup[latitude]"] = pickup_coords["lat"]
        params["pickup[longitude]"] = pickup_coords["lng"]
        params["pickup[formatted_address]"] = pickup_address
    else:
        params["pickup[formatted_address]"] = pickup_address

    # Dropoff
    if dropoff_coords:
        params["dropoff[latitude]"] = dropoff_coords["lat"]
        params["dropoff[longitude]"] = dropoff_coords["lng"]
        params["dropoff[formatted_address]"] = dropoff_address
    else:
        params["dropoff[formatted_address]"] = dropoff_address

    query = urllib.parse.urlencode(params)
    return f"https://m.uber.com/ul/?{query}"


def make_lyft_link(pickup_address, dropoff_address, pickup_coords=None, dropoff_coords=None) -> str:
    """
    Build a Lyft deep link. If coords are available, include them; otherwise, use addresses only.
    """
    params = {
        "id": "lyft",
    }

    # Pickup
    if pickup_coords:
        params["pickup[latitude]"] = pickup_coords["lat"]
        params["pickup[longitude]"] = pickup_coords["lng"]
    params["pickup[address]"] = pickup_address

    # Dropoff
    if dropoff_coords:
        params["destination[latitude]"] = dropoff_coords["lat"]
        params["destination[longitude]"] = dropoff_coords["lng"]
    params["destination[address]"] = dropoff_address

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

    try:
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

        # Try to geocode both addresses with Mapbox (but fall back if it fails)
        pickup_coords = geocode_with_mapbox(pickup)
        dropoff_coords = geocode_with_mapbox(dropoff)

        print(f"Geocoded pickup: {pickup_coords}, dropoff: {dropoff_coords}", flush=True)

        uber_url = make_uber_link(pickup, dropoff, pickup_coords, dropoff_coords)
        lyft_url = make_lyft_link(pickup, dropoff, pickup_coords, dropoff_coords)

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
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": "Links open Uber/Lyft with your trip details as much as each app supports.",
                        }
                    ],
                },
            ],
        )
    except Exception as e:
        print(f"ERROR in /fare handler: {e}", flush=True)
        respond(
            response_type="ephemeral",
            text="Sorry, something went wrong handling that request.",
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
