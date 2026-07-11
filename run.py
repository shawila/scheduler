import os

from app import create_app

app = create_app()

if __name__ == '__main__':
    # Dev-only entry point; production uses gunicorn on port 5000 (see Dockerfile)
    app.run(debug=True, port=int(os.environ.get('PORT', 3032)))

