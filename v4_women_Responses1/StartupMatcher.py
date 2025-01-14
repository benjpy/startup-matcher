import csv
import os
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file, make_response
from oauth2client.service_account import ServiceAccountCredentials
import gspread

# Website
# http://127.0.0.1:5000

# Ben Login
# ID = WHM25INV4568

app = Flask(__name__)

# Define the folder for storing user selection files
SELECTIONS_FOLDER = "selections"

# Ensure the selections folder exists
if not os.path.exists(SELECTIONS_FOLDER):
    os.makedirs(SELECTIONS_FOLDER)

# Google Sheets configuration
STARTUPS_CSV = "startups.csv"
# GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1DCAXLUzBq4iUDKbhG0D624-eZn_G7PY-kJ_EshTtsVw/edit?gid=1253631369"
# GOOGLE_SHEET_URL_USERS = "https://docs.google.com/spreadsheets/d/13MdnoRcH6uwWCADivSc23Vn9cPOyd7bWxrdSh75Jhz0/edit?gid=427040127"

# Women's Health Matchup Sheets
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1fUhno3fxecM11b13Uk2vQlI7mHOGvUziD9IWpaD-BwA/edit?resourcekey=&gid=1776385501#gid=1776385501"
GOOGLE_SHEET_URL_USERS = "https://docs.google.com/spreadsheets/d/1UwpKGOhhEGqxMMs9U6OwikiaiaU3OSwbZgOS2-w8vOU/edit?resourcekey=&gid=942432365#gid=942432365"

# Google Cloud Service Account Email
GOOGLE_ACCOUNT = "https://console.cloud.google.com/apis/credentials?authuser=1&inv=1&invt=Abmxwg&project=startupmatcher-447623"
GOOGLE_CLOUD_SERVICE_ACCOUNT_EMAIL = "startupmatcher-service-account@startupmatcher-447623.iam.gserviceaccount.com"

# Initialize the user database
USER_DATABASE = {}


def load_users_from_sheet():
    global USER_DATABASE
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("service-account.json", scope)
        client = gspread.authorize(creds)

        # Open the sheet and fetch data from the "IDs" tab
        sheet = client.open_by_url(GOOGLE_SHEET_URL_USERS).worksheet("IDs")
        records = sheet.get_all_records()
        
        # Debugging log to check data
        # print("Records loaded from Google Sheet:", records)

        USER_DATABASE = {
            record["ID"]: {"email": record["Email"]}
            for record in records
            if record.get("ID") and record.get("Email")
        }

        print(f"Loaded {len(USER_DATABASE)} users from Google Sheet.")
    except Exception as e:
        print(f"Error loading users from Google Sheet: {e}")
        USER_DATABASE = {}


def export_google_sheet_to_csv():
    """Fetch data from Google Sheets and export it to a local CSV file."""
    try:
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
    except Exception as e:
        print(f"Error exporting Google Sheet to CSV: {e}")


def load_startups():
    """Load startups from the local CSV file."""
    if not os.path.exists(STARTUPS_CSV):
        export_google_sheet_to_csv()

    with open(STARTUPS_CSV, "r") as file:
        reader = csv.DictReader(file)
        records = list(reader)
        print("Loaded startups:", records)  # Add this line for debugging
        return records


def get_user_file(user_id):
    """Return the file path for the user's decision file in the selections folder."""
    return os.path.join(SELECTIONS_FOLDER, f"selections_{user_id}.csv")

def load_user_decisions(user_id):
    """Load the user's decisions from their specific file."""
    user_file = get_user_file(user_id)
    if os.path.exists(user_file):
        with open(user_file, "r", newline="") as file:
            reader = csv.DictReader(file)
            return {row["Order"]: row for row in reader}
    return {}

def save_user_decisions(user_id, decisions):
    """Save the user's decisions to their specific file."""
    user_file = get_user_file(user_id)
    with open(user_file, "w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["Order", "Action", "Company Name", "Company URL"])
        writer.writeheader()
        for decision in decisions.values():
            writer.writerow(decision)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Render login page and handle authentication."""
    if request.method == "POST":
        user_id = request.form.get("user_id")

        if user_id in USER_DATABASE:
            response = make_response(redirect(url_for("index")))
            response.set_cookie("user_id", user_id)
            return response
        else:
            return "Invalid ID. Please try again.", 401

    return render_template("login.html")


@app.route("/logout")
def logout():
    """Log out the user by clearing cookies."""
    response = make_response(redirect(url_for("login")))
    response.delete_cookie("user_id")
    return response


@app.route("/")
def index():
    """Main page where users select startups."""
    user_id = request.cookies.get("user_id")

    if not user_id or user_id not in USER_DATABASE:
        return redirect(url_for("login"))

    startups = load_startups()
    user_decisions = load_user_decisions(user_id)

    for startup in startups:
        if startup["Order"] not in user_decisions:
            return render_template("swipe.html", startup=startup, user_id=user_id)

    return redirect(url_for("complete_list"))


@app.route("/startup/<Order>")
def startup_selection(Order):
    """Render the swipe page for a specific startup."""
    user_id = request.cookies.get("user_id")

    if not user_id or user_id not in USER_DATABASE:
        return redirect(url_for("login"))

    startups = load_startups()
    startup = next((s for s in startups if s["Order"] == Order), None)

    if not startup:
        return f"<h1>Startup with ID {Order} not found.</h1>", 404

    return render_template("swipe.html", startup=startup, user_id=user_id)


@app.route("/decision", methods=["POST"])
def decision():
    """Save a decision for the user."""
    user_id = request.cookies.get("user_id")

    if not user_id or user_id not in USER_DATABASE:
        return redirect(url_for("login"))

    startup_order = request.form.get("Order")
    action = request.form.get("action")

    startups = load_startups()
    user_decisions = load_user_decisions(user_id)

    startup = next((s for s in startups if s["Order"] == startup_order), None)
    if startup:
        user_decisions[startup_order] = {
            "Order": startup["Order"],
            "Action": action,
            "Company Name": startup["Company Name"],
            "Company URL": startup["Company URL"],
        }
        save_user_decisions(user_id, user_decisions)

    return redirect(url_for("index"))


@app.route("/complete-list")
def complete_list():
    """Display the list of startups with decisions."""
    user_id = request.cookies.get("user_id")

    if not user_id or user_id not in USER_DATABASE:
        return redirect(url_for("login"))

    decision_filter = request.args.get("filter")

    if decision_filter in [None, "", "None"]:
        decision_filter = None

    startups = load_startups()
    user_decisions = load_user_decisions(user_id)

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

    if decision_filter:
        complete_startups = [
            s for s in complete_startups if s["decision"] == decision_filter
        ]

    next_pending_startup = next(
        (s for s in complete_startups if s["decision"] == "Pending"), None
    )
    back_to_swipe_url = (
        url_for("startup_selection", Order=next_pending_startup["order"])
        if next_pending_startup else url_for("index")
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
    user_id = request.cookies.get("user_id")

    if not user_id or user_id not in USER_DATABASE:
        return redirect(url_for("login"))

    user_file = get_user_file(user_id)
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
    user_id = request.cookies.get("user_id")

    if not user_id or user_id not in USER_DATABASE:
        return redirect(url_for("login"))

    existing_startups = load_startups() if os.path.exists(STARTUPS_CSV) else []
    existing_orders = {startup["Order"] for startup in existing_startups}

    try:
        export_google_sheet_to_csv()
        refreshed = True
    except Exception as e:
        refreshed = False
        print(f"Error refreshing startups: {e}")

    updated_startups = load_startups()
    updated_orders = {startup["Order"] for startup in updated_startups}

    new_startups_count = len(updated_orders - existing_orders)

    origin = request.args.get("origin", "index")
    decision_filter = request.args.get("filter", None)

    if origin == "complete_list":
        return redirect(
            url_for("complete_list", refreshed=str(refreshed).lower(), new=new_startups_count, filter=decision_filter)
        )
    else:
        return redirect(
            url_for("index", refreshed=str(refreshed).lower(), new=new_startups_count)
        )


if __name__ == "__main__":
    load_users_from_sheet()
    app.run(debug=True)