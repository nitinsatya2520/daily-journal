from flask import Flask, render_template, request, redirect, session, url_for
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import base64
import json
import os

app = Flask(__name__)
app.secret_key = "your_secret_key"  # Use a strong, random key in production

# Google Sheets setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

creds_b64 = os.getenv("GOOGLE_CREDS")
if creds_b64:
    creds_json = base64.b64decode(creds_b64).decode("utf-8")
    creds_dict = json.loads(creds_json)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
else:
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)

client = gspread.authorize(creds)

spreadsheet = client.open_by_key("1YlNopozlThhYr1zAk9tXD3AAsJt43ydMDXyU_oGYGu4")
journal_sheet = spreadsheet.sheet1
user_sheet = spreadsheet.worksheet("Users")

@app.route("/")
def home():
    return render_template("login.html")

@app.route("/login", methods=["POST"])
def login():
    email = request.form["email"]
    password = request.form["password"]

    users = user_sheet.get_all_records()
    for user in users:
        if user["Email"] == email and check_password_hash(user["Password"], password):
            session["email"] = email
            return redirect("/journal")
    return "Invalid credentials"

@app.route("/logout")
def logout():
    session.pop("email", None)
    return redirect(url_for("home"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])
        join_date = datetime.now().strftime("%Y-%m-%d")
        user_sheet.append_row([name, email, password, join_date])
        return redirect("/")
    return render_template("register.html")

@app.route("/journal")
def journal():
    if "email" not in session:
        return redirect(url_for("login"))

    email = session["email"]
    all_entries = journal_sheet.get_all_records()

    entries = []
    for i, record in enumerate(all_entries, start=2):
        if record.get("Email") == email:
            record["Row"] = i  # Track row for edit/delete
            entries.append(record)

    return render_template("index.html", entries=entries)

@app.route("/submit", methods=["POST"])
def submit():
    if "email" not in session:
        return redirect("/")

    title = request.form["title"]
    entry = request.form["entry"]
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    journal_sheet.append_row([timestamp, session["email"], title, entry])
    return render_template("thankyou.html")

@app.route("/edit/<int:row>", methods=["GET", "POST"])
def edit_entry(row):
    if "email" not in session:
        return redirect("/login")

    if request.method == "POST":
        title = request.form["title"]
        entry = request.form["entry"]
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        journal_sheet.update(f"A{row}:D{row}", [[timestamp, session["email"], title, entry]])
        return redirect("/journal")

    row_values = journal_sheet.row_values(row)
    if not row_values or len(row_values) < 4:
        return "Entry not found", 404

    return render_template("edit.html", row=row, title=row_values[2], entry=row_values[3])

@app.route("/delete/<int:row>")
def delete_entry(row):
    if "email" not in session:
        return redirect("/login")
    journal_sheet.delete_rows(row)
    return redirect("/journal")

@app.route("/profile")
def profile():
    if "email" not in session:
        return redirect(url_for("login"))

    email = session["email"]

    users = user_sheet.get_all_records()
    user_data = next((u for u in users if u["Email"] == email), None)

    if not user_data:
        return "User profile not found", 404

    join_date = user_data.get("JoinDate", "Unknown")
    all_entries = journal_sheet.get_all_records()
    total_entries = sum(1 for entry in all_entries if entry["Email"] == email)
    name = user_data.get("Name", email.split("@")[0].capitalize())

    return render_template("profile.html", user={
        "email": email,
        "name": name,
        "join_date": join_date,
        "total_entries": total_entries
    })

@app.route("/change-password", methods=["GET", "POST"])
def change_password():
    if "email" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        current_password = request.form["current_password"]
        new_password = request.form["new_password"]
        confirm_password = request.form["confirm_password"]

        if new_password != confirm_password:
            return "New passwords do not match."

        users = user_sheet.get_all_records()
        for index, user in enumerate(users, start=2):  # start=2 because row 1 is header
            if user["Email"] == session["email"]:
                if check_password_hash(user["Password"], current_password):
                    hashed = generate_password_hash(new_password)
                    user_sheet.update_cell(index, 3, hashed)  # Password column index
                    return redirect("/profile")
                else:
                    return "Incorrect current password."

        return "User not found"

    return render_template("change_password.html")

if __name__ == "__main__":
    app.run(debug=True)
