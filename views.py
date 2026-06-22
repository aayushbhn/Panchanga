"""HTML page routes that render the demo templates."""
from flask import render_template

from webapp import app


@app.route("/monthly-panchanga-page")
def monthly_panchanga_page():
    return render_template("monthly_panchanga.html")

@app.route("/panchanga-page")
def panchanga_page():
    return render_template("panchanga.html")
