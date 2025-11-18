import os

from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from flask import Flask, request

# ---------- Environment Variables ----------
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]

# ---------- Slack/Bolt App ----------
app = App(
    token=SLACK_BOT_TOKEN,
    signing_secret=SLACK_SIGNING_SECRET,
)

flask_app = Flask(__name__)
handler = SlackRequestHandler(app)


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

    # Public message for everyone in the channel
    respond(
        response_type="in_channel",
        text=f"*From:* {pickup}\n*To:* {dropoff}",
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
