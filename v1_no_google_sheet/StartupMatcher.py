import csv
import os
import glob
from flask import Flask, render_template, request, redirect, url_for, jsonify
from jinja2 import Environment

app = Flask(__name__)
app.jinja_env.filters['truncatewords'] = lambda value, words, suffix='...': ' '.join(value.split()[:words]) + (suffix if len(value.split()) > words else '')

# Output CSV file to store user decisions
OUTPUT_CSV = "user_decisions.csv"

# Function to initialize the output CSV
def initialize_output_csv():
    if not os.path.exists(OUTPUT_CSV):
        with open(OUTPUT_CSV, "w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["ID", "Name", "Action"])  # Add column headers

# Call the function to initialize the CSV file on startup
initialize_output_csv()

# Function to get the latest CSV from the Downloads folder
def get_latest_csv(folder_path):
    csv_files = glob.glob(os.path.join(folder_path, "*.csv"))
    if not csv_files:
        raise FileNotFoundError("No CSV files found in the folder.")
    csv_files.sort(key=os.path.getmtime, reverse=True)
    return csv_files[0]

# Load startup profiles from the most recent CSV
def load_startups():
    downloads_folder = os.path.expanduser("~/Downloads")  # Path to Downloads folder
    csv_file = get_latest_csv(downloads_folder)           # Get the latest CSV
    startups = []
    with open(csv_file, "r") as file:
        reader = csv.DictReader(file)
        for row in reader:
            startups.append(row)
    return startups

# Store investor decisions temporarily in memory
decisions = {}

@app.route("/")
def index():
    try:
        startups = load_startups()
    except FileNotFoundError as e:
        return f"<h1>Error:</h1><p>{str(e)}</p>", 500
    except Exception as e:
        return f"<h1>Unexpected Error:</h1><p>{str(e)}</p>", 500

    for startup in startups:
        if startup["ID"] not in decisions:
            return render_template("swipe.html", startup=startup)

    return render_template("complete.html")

@app.route("/decision", methods=["POST"])
def decision():
    data = request.form
    startup_id = data.get("id")
    action = data.get("action")

    # Load the startups to get additional details
    startups = load_startups()
    startup = next((s for s in startups if s.get("ID") == startup_id), None)

    if startup:
        # Record the decision in memory
        decisions[startup_id] = action

        # Append the decision to the output CSV
        with open(OUTPUT_CSV, "a", newline="") as file:
            writer = csv.writer(file)
            writer.writerow([
                startup.get("Company Name", "Unknown Company Name"),
                startup.get("Company URL", "N/A"),
                startup.get("Company introduction (max. 300 characters / 40 words)", "N/A"),
                startup.get("HQ Country", "N/A"),
                startup.get("Investment Goal", "N/A"),
                startup.get("Notable investors in your company (max 5 - optional)", "N/A"),
                startup.get("Website Upgrade", "N/A"),
                startup.get("Seeking Upgrade", "N/A"),
                startup.get("Pitch Deck", "N/A"),
                action  # User's decision (Interested, Pass, or Meet)
            ])

    return redirect(url_for("index"))

# Admin route to view decisions
@app.route("/admin")
def admin():
    return jsonify(decisions)

if __name__ == "__main__":
    app.run(debug=True)