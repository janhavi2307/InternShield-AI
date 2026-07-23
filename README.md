# InternShield AI

InternShield AI is an explainable internship assessment platform designed to help students evaluate internship opportunities before accepting them.

It analyzes recruiter messages, offer letters, PDF documents and screenshots to identify warning indicators, estimate opportunity value, calculate effective hourly compensation and check compatibility with the student's academic schedule.

## Key Features

- Secure email and password authentication
- Supabase PostgreSQL database integration
- Row Level Security for protecting user data
- Internship description and recruiter-message analysis
- PDF offer-letter text extraction
- Screenshot text extraction using OCR
- Explainable verification scoring
- Opportunity value scoring
- Effective hourly stipend calculation
- Suspicious phrase and warning-indicator detection
- Academic schedule compatibility assessment
- Personal analysis history dashboard
- Downloadable professional PDF reports
- Responsive and animated user interface

## How It Works

InternShield evaluates an internship using three main dimensions:

### 1. Verification Assessment

The system searches the submitted information for warning indicators such as:

- Registration or application fees
- Guaranteed selection claims
- Urgent joining pressure
- Requests for bank or identity information
- Communication through unofficial channels
- Missing or unclear selection procedures

A higher verification score means fewer predefined warning indicators were detected.

### 2. Opportunity Value

The value score considers information such as:

- Monthly stipend
- Working hours
- Working days
- Internship duration
- Mentorship and learning indicators
- Unpaid workload
- Effective hourly compensation

### 3. Academic Compatibility

The compatibility engine compares the internship workload with the student's availability and considers:

- Weekly internship workload
- Available hours per week
- Fixed or flexible schedules
- Examination overlap
- Lecture or practical-session conflicts

## Assessment Statuses

InternShield may classify an opportunity as:

- **Appears Reasonable**
- **Verification Required**
- **Potentially Suspicious**

Academic compatibility may be classified as:

- **Manageable**
- **Demanding**
- **Conflict Risk**

These results are explainable assessments and do not conclusively prove that an internship is legitimate or fraudulent.

## Technology Stack

### Backend

- Python
- Flask
- Supabase Python Client
- PostgreSQL

### Frontend

- HTML5
- CSS3
- Jinja2
- JavaScript

### Document Processing

- PyMuPDF for PDF text extraction
- EasyOCR for screenshot text extraction
- Pillow for image processing

### Report Generation

- ReportLab

### Authentication and Database

- Supabase Authentication
- Supabase PostgreSQL
- Row Level Security policies

## Project Structure

```text
InternShield-AI/
│
├── app.py
├── supabase_client.py
├── requirements.txt
├── README.md
├── .gitignore
│
├── services/
│   ├── __init__.py
│   ├── analysis_engine.py
│   ├── compatibility_engine.py
│   ├── document_extractor.py
│   ├── image_extractor.py
│   └── report_generator.py
│
├── static/
│   └── css/
│       └── style.css
│
└── templates/
    ├── index.html
    ├── login.html
    ├── signup.html
    ├── dashboard.html
    ├── analyze.html
    └── analysis_result.html