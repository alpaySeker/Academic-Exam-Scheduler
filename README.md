# Academic Exam Scheduler & Management System 🎓

A professional-grade desktop application built with Python to streamline university exam scheduling, automate conflict detection, and manage complex academic data structures.

## 🚀 Key Engineering Highlights
- **Conflict Detection Logic:** Developed a custom validation engine that cross-references dates, times, and departmental constraints to ensure 100% schedule integrity.
- **Modular Backend Architecture:** Implemented a clean "Separation of Concerns" (SoC) by decoupling the UI (PySide6) from the Data Access Layer (SQLAlchemy).
- **Relational Data Modeling:** Designed structured object models for Users, Students, Courses, and Exams to handle complex many-to-many relationships.
- **Role-Based Access Control (RBAC):** Built a secure authentication system with hierarchical permissions for Admins and Department Coordinators.
- **Dynamic Reporting:** Integrated automated PDF report generation and Excel data processing for real-world academic workflows.

## 🛠️ Tech Stack
- **Language:** Python 3.10+
- **GUI Framework:** PySide6 (Qt for Python)
- **Database / ORM:** SQLite with SQLAlchemy
- **Data Science:** Pandas, NumPy, Matplotlib
- **Document Styling:** ReportLab (for PDF generation)

## 📂 Project Structure
- `app.py`: Main entry point and GUI controller.
- `core/`: Business logic, authentication, and database models.
- `data/`: Persistent storage and local database files.
- `requirements.txt`: Comprehensive dependency list for seamless deployment.

## 📋 Installation & Usage
1. Clone the repository.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
3. Run the application:
   ```bash
   py app.py
