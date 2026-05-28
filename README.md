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
git clone https://github.com/CharafiHafsa/psyche_sentinel.git
cd cognisec-platform
```

### 3. Setup the Virtual Environment
Always isolate your dependencies. Do not install packages globally.
#### Create the virtual environment
```bash 
python -m venv venv
```

#### Activate it (Windows)
```bash 
venv\Scripts\activate
```
#### Activate it (Mac/Linux)
```bash
source venv/bin/activate
```

### 4. Install Dependencies
``` Bash
pip install -r requirements.txt
```

### 5. Database Configuration
You must create the local PostgreSQL database before running the app.

Open your Postgres terminal (psql) or pgAdmin.

Run the following SQL command:
```bash
CREATE DATABASE cognisec_db;
```

Note: Ensure the username and password in cognisec/settings.py match your local Postgres credentials.

### 6. Run Migrations & Start the Server
``` Bash
# Apply the database schema
python manage.py migrate

# Start the development server
python manage.py runserver
``` 
## Git Workflow: Branching & Pushing
To keep our codebase stable, no one should push directly to the main branch. Every new feature or app should be built in its own branch and then merged.

### Step 1: Pull the Latest Changes
Before starting your work for the day, always make sure your local main branch is up to date:

``` Bash
git checkout main
git pull origin main
```

### Step 2: Create a New Branch
Create a branch named after the feature you are building. Use prefixes like feature/, fix/, or ui/:

``` Bash
git checkout -b feature/your-app-name
(Example: git checkout -b feature/ml-engine)
```

### Step 3: Make Changes, Add, and Commit
Write your code, save your files, and then commit your work, but don't forget to update the requerement file :
```bash
pip freeze > requirements.txt
```

``` Bash
# See which files you changed
git status

# Add your changed files to the staging area
git add .

# Commit with a clear, descriptive message
git commit -m "Added the models and views for the QCM module"
```
### Step 4: Push Your Branch to GitHub
Push your specific branch to the remote repository:

``` Bash
git push -u origin feature/your-app-name
```

### Step 5: Create a Pull Request (PR)
Go to the repository on GitHub.
You will see a green button that says "Compare & pull request". Click it.
Add a brief description of what you built and request a review from a teammate before merging it into main.

## Keeping Your Branch Up to Date
As development progresses, the `main` branch will be frequently updated with core UI components and system architecture. **Do not push directly to main.** 
To get the latest updates from `main` into your personal feature branch, run the following commands in your terminal:
1. **Commit your current work** so you don't lose any progress:
   ```bash
   git add .
   git commit -m "Save current progress before pulling main"
   ```
2. **Pull the latest changes** from the main branch directly into your active branch:
   ```bash
   git pull origin main
   ```
3. If there are merge conflicts, resolve them in your code editor, save the files, and commit the resolved changes.
   
## Start the development server
```bash
python manage.py runserver
```
Visit http://127.0.0.1:8000/ in your browser to see the Landing Page.
Visit http://127.0.0.1:8000/ui-kit/ and http://127.0.0.1:8000/dataviz-kit to access the Master Component Catalog.


## Team Architecture & Workflow
To prevent Git merge conflicts, our platform is divided into isolated Django apps. You will work primarily within your assigned app but will inherit the global design from the core app.

### App Assignments
**core (Shared)** - Global UI Kit, Authentication, Base Layouts.

**training (Person 1)** - Web-based Sensibilisation, QCMs, and courses.

**announced_drills (Person 2)** - AI spear-phishing generation and tracking.

**silent_drills (Person 3)** - C2 Agent WebSockets, Honeytokens, Shadow AI.

**ml_engine (Person 4)** - Isolation Forest models, HRN scoring, Data processing.

How to Create Your App
When you are ready to start building your section, run:

``` Bash
python manage.py startapp your_app_name
```
Don't forget to add your new app to INSTALLED_APPS in cognisec/settings.py!


### Using the UI System
Do not write custom CSS unless absolutely necessary.
To build a new page, extend the base template and copy components from the UI Kit:

HTML
{% extends 'core/base.html' %}

{% block content %}
    {% endblock %}

***
# Important !!!
we may need to chnage the name of the tests to : 
- Évaluations de connaissances 
- Scénarios d’attaque simulée 
- Évaluations comportementales non prédictibles

# Local Database: Loading Employee Test Data
To make development faster, **you do not need to run the LDAP synchronization locally.** We have provided a database fixture containing a fully populated employee directory.
**Inject the employee data into your local database:**
```bash
python manage.py loaddata initial_employees.json
```

