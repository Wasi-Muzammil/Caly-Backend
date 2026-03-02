# 🗓️ Caly Backend — AI-Assisted Smart Meeting Scheduler

Caly's backend is built with **FastAPI** and handles everything from Google OAuth login to finding the best meeting times across multiple calendars. It is fast, clean, and beginner-friendly.

---

## 🧠 What This Backend Does

When someone wants to schedule a meeting, Caly does the following automatically:

1. Logs the user in securely via their Google account
2. Connects to Google Calendar and checks when everyone is busy
3. Flips the busy times to find when everyone is free
4. Scores and ranks the best available slots
5. Saves the confirmed meeting to the database
6. Sends a confirmation email to every participant

---

## 🛠️ Tech Stack

| Tool | Purpose |
|---|---|
| FastAPI | Web framework — handles all API routes |
| SQLAlchemy | Database ORM — manages tables and queries |
| NeonDB-Postgres | Database — stores users, meetings, participants |
| Google OAuth 2.0 | Secure Google login |
| Google Calendar API | Reads calendar availability |
| python-jose | Creates and verifies JWT tokens |
| httpx | Makes async HTTP calls to Google APIs |
| smtplib | Sends confirmation emails via Gmail |
| authlib | Handles the OAuth flow with Google |
| python-dotenv | Loads environment variables from .env |

---

## 📁 Project Structure

```
caly/
├── main.py                        # App entry point, registers all routes
├── requirements.txt               # All Python dependencies
├── .env                           # Secret keys and credentials (never commit this)
│
└── app/
    ├── auth/
    │   ├── oauth.py               # Google OAuth configuration
    │   └── router.py              # Login and callback routes     
    │
    ├── database/
    │   ├── base.py                # SQLAlchemy base class
    │   └── session.py             # Database connection and session
    ├── core/
    │   ├── security.py            # JWT Authorization
    │
    ├── users/
    │   ├── models.py              # User database table
    │   ├── router.py              # User profile route
    │   └── schemas.py          
    │
    ├── calendar/
    │   ├── router.py              # Meeting and MeetingParticipant tables
    │   └── schemas.py              # Suggest, confirm, list, detail routes
    │   └── service.py   
    │
    ├── meetings/
    │   ├── models.py              # Meeting and MeetingParticipant tables
    │   ├── router.py              # Suggest, confirm, list, detail routes
    │   ├── schemas.py      
    │   ├── service.py 
    │   └── ranking.py    
    │
    └── email/
        └── email_service.py       # Sends confirmation emails via Gmail SMTP
```

---

## 🚀 Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/Wasi-Muzammil/Caly-Backend
cd caly
```

### 2. Create a Virtual Environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Set Up Your .env File

Create a `.env` file in the root folder and fill in your credentials:

```env
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/callback
SECRET_KEY=any_long_random_string
DATABASE_URL=postgresql://user:password@ep-xxxx.us-east-2.aws.neon.tech/dbname?sslmode=require
SMTP_EMAIL=your_gmail@gmail.com
SMTP_PASSWORD=your_gmail_app_password
```

> **Important:** Never commit your `.env` file to GitHub. It contains secret keys.

### 5. Run the Server

```bash
uvicorn main:app --reload
```

Visit `http://localhost:8000/docs` to see all endpoints in an interactive UI.

---

## 📡 API Endpoints

### Auth
| Method | Endpoint | Description |
|---|---|---|
| GET | `/auth/google` | Redirects user to Google login |
| GET | `/auth/google/callback` | Handles Google response, returns JWT token |

### Meetings
| Method | Endpoint | Description |
|---|---|---|
| POST | `/meeting/suggest` | Finds and ranks top 5 available meeting slots |
| POST | `/meeting/confirm` | Confirms a slot, saves to DB, emails everyone |
| GET | `/meeting/` | Lists all meetings for the current user |
| GET | `/meeting/{id}` | Returns details for a single meeting |

### Users
| Method | Endpoint | Description |
|---|---|---|
| GET | `/users/me` | Returns the current logged-in user's profile |

---

## 🔐 How Authentication Works

Caly uses **Google OAuth 2.0** for login. Here is the flow in simple terms:

1. User visits `/auth/google` and gets redirected to Google's login page
2. User approves access and Google sends a code back to `/auth/google/callback`
3. The backend exchanges that code for a Google access token and refresh token
4. The backend creates a **JWT token** and sends it to the frontend
5. The frontend stores the JWT and sends it with every future request in the header
6. Every protected route checks the JWT before doing anything

---

## 🧠 How the Smart Slot Logic Works

The slot suggestion system works in four steps inside `services/google_calendar.py` and `services/slot_ranking.py`:

**Step 1 — Fetch Busy Times:** Caly calls Google Calendar's freebusy API and gets back a list of when each participant is busy.

**Step 2 — Find Free Windows:** The busy blocks are flipped to find when each person is free within working hours (9am–6pm).

**Step 3 — Find Overlaps:** Caly compares everyone's free windows and keeps only the times when ALL participants are free at the same time for long enough.

**Step 4 — Score and Rank:** Each valid slot is scored based on four rules — morning preference (+30), earliest available (+20), buffer around the meeting (+15), and extra room (+10). Priority meetings double the score. Top 5 are returned.

---

## 📧 How Emails Work

Caly uses Gmail's SMTP server to send confirmation emails. When a meeting is confirmed, every participant receives a plain-text email with the meeting title, date, time, duration, and participant list.

To enable this, you need a Gmail **App Password** (not your regular Gmail password):

1. Go to **myaccount.google.com → Security → App Passwords**
2. Generate a password for `Caly`
3. Paste it into `SMTP_PASSWORD` in your `.env` file

---

## ⚙️ Environment Variables Explained

| Variable | What It Is |
|---|---|
| `GOOGLE_CLIENT_ID` | From Google Cloud Console → Credentials |
| `GOOGLE_CLIENT_SECRET` | From Google Cloud Console → Credentials |
| `GOOGLE_REDIRECT_URI` | Must match exactly what you set in Google Console |
| `SECRET_KEY` | Any random string used to sign JWT tokens |
| `DATABASE_URL` | Path to your Postgres database |
| `SMTP_EMAIL` | Your Gmail address for sending emails |
| `SMTP_PASSWORD` | Your Gmail App Password (not your regular password) |

---

## 🗄️ Database Tables

**users** — stores everyone who logs in via Google. Saves their email, name, Google ID, and OAuth tokens.

**meetings** — stores every confirmed meeting with title, time, duration, status, and who created it.

**meeting_participants** — links participants to meetings. Stores their email and whether they are a registered user.

---

## 🔄 Resetting the Database

If you want to start fresh and delete all data:

```bash
# Stop the server
Ctrl + C


# Restart — tables are recreated automatically
uvicorn main:app --reload
```


> Built with FastAPI · Google Calendar API · SQLite · Gmail SMTP
