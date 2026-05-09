from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS
import requests
import os
from dotenv import load_dotenv
import anthropic
from flask_sqlalchemy import SQLAlchemy
from datetime import date, datetime, timedelta
import random

load_dotenv()

app = Flask(__name__, static_folder='static')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///ring_report.db'
db = SQLAlchemy(app)
CORS(app)

class DailyLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(10), nullable=False)
    workout_type = db.Column(db.String(50))
    duration = db.Column(db.Integer)
    intensity = db.Column(db.Integer)
    soreness = db.Column(db.Integer)
    joint_pain = db.Column(db.Integer)
    pain_location = db.Column(db.String(100))
    fatigue = db.Column(db.Integer)
    notes = db.Column(db.Text)

with app.app_context():
    db.create_all()

OURA_TOKEN = os.getenv('OURA_TOKEN')
OPENWEATHER_KEY = os.getenv('OPENWEATHER_KEY')
def generate_mock_data(base_score, days = 7):
    data = []
    score = base_score
    for i in range(days):
        day = (datetime.today()-timedelta(days=days-i-1)).strftime('%Y-%m-%d')
        score = max(50, min(99, score + random.randint(-8,8)))
        data.append({"day": day, "score": score})
    return {"data": data}

_mock_sleep = generate_mock_data(72)

def derive_readiness(sleep_data):
    data = []
    for s in sleep_data['data']:
        readiness_score = max(50, min(99, s['score'] + random.randint(-8,8)))
        data.append({"day": s['day'], "score": readiness_score})
    return {"data": data}

_mock_cache = {
    'sleep': _mock_sleep,
    'readiness': derive_readiness(_mock_sleep)
}

def generate_mock_workouts(days=7):
    workout_types = ['match', 'conditioning', 'lift', 'practice', 'rest']
    logs = []
    for i in range(days):
        day = (datetime.today()-timedelta(days=days-i-1)).strftime('%Y-%m-%d')
        workout_type = random.choice(workout_types)
        if workout_type == 'rest':
            logs.append({
                "date": day,
                "workout_type": "rest",
                "duration": 0,
                "intensity": 1,
                "soreness": random.randint(1, 3),
                "joint_pain": random.randint(1, 3),
                "fatigue": random.randint(1, 3)
            })
        else:
            intensity = random.randint(3, 10)
            logs.append({
                "date": day,
                "workout_type": workout_type,
                "duration": random.randint(15, 120),
                "intensity": intensity,
                "joint_pain": random.randint(1, 5),
                "soreness": max(1, min(5, intensity - random.randint(2, 4))),
                "fatigue": max(1, min(5, intensity - random.randint(1, 3)))
            })
    return logs

_mock_workouts = generate_mock_workouts()

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/api/readiness')
def get_readiness():
    if not OURA_TOKEN:
        return jsonify(_mock_cache['readiness'])
    else: 
        headers = {'Authorization': f'Bearer {OURA_TOKEN}'}
        response = requests.get(
            'https://api.ouraring.com/v2/usercollection/daily_readiness?start_date=2026-04-01',
            headers=headers
        )
    return jsonify(response.json())

@app.route('/api/sleep')
def get_sleep():
    if not OURA_TOKEN:
       return jsonify(_mock_cache['sleep'])
    else:
        headers = {'Authorization': f'Bearer {OURA_TOKEN}'}
        response = requests.get(
            'https://api.ouraring.com/v2/usercollection/daily_sleep?start_date=2026-04-01',
            headers=headers
        )
    return jsonify(response.json())

@app.route('/api/weather')
def get_weather():
    response = requests.get(
        f'http://api.openweathermap.org/data/2.5/weather?lat=43.7022&lon=-72.2896&appid={OPENWEATHER_KEY}&units=imperial'
    )
    return jsonify(response.json())

@app.route('/api/insights')
def get_insights():
    if not OURA_TOKEN:
        readiness = _mock_cache['readiness']['data']
        sleep = _mock_cache['sleep']['data']
    else:
        headers = {'Authorization': f'Bearer {OURA_TOKEN}'}
        readiness = requests.get(
            'https://api.ouraring.com/v2/usercollection/daily_readiness?start_date=2026-04-01',
            headers=headers
        ).json()
        sleep = requests.get(
            'https://api.ouraring.com/v2/usercollection/daily_sleep?start_date=2026-04-01',
            headers=headers
        ).json()
        

    recent_readiness = readiness[-7:] if isinstance(readiness, list) else readiness['data'][-7:]
    recent_sleep = sleep[-7:]  if isinstance(sleep, list) else sleep['data'][-7:]

    weather = requests.get(
        f'http://api.openweathermap.org/data/2.5/weather?lat=43.7022&lon=-72.2896&appid={OPENWEATHER_KEY}&units=imperial',
    ).json()
    pressure = weather['main']['pressure']
    temp = weather['main']['temp']
    conditions = weather['weather'][0]['description']

    summary = "Readiness scores (most recent last):\n"
    for r in recent_readiness:
        summary += f"  {r['day']}: {r['score']}\n"
    summary += "\nSleep scores (most recent last):\n"
    for s in recent_sleep:
        summary += f"  {s['day']}: {s['score']}\n"

    summary += f"\nCurrent weather: {temp}°F, barometric pressure: {pressure} hPa, weather conditions: {conditions}\n"

    if not OURA_TOKEN:
        workout_logs = _mock_workouts
    else:
        workout_logs = []
        for workout in DailyLog.query.order_by(DailyLog.date.desc()).limit(7).all():
            workout_logs.append({
                "date": workout.date,
                "workout_type": workout.workout_type,
                "duration": workout.duration,
                "intensity": workout.intensity,
                "soreness": workout.soreness,
                "joint_pain": workout.joint_pain,
                "fatigue": workout.fatigue
            })
        
    if workout_logs:
        summary += "\nRecent Workouts:\n"
        for log in workout_logs:
            summary += f"  {log['date']}: {log['workout_type'] or 'unknown'}, {log['duration'] or 0} min"
            if log['intensity']:
                summary += f", intensity {log['intensity']}/10"
            if log['soreness']:
                summary += f", soreness {log['soreness']}/5"
            if log['joint_pain']:
                summary += f", joint pain {log['joint_pain']}/5"
            if log['fatigue']:
                summary += f", fatigue {log['fatigue']}/5"
            summary += "\n"

    client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_KEY'))
    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": f"""You are analyzing recovery data for a D1 college tennis athlete who has an autoimmune condition.

            Here is her last 7 days of data:
            {summary}

            Look for patterns between workout type, intensity, and duration and next day readiness drops, soreness or joint
            pain across days, weather pressure/temperature/conditions and joint pain or fatigue, correlation between high 
            intensity workouts and sleep scores, soreness or joint pain patterns across days, and any overtraining signals.
            In 3-4 sentences all lowercase, tell her what patterns you notice and what she should pay attention to today.
            Be specific to the numbers. Be direct, not generic."""
        }]
    )

    return jsonify({"insight": message.content[0].text})

@app.route('/api/log', methods=['POST'])
def save_log():
    data = request.get_json()
    entry = DailyLog(
        date=data.get('date'),
        workout_type=data.get('workout_type'),
        duration=data.get('duration'),
        intensity=data.get('intensity'),
        soreness=data.get('soreness'),
        joint_pain=data.get('joint_pain'),
        pain_location=data.get('pain_location'),
        fatigue=data.get('fatigue'),
        notes=data.get('notes')
    )
    db.session.add(entry)
    db.session.commit()
    return jsonify({"status": "saved"})

@app.route('/api/logs')
def get_logs():
    logs = DailyLog.query.order_by(DailyLog.date.desc()).limit(7).all()
    return jsonify([{
        "date": l.date,
        "workout_type": l.workout_type,
        "duration": l.duration,
        "intensity": l.intensity,
        "soreness": l.soreness,
        "joint_pain": l.joint_pain,
        "fatigue": l.fatigue
    } for l in logs])

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5001)
    