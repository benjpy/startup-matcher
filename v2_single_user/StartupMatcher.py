import csv
import os
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file
from oauth2client.service_account import ServiceAccountCredentials
import gspread

app = Flask(__name__)

# Google Sheets configuration
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1DCAXLUzBq4iUDKbhG0D624-eZn_G7PY-kJ_EshTtsVw/edit?gid=1253631369"


# Output CSV file to store user decisions
OUTPUT_CSV = "user_decisions.csv"

# Store investor decisions temporarily in memory
decisions = {}  # Declare this globally before using it in functions

# Function to load existing decisions
def load_existing_decisions():
    """Load existing decisions from the output CSV into the decisions dictionary."""
    global decisions
    if os.path.exists(OUTPUT_CSV):
        with open(OUTPUT_CSV, "r", newline="") as file:
            reader = csv.DictReader(file)
            for row in reader:
                if row["Order"] and row["Action"]:  # Ensure valid data
                    decisions[row["Order"]] = row["Action"]

# Function to initialize the output CSV
def initialize_output_csv():
    """Create the decisions CSV file if it doesn't exist."""
    if not os.path.exists(OUTPUT_CSV):
        with open(OUTPUT_CSV, "w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow([
                "Order",
                "Company Name",
                "Company URL",
                "Company introduction (max. 300 characters / 40 words)",
                "HQ Country",
                "Investment Goal",
                "Notable investors in your company (max 5 - optional)",
                "Website Upgrade",
                "Seeking Upgrade",
                "Pitch Deck",
                "Action"
            ])


# Load existing decisions into memory
load_existing_decisions()


STARTUPS_CSV = "startups.csv"  # Local CSV file for startups

def export_google_sheet_to_csv():
    """Fetch data from Google Sheets and export it to a local CSV file."""
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

    print("Exported Google Sheet data to startups.csv")

def load_startups():
    """Load startups from the local CSV file."""
    if not os.path.exists(STARTUPS_CSV):
        print("Local CSV not found. Exporting data from Google Sheets...")
        export_google_sheet_to_csv()

    # Load data from the local CSV
    startups = []
    with open(STARTUPS_CSV, "r") as file:
        reader = csv.DictReader(file)
        for row in reader:
            startups.append(row)
    return startups

@app.route("/")
def index():
    try:
        startups = load_startups()
    except FileNotFoundError as e:
        return f"<h1>Error:</h1><p>{str(e)}</p>", 500
    except Exception as e:
        import traceback
        return f"<h1>Unexpected Error:</h1><pre>{traceback.format_exc()}</pre>", 500

    # Iterate through startups and find the first one without a decision
    for startup in startups:
        if startup.get("Order") not in decisions:  # Check if the startup's Order is not in decisions
            return render_template("swipe.html", startup=startup)

    # If all startups have decisions, show the complete page
    return render_template("complete.html")

@app.route("/refresh")
def refresh_csv():
    """Refresh the startups CSV from Google Sheets and calculate new entries."""
    try:
        # Load the existing startups
        existing_startups = load_startups() if os.path.exists(STARTUPS_CSV) else []
        existing_ids = {startup.get("Order") for startup in existing_startups}

        # Refresh the CSV by exporting data from Google Sheets
        export_google_sheet_to_csv()

        # Load the updated startups
        updated_startups = load_startups()
        updated_ids = {startup.get("Order") for startup in updated_startups}

        # Calculate the number of new startups
        new_startups_count = len(updated_ids - existing_ids)

        # Redirect back to the referring page with a query parameter
        return redirect(f"{request.referrer}?refreshed=true&new={new_startups_count}")
    except Exception as e:
        return f"Error refreshing data: {str(e)}", 500

@app.route("/meet-list")
def meet_list():
    # Filter startups with "Meet" decision
    meet_startups = [
        {"name": startup["Company Name"], "url": startup["Website Upgrade"]}
        for Order, action in decisions.items()
        if action == "Meet"
        for startup in load_startups()
        if startup["Order"] == Order
    ]

    # Render the meet list template
    return render_template("meet_list.html", meet_startups=meet_startups)

@app.route("/complete-list")
def complete_list():
    # Get the filter from the query parameters
    decision_filter = request.args.get("filter")

    # Load all startups
    startups = load_startups()

    # Map decisions to startups
    complete_startups = [
        {
            "order": startup["Order"],  # Pass the Order value to the dictionary
            "decision": decisions.get(startup["Order"], "Pending"),
            "name": startup["Company Name"],
            "url": startup["Company URL"],
            "pitch_deck": startup.get("Pitch Deck", None),
            "selection_url": f"/startup/{startup['Order']}"  # URL to modify choice
        }
        for startup in startups
    ]

    # Apply filtering if a filter is specified
    if decision_filter:
        complete_startups = [
            startup for startup in complete_startups if startup["decision"] == decision_filter
        ]

    return render_template("complete_list.html", complete_startups=complete_startups, decision_filter=decision_filter)

@app.route("/startup/<Order>")
def startup_selection(Order):
    startups = load_startups()
    startup = next((s for s in startups if s["Order"] == Order), None)

    if not startup:
        return f"<h1>Startup with ID {Order} not found.</h1>", 404

    return render_template("swipe.html", startup=startup)

@app.route("/decision", methods=["POST"])
def decision():
    data = request.form
    startup_order = data.get("Order")  # Get the startup Order from the form
    action = data.get("action")  # Get the selected action (Pass, Interested, Meet)

    startups = load_startups()
    startup = next((s for s in startups if s.get("Order") == startup_order), None)

    if startup:
        # Update the decision in memory
        decisions[startup_order] = action

        # Read the existing CSV and update the decision
        rows = []
        found = False
        if os.path.exists(OUTPUT_CSV):
            with open(OUTPUT_CSV, "r", newline="") as file:
                reader = csv.DictReader(file)
                for row in reader:
                    if row["Order"] == startup_order:
                        row["Action"] = action
                        found = True
                    rows.append(row)

        # If the startup is not in the CSV, add it
        if not found:
            rows.append({
                "Order": startup.get("Order", "Unknown"),
                "Company Name": startup.get("Company Name", "Unknown"),
                "Company URL": startup.get("Company URL", "N/A"),
                "Company introduction (max. 300 characters / 40 words)": startup.get("Company introduction (max. 300 characters / 40 words)", "N/A"),
                "HQ Country": startup.get("HQ Country", "N/A"),
                "Investment Goal": startup.get("Investment Goal", "N/A"),
                "Notable investors in your company (max 5 - optional)": startup.get("Notable investors in your company (max 5 - optional)", "N/A"),
                "Website Upgrade": startup.get("Website Upgrade", "N/A"),
                "Seeking Upgrade": startup.get("Seeking Upgrade", "N/A"),
                "Pitch Deck": startup.get("Pitch Deck", "N/A"),
                "Action": action
            })

        # Write the updated data back to the CSV
        with open(OUTPUT_CSV, "w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=[
                "Order",
                "Action",
                "Company Name",
                "Company URL",
                "Company introduction (max. 300 characters / 40 words)",
                "HQ Country",
                "Investment Goal",
                "Notable investors in your company (max 5 - optional)",
                "Website Upgrade",
                "Seeking Upgrade",
                "Pitch Deck"
            ])
            writer.writeheader()
            writer.writerows(rows)

    return redirect(url_for("index"))


@app.route("/download-csv")
def download_csv():
    """Send the user_decisions.csv file for download."""
    if os.path.exists(OUTPUT_CSV):
        return send_file(
            OUTPUT_CSV,
            as_attachment=True,
            download_name="user_decisions.csv",
            mimetype="text/csv"
        )
    else:
        return "No decisions have been made yet.", 404

# Admin route to view decisions
@app.route("/admin")
def admin():
    return jsonify(decisions)


# Initialize CSV and load decisions
initialize_output_csv()
load_existing_decisions()
print("Decisions loaded:", decisions)

if __name__ == "__main__":
    app.run(debug=True)