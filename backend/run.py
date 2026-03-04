"""
run.py
Entry point for the Flask development server.
In production, use Gunicorn:
    gunicorn --bind 0.0.0.0:5000 --workers 4 --timeout 120 run:app
"""

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5005,
        debug=True,      # Set False in production
        use_reloader=True,
    )