import os

from cs50 import SQL
import sqlite3 as sql
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)
#app.config["DEBUG"] = True


# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Shows portfolio of stocks"""
    # Get UserID from current login session
    UserId = session["user_id"]
    # Get otherInfo to use in portfolio overview
    OtherInfo = db.execute("SELECT * FROM users WHERE id = ?", UserId)
    username = OtherInfo[0]["username"]
    cash = OtherInfo[0]["cash"]

    # Select symbols of current holdings
    symbols = db.execute("SELECT * FROM purchase_records WHERE UserID = ?", UserId)

    if not symbols:
        return render_template("index.html", cash=cash, username=username)

    SumOfStocks = db.execute(
        "SELECT SUM(HoldingsValue) AS SumOfStocks FROM purchase_records WHERE UserID = ? GROUP BY UserID", UserId)

    SumOfAllHoldings = SumOfStocks[0]["SumOfStocks"] + cash

    # Finally extract from database and show current holdings for user
    try:
        con = sql.connect("finance.db")
        con.row_factory = sql.Row
        curs = con.cursor()
        output_details = "SELECT Symbol, Name, SUM(Shares), Price, SUM(HoldingsValue) AS SUMS FROM purchase_records WHERE UserID = {} GROUP BY Symbol HAVING SUM(Shares)>0".format(
            UserId)
        curs.execute(output_details)
        rows = curs.fetchall()

    except sql.Error as error:
        print("Failed to select multiple records of sqlite table", error)
    finally:
        if con:
            con.close()
            print("The SQLite connection is closed")

    return render_template("index.html", rows=rows, cash=cash, username=username, SumOfAllHoldings=usd(SumOfAllHoldings), SumOfStocks=usd(SumOfStocks[0]['SumOfStocks']))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":

        # Check if userinput in symbol is empty
        if not request.form.get("symbol"):
            return apology("must provide symbol input")

        # Check if symbol is found by api call (lookup function)
        quote = lookup(request.form.get("symbol"))
        print(quote)
        if quote == None:
            return apology("Symbol not found")

        # Check if userinput is positive integer
        if request.form.get("shares"):
            try:
                number = int(request.form.get("shares"))
                if number < 0:
                    return apology("that's not a positive number. Try again: ")
            except ValueError:
                return apology("Share count is not an integer. Try again: ")

        # Calculate cost of purchage
        cost = quote["price"]*number

        # Query holding for username
        cash_balance = db.execute("SELECT cash, username FROM users WHERE id = ?", session["user_id"])

        if cost > cash_balance[0]["cash"]:
            return apology("Current holding is not sufficient to complete stock purchase")

        else:
            # Insert purchase info into purchases table
            db.execute("INSERT INTO purchase_records (UserID, Symbol, Name, Shares, Price, MarketCap, HoldingsValue, Time, LatestPrice, LatestMarketCap, LatestHoldingsValue, PERCENTAGE) VALUES(?,?,?,?,?,?,?, CURRENT_TIMESTAMP, ?,?,?,?)",
                       session["user_id"], quote["symbol"], quote["name"], number, quote["price"], 0, cost, 0,0,0,0)

            # Calculate updated cash balance
            cash_balance_new = cash_balance[0]["cash"] - cost

            # Modify holding for username
            db.execute("UPDATE users SET cash = ? WHERE id = ?", cash_balance_new, session["user_id"])

            return render_template("buy.html", symbol=quote["symbol"], name=quote["name"], number=number, price=usd(quote["price"]), cost=usd(cost), cash_balance_new=usd(cash_balance_new))

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    # Get UserID from current login session
    UserId = session["user_id"]
    # Get otherInfo to use in portfolio overview
    OtherInfo = db.execute("SELECT username, cash FROM users WHERE id = ?", UserId)
    username = OtherInfo[0]["username"]

    # Finally extract from database and show current holdings for user
    try:
        con = sql.connect("finance.db")
        con.row_factory = sql.Row
        curs = con.cursor()
        output_details = "SELECT Symbol, Name, Shares, Price, time FROM purchase_records WHERE UserID = {}".format(UserId)
        curs.execute(output_details)
        rows = curs.fetchall()

    except sql.Error as error:
        print("Failed to select multiple records of sqlite table", error)
    finally:
        if con:
            con.close()
            print("The SQLite connection is closed")

    return render_template("history.html", rows=rows, username=username)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 401)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 401)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]['hash'], request.form.get("password")):
            return apology("invalid username and/or password", 401)

        # Remember which user has logged in
        session["user_id"] = rows[0]['id']

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("must provide symbol input")

        quote = lookup(request.form.get("symbol"))
        if quote == None:
            return apology("Symbol not found")

        return render_template("quoted.html", name=quote["name"], price=usd(quote["price"]), symbol=quote["symbol"])

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Ensure password confirmation was submitted
        elif not request.form.get("confirmation"):
            return apology("must provide password confirmation", 400)

        # Ensure passwords match
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords do not match", 400)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get(
            "username"))

        # Check if username already exists
        if len(rows) == 1:
            return apology("username already exist", 400)

        # Insert new user into users table
        db.execute("INSERT INTO users (username, hash) VALUES(?,?)", request.form.get(
            "username"), generate_password_hash(request.form.get("password")))

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/password", methods=["GET", "POST"])
def password():
    """Register user"""
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must current provide password", 403)

        # Ensure new password is submitted
        elif not request.form.get("new_password"):
            return apology("must provide new password", 403)

        # Ensure passwords does not match
        elif request.form.get("password") == request.form.get("new_password"):
            return apology("Current and new password should not match", 403)

        # Query database for username
        rows = db.execute("SELECT hash FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        try:
            # Insert new user into users table
            db.execute("UPDATE users SET hash = ? WHERE username = ?", generate_password_hash(
                request.form.get("new_password")), request.form.get("username"))
        except sql.Error as error:
            print("Failed to select multiple records of sqlite table", error)

        # Redirect user to home page
        return redirect("/login")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("password.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # Get UserID from current login session
    UserId = session["user_id"]

    # Get symbols for current holdings to dropdown list in html
    try:
        con = sql.connect("finance.db")
        con.row_factory = sql.Row
        curs = con.cursor()
        output_details = "SELECT Symbol FROM purchase_records WHERE UserID = {} GROUP BY Symbol HAVING SUM(Shares) > 0".format(
            UserId)
        print(output_details)
        curs.execute(output_details)
        rows = curs.fetchall()
    except sql.Error as error:
        print("Failed to select multiple records of sqlite table", error)
    finally:
        if con:
            con.close()
            print("The SQLite connection is closed")

    if request.method == "POST":
        # Check if userinput in symbol is empty
        if not request.form.get("symbol"):
            return apology("must provide symbol input", 403)

        # Check if symbol is found by api call (lookup function)
        quote = lookup(request.form.get("symbol"))

        if quote == None:
            return apology("Symbol not found", 403)

        # Check if userinput is positive integer
        if request.form.get("shares"):
            try:
                number = int(request.form.get("shares"))
                if number < 0:
                    return apology("that's not a positive number. Try again: ")
            except ValueError:
                return apology("Share count is not an integer. Try again: ")

        # Query nr of shares for the symbol which needs to be sold for the current username
        SumOfShares = db.execute(
            "SELECT SUM(Shares) AS SumOfShares FROM purchase_records WHERE UserID = ? AND Symbol = ? GROUP BY Symbol", UserId, request.form.get("symbol"))

        # Calculate sale amount
        sale = quote["price"]*number

        if number > int(SumOfShares[0]["SumOfShares"]):
            return apology("You dont own that many shares of this stock !")

        else:
            # Insert purchase info into purchases table
            db.execute("INSERT INTO purchase_records (UserID, Symbol, Name, Shares, Price, MarketCap, HoldingsValue, Time, LatestPrice, LatestMarketCap, LatestHoldingsValue, PERCENTAGE) VALUES(?,?,?,?,?,?,?, CURRENT_TIMESTAMP, ?,?,?,?)",
                       session["user_id"], quote["symbol"], quote["name"], -1*number, quote["price"], 0, -sale, 0,0,0,0)

            # Query holding for username
            cash_balance = db.execute("SELECT cash, username FROM users WHERE id = ?", session["user_id"])

            # Calculate updated cash balance (increase of cash)
            cash_balance_new = cash_balance[0]["cash"] + sale

            # Modify holding for username
            db.execute("UPDATE users SET cash = ? WHERE id = ?", cash_balance_new, session["user_id"])

            # Redirect user to home page
            return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("sell.html", rows=rows)

if __name__ == "__main__":
 port = int(os.environ.get("PORT", 8080))
 app.run(host="0.0.0.0", port=port)
