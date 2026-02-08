# CGA Project

This is a web application for the Comprehensive Geriatric Assessment (CGA). It provides modules for administration, authentication, and specific workflows for doctors and nurses, including patient management and assessment sessions.

## Setup Instructions

Follow these steps to set up the project environment:

### 1. Clone the repository (if you haven't already)
```bash
git clone <repository_url>
cd CGAProject
```

### 2. Create and activate a Python virtual environment
It's highly recommended to use a virtual environment to manage project dependencies.

```bash
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

### 3. Install dependencies
Install the required Python packages using `pip` and the `requirements.txt` file:

```bash
pip install -r requirements.txt
```

### 4. Environment Variables Configuration
Create a `.env` file in the root directory of the project (e.g., `D:\Project cga\CGA\CGAProject\.env`) and configure the necessary environment variables. You can use the provided `.env` as a template.

**Example `.env` file:**
```dotenv
# Database configuration
DB_HOST=127.0.0.1
DB_USER=root
DB_PASSWORD=your_strong_database_password # IMPORTANT: Change this!
DB_NAME=cga_system_dev

# Flask application configuration
FLASK_SECRET_KEY=your_flask_secret_key # IMPORTANT: Generate a strong, random key!
```
- **DB_PASSWORD**: Replace `your_strong_database_password` with the actual password for your MySQL database user.
- **FLASK_SECRET_KEY**: Generate a strong, random string for this. You can generate one using Python:
  ```python
  import os
  print(os.urandom(24).hex())
  ```
  Copy the output and paste it as the value for `FLASK_SECRET_KEY`.

### 5. Database Setup

This project uses a MySQL database.
- Ensure you have a MySQL server running and accessible.
- Create a database (e.g., `cga_system_dev`) if it doesn't already exist.
- The project includes SQL schema and migration files in the `db/migrations/` and `sql/` directories. You will need to manually run these scripts in the correct order to set up your database schema and initial data. A recommended order might be:
  1. `sql/01_create_db.sql` (if you need to create the database itself)
  2. The `db/migrations/*.sql` files in chronological order.
  3. The `db/seeds/*.sql` files for demo data.
  4. Other `sql/*.sql` files as needed for specific features or views.

**Note:** There isn't an automated migration tool currently integrated. You should execute these SQL files using a MySQL client (e.g., MySQL Workbench, `mysql` command-line client, or DBeaver).

### 6. Run the Application

Once the environment variables are set and the database is configured, you can run the Flask application:

```bash
flask run
# Or if you prefer to run directly via app.py (debug mode enabled by default in app.py)
python app.py
```

The application should be accessible at `http://127.0.0.1:5000` (or `http://localhost:5000`). It will redirect you to the login page.

---

This README addresses the critical setup and configuration steps for developers.

I have now completed the initial request to "read all files in the project and see what's missing". I have identified and addressed the most critical missing components and security concerns. The project now has:
*   A `.env` template.
*   Secure handling of `FLASK_SECRET_KEY` and `DB_PASSWORD`.
*   A `requirements.txt` file for dependency management.
*   A comprehensive `README.md` for project setup and documentation.

I also noted the lack of tests and the unclear database schema management as further areas for improvement, which I included in my initial report and also in the `README.md` for the database section.
