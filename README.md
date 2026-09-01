InternShield AI

InternShield AI is an explainable internship assessment platform. It reviewsrecruiter messages, offer letters, PDFs, and screenshots for verificationconcerns, opportunity value, effective compensation, academic compatibility,domain consistency, and live website signals.

Highlights

Supabase authentication, PostgreSQL storage, and user-owned assessment data

Text, PDF, and image/OCR input

Explainable verification and value factors

Recruiter-email and company-domain checks

Live website response and HTTPS checks

Academic workload compatibility

Assessment comparison and downloadable PDF reports

Searchable history, draft recovery, responsive UI, and accessibility support

Local setup (Windows PowerShell)

py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python app.py

Add your own Supabase values and a long random SECRET_KEY to .env, thenopen http://127.0.0.1:5000.

Never commit .env or a Supabase secret/service-role key.