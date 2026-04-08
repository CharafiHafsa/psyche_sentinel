# CogniSec Platform (Psyche Sentinel UI) 🧠🛡️

A Next-Generation Insider Threat & Awareness Platform. This system utilizes a lightweight C2 endpoint architecture, behavioral machine learning, and zero-knowledge credential testing to close the recognition-action gap in enterprise cybersecurity.

## 🚀 Getting Started (Local Development Setup)

Welcome to the team! Follow these exact steps to get the platform running on your local machine.

### 1. Prerequisites
* **Python 3.10+** installed on your system.
* **PostgreSQL** installed and running locally.
* **Git** installed.

### 2. Clone the Repository
```bash
git clone [https://github.com/YourUsername/cognisec-platform.git](https://github.com/YourUsername/cognisec-platform.git)
cd cognisec-platform
```

### 3. Setup the Virtual Environment
Always isolate your dependencies. Do not install packages globally.
# Create the virtual environment
``` python -m venv venv ```

# Activate it (Windows)
``` venv\Scripts\activate ```
# Activate it (Mac/Linux)
source venv/bin/activate

### 4. Install Dependencies
``` Bash
pip install -r requirements.txt ```

### 5. Database Configuration
You must create the local PostgreSQL database before running the app.

Open your Postgres terminal (psql) or pgAdmin.

Run the following SQL command:
CREATE DATABASE cognisec_db;

Note: Ensure the username and password in cognisec/settings.py match your local Postgres credentials.

### 6. Run Migrations & Start the Server
``` Bash
# Apply the database schema
python manage.py migrate ``` 

# Start the development server
``` python manage.py runserver
Visit http://127.0.0.1:8000/ in your browser to see the Landing Page.
Visit http://127.0.0.1:8000/ui-kit/ to access the Master Component Catalog.```

Team Architecture & Workflow
To prevent Git merge conflicts, our platform is divided into isolated Django apps. You will work primarily within your assigned app but will inherit the global design from the core app.

App Assignments
core (Shared) - Global UI Kit, Authentication, Base Layouts.

training (Person 1) - Web-based Sensibilisation, QCMs, and courses.

announced_drills (Person 2) - AI spear-phishing generation and tracking.

silent_drills (Person 3) - C2 Agent WebSockets, Honeytokens, Shadow AI.

ml_engine (Person 4) - Isolation Forest models, HRN scoring, Data processing.

How to Create Your App
When you are ready to start building your section, run:

Bash
python manage.py startapp your_app_name
Don't forget to add your new app to INSTALLED_APPS in cognisec/settings.py!

Using the UI System
Do not write custom CSS unless absolutely necessary.
To build a new page, extend the base template and copy components from the UI Kit:

HTML
{% extends 'core/base.html' %}

{% block content %}
    {% endblock %}

***

Once your team has pulled this down and everyone has it running locally, you will
