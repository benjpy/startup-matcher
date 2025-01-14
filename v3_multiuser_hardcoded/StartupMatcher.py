import csv
import os
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file, make_response

app = Flask(__name__)

# Simulated user database (email and user ID)
USER_DATABASE = {
    "user1@example.com": "1234",
    "user2@example.com": "5678",
    "skye@gmail.com": "password"
}

# Google Sheets configuration
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1DCAXLUzBq4iUDKbhG0D624-eZn_G7PY-kJ_EshTtsVw/edit?gid=1253631369"
STARTUPS_CSV = "startups.csv"  # Local CSV file for startups

def export_google_sheet_to_csv():
    """Fetch data from Google Sheets and export it to a local CSV file."""
    from oauth2client.service_account import ServiceAccountCredentials
    import gspread

    # Define the scope and authenticate
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("service-account.json", scope)
    client = gspread.authorize(creds)

    # Open the sheet and fetch data
    sheet = client.open_by_url(GOOGLE_SHEET_URL).sheet1
    records = sheet.get_all_records()

    # Write data to local CSV
    with open(STARTUPS_CSV, "w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)

def load_startups():
    """Load startups from the local CSV file."""
    if not os.path.exists(STARTUPS_CSV):
        export_google_sheet_to_csv()

    with open(STARTUPS_CSV, "r") as file:
        reader = csv.DictReader(file)
        return list(reader)

def get_user_file(email, user_id):
    """Return the file name for the user's decision file."""
    return f"selections_{email}_{user_id}.csv"

def load_user_decisions(email, user_id):
    """Load the user's decisions from their specific file."""
    user_file = get_user_file(email, user_id)
    if os.path.exists(user_file):
        with open(user_file, "r", newline="") as file:
            reader = csv.DictReader(file)
            return {row["Order"]: row for row in reader}
    return {}

def save_user_decisions(email, user_id, decisions):
    """Save the user's decisions to their specific file."""
    user_file = get_user_file(email, user_id)
    with open(user_file, "w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["Order", "Action", "Company Name", "Company URL"])
        writer.writeheader()
        for decision in decisions.values():
            writer.writerow(decision)

@app.route("/login", methods=["GET", "POST"])
def login():
    """Render login page and handle authentication."""
    if request.method == "POST":
        email = request.form.get("email")
        user_id = request.form.get("user_id")

        if email in USER_DATABASE and USER_DATABASE[email] == user_id:
            response = make_response(redirect(url_for("index")))
            response.set_cookie("email", email)
            response.set_cookie("user_id", user_id)
            return response
        else:
            return "Invalid credentials. Please try again.", 401

    return render_template("login.html")

@app.route("/logout")
def logout():
    """Log out the user by clearing cookies."""
    response = make_response(redirect(url_for("login")))
    response.delete_cookie("email")
    response.delete_cookie("user_id")
    return response

@app.route("/")
def index():
    """Main page where users select startups."""
    email = request.cookies.get("email")
    user_id = request.cookies.get("user_id")

    if not email or not user_id or USER_DATABASE.get(email) != user_id:
        return redirect(url_for("login"))

    startups = load_startups()
    user_decisions = load_user_decisions(email, user_id)

    for startup in startups:
        if startup["Order"] not in user_decisions:
            return render_template("swipe.html", startup=startup, email=email, user_id=user_id)

    return redirect(url_for("complete_list", refreshed="true", new="0"))

@app.route("/startup/<Order>")
def startup_selection(Order):
    """Render the swipe page for a specific startup."""
    email = request.cookies.get("email")
    user_id = request.cookies.get("user_id")

    # Check if the user is logged in
    if not email or not user_id or USER_DATABASE.get(email) != user_id:
        return redirect(url_for("login"))

    # Load startups and find the selected one
    startups = load_startups()
    startup = next((s for s in startups if s["Order"] == Order), None)

    if not startup:
        return f"<h1>Startup with ID {Order} not found.</h1>", 404

    return render_template("swipe.html", startup=startup, email=email, user_id=user_id)

@app.route("/decision", methods=["POST"])
def decision():
    """Save a decision for the user."""
    email = request.cookies.get("email")
    user_id = request.cookies.get("user_id")

    if not email or not user_id or USER_DATABASE.get(email) != user_id:
        return redirect(url_for("login"))

    startup_order = request.form.get("Order")
    action = request.form.get("action")

    startups = load_startups()
    user_decisions = load_user_decisions(email, user_id)

    startup = next((s for s in startups if s["Order"] == startup_order), None)
    if startup:
        user_decisions[startup_order] = {
            "Order": startup["Order"],
            "Action": action,
            "Company Name": startup["Company Name"],
            "Company URL": startup["Company URL"],
        }
        save_user_decisions(email, user_id, user_decisions)

    return redirect(url_for("index"))

@app.route("/complete-list")
def complete_list():
    """Display the list of startups with decisions."""
    email = request.cookies.get("email")
    user_id = request.cookies.get("user_id")

    if not email or not user_id or USER_DATABASE.get(email) != user_id:
        return redirect(url_for("login"))

    # Get filter from query parameters
    decision_filter = request.args.get("filter")

    # If filter is explicitly 'None', treat it as no filter (Show All)
    if decision_filter in [None, "", "None"]:
        decision_filter = None

    startups = load_startups()
    user_decisions = load_user_decisions(email, user_id)

    # Map decisions to startups
    complete_startups = [
        {
            "order": startup["Order"],
            "decision": user_decisions.get(startup["Order"], {}).get("Action", "Pending"),
            "name": startup["Company Name"],
            "url": startup["Company URL"],
            "pitch_deck": startup.get("Pitch Deck", None),
            "selection_url": url_for("startup_selection", Order=startup["Order"])
        }
        for startup in startups
    ]

    # Apply filtering if a filter is specified
    if decision_filter:
        complete_startups = [
            s for s in complete_startups if s["decision"] == decision_filter
        ]

    # Find the first startup with a "Pending" decision
    next_pending_startup = next(
        (s for s in complete_startups if s["decision"] == "Pending"), None
    )
    back_to_swipe_url = (
        url_for("startup_selection", Order=next_pending_startup["order"])
        if next_pending_startup else url_for("index")  # Fallback to index if none
    )

    return render_template(
        "complete_list.html",
        complete_startups=complete_startups,
        decision_filter=decision_filter,
        back_to_swipe_url=back_to_swipe_url,
    )

@app.route("/download-csv")
def download_csv():
    """Allow users to download their decision file."""
    email = request.cookies.get("email")
    user_id = request.cookies.get("user_id")

    if not email or not user_id or USER_DATABASE.get(email) != user_id:
        return redirect(url_for("login"))

    user_file = get_user_file(email, user_id)
    if os.path.exists(user_file):
        return send_file(
            user_file,
            as_attachment=True,
            download_name=os.path.basename(user_file),
            mimetype="text/csv"
        )
    else:
        return "No decisions have been made yet.", 404

@app.route("/refresh", methods=["GET"])
def refresh():
    """Refresh the startups list and redirect back to the appropriate page."""
    email = request.cookies.get("email")
    user_id = request.cookies.get("user_id")

    if not email or not user_id or USER_DATABASE.get(email) != user_id:
        return redirect(url_for("login"))

    # Load the existing startups
    existing_startups = load_startups() if os.path.exists(STARTUPS_CSV) else []
    existing_orders = {startup["Order"] for startup in existing_startups}

    try:
        # Refresh the startups CSV from Google Sheets
        export_google_sheet_to_csv()
        refreshed = True
    except Exception as e:
        refreshed = False
        print(f"Error refreshing startups: {e}")

    # Load the updated startups
    updated_startups = load_startups()
    updated_orders = {startup["Order"] for startup in updated_startups}

    # Calculate the number of new startups
    new_startups_count = len(updated_orders - existing_orders)

    # Get the origin and filter from the query parameters
    origin = request.args.get("origin", "index")
    decision_filter = request.args.get("filter", None)

    # Redirect based on the origin with the new count
    if origin == "complete_list":
        return redirect(
            url_for("complete_list", refreshed=str(refreshed).lower(), new=new_startups_count, filter=decision_filter)
        )
    else:
        return redirect(
            url_for("index", refreshed=str(refreshed).lower(), new=new_startups_count)
        )

if __name__ == "__main__":
    app.run(debug=True)