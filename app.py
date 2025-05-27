from flask import Flask, request, jsonify, render_template, redirect, url_for, session, send_file
from flask import Response
from flask_bcrypt import Bcrypt
from markupsafe import Markup
from flask_cors import CORS
import mysql.connector
import requests
import io
import csv
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib
import base64 # Import base64 for image encoding
import numpy as np # Import numpy for numerical operations like correlation

matplotlib.use('Agg')

app = Flask(__name__)
app.secret_key = '111'
bcrypt = Bcrypt(app)
CORS(app)

@app.route('/')
def login():
    return render_template('login.html')


@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

# Configurare DB
db_config = {
    'host': 'sql7.freesqldatabase.com',
    'user': 'sql7781154',
    'password': 'Xxpsy1T8b7',
    'database': 'sql7781154',
    'port': 3306
}

OPENWEATHER_API_KEY = 'e86a21e5e7ee35cc87a7aec4cacc3365'
OPENCAGE_API_KEY = 'ce2f5a5e6b314cb684dbe8370195345d'

def get_db_connection():
    return mysql.connector.connect(**db_config)

def create_database_and_tables():
    connection = mysql.connector.connect(
        host=db_config['host'],
        user=db_config['user'],
        password=db_config['password']
    )
    cursor = connection.cursor()
    cursor.execute("CREATE DATABASE IF NOT EXISTS sql7781154 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    connection.commit()
    cursor.close()
    connection.close()

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS utilizatori (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(100) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS masuratori (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            city VARCHAR(100) NOT NULL,
            country VARCHAR(100) NOT NULL,
            temperature FLOAT NOT NULL,
            humidity INT NOT NULL,
            pressure FLOAT,
            co FLOAT,
            no2 FLOAT,
            so2 FLOAT,
            o3 FLOAT,
            pm25 FLOAT,
            pm10 FLOAT,
            `condition` VARCHAR(100) NOT NULL,
            timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES utilizatori(id) ON DELETE CASCADE
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
    """)
    conn.commit()
    cursor.close()
    conn.close()

create_database_and_tables()

# --- AUTHENTICARE ---



@app.route('/signup', methods=['POST'])
def signup():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({'error': 'Nume utilizator și parolă sunt obligatorii'}), 400

    hashed = bcrypt.generate_password_hash(password).decode('utf-8')

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO utilizatori (username, password_hash) VALUES (%s, %s)", (username, hashed))
        conn.commit()
    except mysql.connector.errors.IntegrityError:
        return jsonify({'error': 'Numele de utilizator există deja'}), 409
    finally:
        cursor.close()
        conn.close()

    return jsonify({'message': 'Utilizator înregistrat cu succes'}), 201

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM utilizatori WHERE username=%s", (username,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if user and bcrypt.check_password_hash(user['password_hash'], password):
        session['user_id'] = user['id']
        session['username'] = user['username']
        # Returnează un URL de redirecționare, frontend-ul se va ocupa de navigare
        return jsonify({'redirect_url': url_for('dashboard')})
    else:
        return jsonify({'error': 'Credențiale invalide'}), 401

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Delogat cu succes'})

def login_required(func):
    from functools import wraps
    @wraps(func)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            # Returnează 401 (Unauthorized) pentru API-uri care necesită login
            return jsonify({'error': 'Autentificarea este necesară'}), 401
        return func(*args, **kwargs)
    return decorated_function

# --- API weather + air quality using OpenWeatherMap and OpenCage ---

def fetch_coordinates(city, country):
    geocode_url = f"https://api.opencagedata.com/geocode/v1/json?q={city}+{country}&key={OPENCAGE_API_KEY}&limit=1"
    r = requests.get(geocode_url)
    if r.status_code != 200:
        print(f"Error fetching coordinates: Status {r.status_code}, Response: {r.text}")
        return None
    data = r.json()
    if not data['results']:
        return None
    lat = data['results'][0]['geometry']['lat']
    lng = data['results'][0]['geometry']['lng']
    return lat, lng

def fetch_weather_and_airquality(city, country):
    coords = fetch_coordinates(city, country)
    if not coords:
        return None
    lat, lon = coords

    weather_url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units=metric"
    weather_res = requests.get(weather_url)
    if weather_res.status_code != 200:
        print(f"Error fetching weather: Status {weather_res.status_code}, Response: {weather_res.text}")
        return None
    weather_data = weather_res.json()

    air_url = f"https://api.openweathermap.org/data/2.5/air_pollution?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}"
    air_res = requests.get(air_url)
    if air_res.status_code != 200:
        print(f"Error fetching air quality: Status {air_res.status_code}, Response: {air_res.text}")
        return None
    air_data = air_res.json()

    main = weather_data.get('main', {})
    weather_cond = weather_data.get('weather', [{}])[0].get('description', '')

    air_components = air_data.get('list', [{}])[0].get('components', {})

    result = {
        'city': city,
        'country': country,
        'lat': lat,
        'lon': lon,
        'temperature': main.get('temp'),
        'humidity': main.get('humidity'),
        'pressure': main.get('pressure'),
        'condition': weather_cond,
        'co': air_components.get('co'),
        'no2': air_components.get('no2'),
        'so2': air_components.get('so2'),
        'o3': air_components.get('o3'),
        'pm25': air_components.get('pm2_5'),
        'pm10': air_components.get('pm10'),
    }
    return result

# NOU: Endpoint pentru căutare publică (fără autentificare)
@app.route('/public_weather/<city>/<country>', methods=['GET'])
def public_get_weather(city, country):
    """
    Permite utilizatorilor nelogați să caute vremea și calitatea aerului.
    Nu permite salvarea datelor în baza de date.
    """
    data = fetch_weather_and_airquality(city, country)
    if not data:
        return jsonify({'error': 'Datele nu au fost găsite pentru locația specificată.'}), 404
    return jsonify(data)


@app.route('/weather/<city>/<country>', methods=['GET'])
@login_required # Acest endpoint necesită în continuare autentificare pentru funcționalități avansate dacă este apelat
def api_get_weather(city, country):
    data = fetch_weather_and_airquality(city, country)
    if not data:
        return jsonify({'error': 'Datele nu au fost găsite'}), 404
    return jsonify(data)

@app.route('/forecast/<city>/<country>', methods=['GET'])
@login_required
def api_get_forecast(city, country):
    coords = fetch_coordinates(city, country)
    if not coords:
        return jsonify({'error': 'Locația nu a fost găsită'}), 404
    lat, lon = coords

    url = f"https://api.openweathermap.org/data/2.5/onecall?lat={lat}&lon={lon}&exclude=current,minutely,hourly,alerts&appid={OPENWEATHER_API_KEY}&units=metric"
    r = requests.get(url)
    if r.status_code != 200:
        return jsonify({'error': 'Datele de prognoză nu au fost găsite'}), 404
    data = r.json()
    results = []
    for day in data.get('daily', []):
        results.append({
            'date': datetime.utcfromtimestamp(day['dt']).strftime('%Y-%m-%d'),
            'maxtemp_c': day['temp']['max'],
            'mintemp_c': day['temp']['min'],
            'avgtemp_c': (day['temp']['max'] + day['temp']['min']) / 2,
            'condition': day['weather'][0]['description'],
            'humidity': day['humidity']
        })
    return jsonify(results)

# --- CRUD masuratori per user ---

@app.route('/measurements', methods=['GET', 'POST'])
@login_required
def manage_measurements():
    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        data = request.json
        city = data.get('city')
        country = data.get('country')

        if not city or not country:
            return jsonify({'error': 'Orașul și țara sunt obligatorii'}), 400

        weather_data = fetch_weather_and_airquality(city, country)
        if not weather_data:
            return jsonify({'error': 'Nu s-au putut prelua datele meteo'}), 404

        cursor.execute("""
            INSERT INTO masuratori (user_id, city, country, temperature, humidity, pressure, co, no2, so2, o3, pm25, pm10, `condition`)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            user_id,
            city,
            country,
            weather_data['temperature'],
            weather_data['humidity'],
            weather_data['pressure'],
            weather_data['co'],
            weather_data['no2'],
            weather_data['so2'],
            weather_data['o3'],
            weather_data['pm25'],
            weather_data['pm10'],
            weather_data['condition']
        ))

        conn.commit()

        cursor.close()
        conn.close()
        return jsonify({'message': 'Măsurătoare adăugată cu succes'}), 201

    # For GET method
    cursor.execute("SELECT * FROM masuratori WHERE user_id = %s ORDER BY timestamp DESC", (user_id,))
    measurements = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(measurements)

@app.route('/measurements/manual', methods=['POST'])
@login_required
def add_manual_measurement():
    user_id = session['user_id']
    data = request.json

    # Aștept să primești toate câmpurile manual:
    city = data.get('city')
    country = data.get('country')
    temperature = data.get('temperature')
    humidity = data.get('humidity')
    pressure = data.get('pressure')
    co = data.get('co')
    no2 = data.get('no2')
    so2 = data.get('so2')
    o3 = data.get('o3')
    pm25 = data.get('pm25')
    pm10 = data.get('pm10')
    condition = data.get('condition')

    # Verificări simple
    if not city or not country or temperature is None or humidity is None or not condition:
        return jsonify({'error': 'Câmpuri obligatorii lipsesc'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO masuratori (user_id, city, country, temperature, humidity, pressure, co, no2, so2, o3, pm25, pm10, `condition`)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        user_id, city, country, temperature, humidity, pressure, co, no2, so2, o3, pm25, pm10, condition
    ))
    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({'message': 'Măsurătoare manuală adăugată cu succes'}), 201


@app.route('/measurements/<int:measurement_id>', methods=['DELETE'])
@login_required
def delete_measurement(measurement_id):
    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM masuratori WHERE id = %s AND user_id = %s", (measurement_id, user_id))
    conn.commit()
    affected = cursor.rowcount
    cursor.close()
    conn.close()

    if affected == 0:
        return jsonify({'error': 'Măsurătoarea nu a fost găsită sau nu ești autorizat'}), 404

    return jsonify({'message': 'Măsurătoare ștearsă cu succes'}), 200

@app.route('/measurements/delete_all', methods=['DELETE'])
@login_required
def delete_all_measurements():
    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM masuratori WHERE user_id = %s", (user_id,))
    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({'message': 'Toate măsurătorile au fost șterse cu succes'}), 200

@app.route('/measurements/export', methods=['GET'])
@login_required
def export_measurements():
    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM masuratori WHERE user_id = %s ORDER BY timestamp DESC", (user_id,))
    measurements = cursor.fetchall()
    cursor.close()
    conn.close()

    if not measurements:
        return jsonify({'error': 'Nicio măsurătoare disponibilă pentru export'}), 404

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=measurements[0].keys())
    writer.writeheader()
    writer.writerows(measurements)
    output.seek(0)

    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name='measurements.csv'
    )

# --- Salvează toate măsurătorile efectuate pentru user (apel API care aduce datele, apoi le salvează) ---

@app.route('/measurements/save_all', methods=['POST'])
@login_required
def save_all_current_measurements():
    """
    Endpoint pentru a salva în baza de date toate măsurătorile curente făcute de utilizator
    în funcție de lista trimisă de locații (city, country) în JSON.
    """
    user_id = session['user_id']
    data = request.json
    locations = data.get('locations')  # aștept listă de dicturi: [{"city": "...", "country": "..."}, ...]

    if not locations or not isinstance(locations, list):
        return jsonify({'error': 'Lista de locații este obligatorie'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    saved = 0
    for loc in locations:
        city = loc.get('city')
        country = loc.get('country')
        if not city or not country:
            continue
        weather_data = fetch_weather_and_airquality(city, country)
        if not weather_data:
            continue
        cursor.execute("""
            INSERT INTO masuratori (user_id, city, country, temperature, humidity, pressure, co, no2, so2, o3, pm25, pm10, `condition`)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            user_id,
            city,
            country,
            weather_data['temperature'],
            weather_data['humidity'],
            weather_data['pressure'],
            weather_data['co'],
            weather_data['no2'],
            weather_data['so2'],
            weather_data['o3'],
            weather_data['pm25'],
            weather_data['pm10'],
            weather_data['condition']
        ))
        saved += 1

    conn.commit()
    cursor.close()
    conn.close()

    if saved == 0:
        return jsonify({'error': 'Nicio măsurătoare validă salvată'}), 400
    return jsonify({'message': f'{saved} măsurători salvate cu succes'}), 201

# --- Utility functions for plotting ---

def create_plot(x, y, title, xlabel, ylabel, plot_type='plot'):
    plt.figure(figsize=(8, 4))
    if plot_type == 'plot':
        plt.plot(x, y, marker='o', linestyle='-', color='blue')
    elif plot_type == 'scatter':
        plt.scatter(x, y, color='blue', alpha=0.6)
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.xticks(rotation=45)
    plt.tight_layout()
    img = io.BytesIO()
    plt.savefig(img, format='png')
    img.seek(0)
    plt.close()
    return "data:image/png;base64," + base64.b64encode(img.getvalue()).decode()

def calculate_aqi(pm25=None, pm10=None, co=None, no2=None, so2=None, o3=None):
    # Simplified AQI calculation based on a single dominant pollutant
    # This is a very basic example and not a full EPA AQI calculation.
    # For a real AQI, you'd need breakpoint concentrations for each pollutant.

    aqi_values = []

    # Example breakpoints for a simplified AQI (very rough, for illustration)
    # Good: 0-50, Moderate: 51-100, Unhealthy: 101-150, Very Unhealthy: 151-200, Hazardous: 201+
    # These are illustrative and should be replaced with actual AQI standards.

    if pm25 is not None:
        if pm25 <= 12.0: aqi_values.append(50) # Good
        elif pm25 <= 35.4: aqi_values.append(100) # Moderate
        elif pm25 <= 55.4: aqi_values.append(150) # Unhealthy for Sensitive Groups
        elif pm25 <= 150.4: aqi_values.append(200) # Unhealthy
        elif pm25 <= 250.4: aqi_values.append(300) # Very Unhealthy
        else: aqi_values.append(500) # Hazardous

    if pm10 is not None:
        if pm10 <= 54: aqi_values.append(50)
        elif pm10 <= 154: aqi_values.append(100)
        elif pm10 <= 254: aqi_values.append(150)
        elif pm10 <= 354: aqi_values.append(200)
        elif pm10 <= 424: aqi_values.append(300)
        else: aqi_values.append(500)

    # Simplified thresholds for other pollutants (these are highly generalized)
    if co is not None: # CO (mg/m3) - OpenWeather provides in μg/m3, need to convert to mg/m3 or adjust threshold
        co_mg_m3 = co / 1000 # Convert from μg/m3 to mg/m3
        if co_mg_m3 <= 4.4: aqi_values.append(50)
        elif co_mg_m3 <= 9.4: aqi_values.append(100)
        elif co_mg_m3 <= 12.4: aqi_values.append(150)
        else: aqi_values.append(200)

    if no2 is not None: # NO2 (ppb) - OpenWeather provides in μg/m3, conversion needed
        # Assuming typical atmospheric conditions for conversion (approx 1 ppb NO2 = 1.88 μg/m3)
        # Using μg/m3 directly for simplified threshold
        if no2 <= 53: aqi_values.append(50)
        elif no2 <= 100: aqi_values.append(100)
        elif no2 <= 360: aqi_values.append(150)
        else: aqi_values.append(200)

    if so2 is not None: # SO2 (ppb) - OpenWeather provides in μg/m3, conversion needed
        if so2 <= 35: aqi_values.append(50)
        elif so2 <= 75: aqi_values.append(100)
        elif so2 <= 185: aqi_values.append(150)
        else: aqi_values.append(200)

    if o3 is not None: # O3 (ppb) - OpenWeather provides in μg/m3, conversion needed
        if o3 <= 54: aqi_values.append(50)
        elif o3 <= 70: aqi_values.append(100)
        elif o3 <= 85: aqi_values.append(150)
        else: aqi_values.append(200)

    if aqi_values:
        return max(aqi_values) # The highest AQI value among pollutants determines the overall AQI
    return None

# --- Plotting and Statistics Endpoints ---

# ... (codul existent până la funcția export_stats) ...

@app.route('/measurements/export_stats', methods=['GET'])
@login_required
def export_stats():
    user_id = session['user_id']
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT temperature, humidity, pressure, co, no2, so2, o3, pm25, pm10, `condition`, timestamp
            FROM masuratori
            WHERE user_id=%s ORDER BY timestamp ASC
        """, (user_id,))

        data = cursor.fetchall()
        cursor.close()
        conn.close()

        if not data:
            return jsonify({'error': 'Nu există măsurători pentru export'}), 404

        # --- Calculează valorile medii și deviațiile (copiat din plot_all_graphs) ---
        temps = [d['temperature'] for d in data if d['temperature'] is not None]
        hums = [d['humidity'] for d in data if d['humidity'] is not None]
        pressures = [d['pressure'] for d in data if d['pressure'] is not None]
        pm25s = [d['pm25'] for d in data if d['pm25'] is not None]
        pm10s = [d['pm10'] for d in data if d['pm10'] is not None]
        cos = [d['co'] for d in data if d['co'] is not None]
        no2s = [d['no2'] for d in data if d['no2'] is not None]
        so2s = [d['so2'] for d in data if d['so2'] is not None]
        o3s = [d['o3'] for d in data if d['o3'] is not None]

        # Calculate AQI for each measurement
        aqi_values = []
        for d in data:
            aqi_val = calculate_aqi(pm25=d.get('pm25'), pm10=d.get('pm10'), co=d.get('co'),
                                     no2=d.get('no2'), so2=d.get('so2'), o3=d.get('o3'))
            if aqi_val is not None:
                aqi_values.append(aqi_val)

        # Medii for all available metrics
        average_values = {
            'temperature': np.mean(temps) if temps else None,
            'humidity': np.mean(hums) if hums else None,
            'pressure': np.mean(pressures) if pressures else None,
            'pm25': np.mean(pm25s) if pm25s else None,
            'pm10': np.mean(pm10s) if pm10s else None,
            'co': np.mean(cos) if cos else None,
            'no2': np.mean(no2s) if no2s else None,
            'so2': np.mean(so2s) if so2s else None,
            'o3': np.mean(o3s) if o3s else None,
            'aqi': np.mean(aqi_values) if aqi_values else None,
        }

        # Standard/Optimal values for deviation calculation (Example values, adjust as needed for research)
        optimal_values = {
            'temperature': 22.0,  # °C, e.g., comfortable indoor temperature
            'humidity': 50.0,     # %, e.g., ideal indoor humidity
            'pressure': 1013.25,  # hPa, standard atmospheric pressure at sea level
            'pm25': 10.0,         # μg/m³, WHO guideline for annual mean
            'pm10': 20.0,         # μg/m³, WHO guideline for annual mean
            'co': 4000.0,         # μg/m³, WHO guideline for 8-hour mean (4 mg/m3)
            'no2': 40.0,          # μg/m³, WHO guideline for annual mean
            'so2': 20.0,          # μg/m³, WHO guideline for 24-hour mean
            'o3': 100.0,          # μg/m³, WHO guideline for 8-hour mean
            'aqi': 50.0           # AQI: Good category max value
        }

        deviation_from_standard = {}
        for key, avg_val in average_values.items():
            if avg_val is not None and key in optimal_values:
                deviation = avg_val - optimal_values[key]
                deviation_from_standard[key] = round(deviation, 2)
            else:
                deviation_from_standard[key] = None
        # --- Sfârșitul calculului pentru medii și deviații ---

        # Conversie în CSV
        output = io.StringIO()
        fieldnames = list(data[0].keys()) # Obține numele coloanelor existente

        # Adaugă noi câmpuri pentru medii și deviații la antet, dacă e necesar
        # O abordare simplă este să adaugi un antet separat sau rânduri separate la sfârșit.
        # Pentru simplitate, vom adăuga rânduri separate la sfârșitul fișierului CSV.

        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)

        # Adaugă rânduri pentru valorile medii
        output.write("\n\n") # Spațiu pentru lizibilitate
        output.write("Valori Medii:\n")
        # Creează un dicționar cu valorile medii, aliniate la coloanele existente
        average_row = {field: '' for field in fieldnames} # Inițializare cu gol
        for key, value in average_values.items():
            if key in average_row: # Asigură-te că cheia există în antet
                average_row[key] = round(value, 2) if value is not None else 'N/A'
            elif key == 'aqi': # AQI poate fi un câmp nou
                 average_row['AQI Mediu'] = round(value, 2) if value is not None else 'N/A'

        # Pentru a adăuga o coloană nouă cum ar fi 'AQI Mediu' fără a modifica structura inițială,
        # trebuie să adăugăm manual rânduri sau să extindem fieldnames inițial.
        # Simplificăm scriind un rând descriptiv și apoi valorile.

        # O soluție mai flexibilă este să adăugăm pur și simplu un rând cu un "nume" pentru statistici
        # și apoi valorile corespunzătoare.
        # Pentru moment, scriem rânduri simple.

        # Header for average values (manual construction for clarity)
        avg_header_row = {key: key for key in average_values.keys()}
        avg_data_row = {key: (round(value, 2) if value is not None else 'N/A') for key, value in average_values.items()}

        # Asigură-te că antetul și datele medii se potrivesc cu un scriitor de dicționar nou
        # sau scrie-le manual. Scrierea manuală este mai simplă aici pentru a nu complica `fieldnames`.
        output.write(','.join(avg_header_row.keys()) + '\n')
        output.write(','.join(map(str, avg_data_row.values())) + '\n')

        # Adaugă rânduri pentru deviațiile de la standard
        output.write("\nDeviatie Fata de Standard:\n")
        dev_header_row = {key: key for key in deviation_from_standard.keys()}
        dev_data_row = {key: (round(value, 2) if value is not None else 'N/A') for key, value in deviation_from_standard.items()}

        output.write(','.join(dev_header_row.keys()) + '\n')
        output.write(','.join(map(str, dev_data_row.values())) + '\n')


        output.seek(0)

        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=statistics.csv"}
        )
    except Exception as e:
        # Arată mai multe detalii despre eroare în consolă pentru depanare
        app.logger.error(f"Eroare la exportul statisticilor: {e}", exc_info=True)
        return jsonify({"error": f"A apărut o eroare la exportul statisticilor: {str(e)}"}), 500


@app.route('/measurements/plot_all', methods=['GET'])
@login_required
def plot_all_graphs():
    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT temperature, humidity, pressure, co, no2, so2, o3, pm25, pm10, `condition`, timestamp
        FROM masuratori
        WHERE user_id=%s ORDER BY timestamp ASC
    """, (user_id,))
    data = cursor.fetchall()
    cursor.close()
    conn.close()

    if not data:
        return jsonify({'error': 'Nicio măsurătoare găsită pentru a trasa grafice'}), 404

    # Extracting data for plots and calculations
    temps = [d['temperature'] for d in data if d['temperature'] is not None]
    hums = [d['humidity'] for d in data if d['humidity'] is not None]
    pressures = [d['pressure'] for d in data if d['pressure'] is not None]
    pm25s = [d['pm25'] for d in data if d['pm25'] is not None]
    pm10s = [d['pm10'] for d in data if d['pm10'] is not None]
    cos = [d['co'] for d in data if d['co'] is not None]
    no2s = [d['no2'] for d in data if d['no2'] is not None]
    so2s = [d['so2'] for d in data if d['so2'] is not None]
    o3s = [d['o3'] for d in data if d['o3'] is not None]
    dates = [d['timestamp'].strftime("%Y-%m-%d %H:%M:%S") for d in data]

    # Calculate AQI for each measurement
    aqi_values = []
    for d in data:
        aqi_val = calculate_aqi(pm25=d.get('pm25'), pm10=d.get('pm10'), co=d.get('co'),
                                 no2=d.get('no2'), so2=d.get('so2'), o3=d.get('o3'))
        if aqi_val is not None:
            aqi_values.append(aqi_val)

    # Medii for all available metrics
    average_values = {
        'temperature': np.mean(temps) if temps else None,
        'humidity': np.mean(hums) if hums else None,
        'pressure': np.mean(pressures) if pressures else None,
        'pm25': np.mean(pm25s) if pm25s else None,
        'pm10': np.mean(pm10s) if pm10s else None,
        'co': np.mean(cos) if cos else None,
        'no2': np.mean(no2s) if no2s else None,
        'so2': np.mean(so2s) if so2s else None,
        'o3': np.mean(o3s) if o3s else None,
        'aqi': np.mean(aqi_values) if aqi_values else None,
    }

    # Standard/Optimal values for deviation calculation (Example values, adjust as needed for research)
    optimal_values = {
        'temperature': 22.0,  # °C, e.g., comfortable indoor temperature
        'humidity': 50.0,     # %, e.g., ideal indoor humidity
        'pressure': 1013.25,  # hPa, standard atmospheric pressure at sea level
        'pm25': 10.0,         # μg/m³, WHO guideline for annual mean
        'pm10': 20.0,         # μg/m³, WHO guideline for annual mean
        'co': 4000.0,         # μg/m³, WHO guideline for 8-hour mean (4 mg/m3)
        'no2': 40.0,          # μg/m³, WHO guideline for annual mean
        'so2': 20.0,          # μg/m³, WHO guideline for 24-hour mean
        'o3': 100.0,          # μg/m³, WHO guideline for 8-hour mean
        'aqi': 50.0           # AQI: Good category max value
    }

    deviation_from_standard = {}
    for key, avg_val in average_values.items():
        if avg_val is not None and key in optimal_values:
            deviation = avg_val - optimal_values[key]
            deviation_from_standard[key] = round(deviation, 2)
        else:
            deviation_from_standard[key] = None

    # Generate plots
    plots = {}
    if temps:
        plots['temperature_plot'] = create_plot(dates, temps, 'Temperatura în timp', 'Data și Ora', 'Temperatură (°C)')
    if hums:
        plots['humidity_plot'] = create_plot(dates, hums, 'Umiditatea în timp', 'Data și Ora', 'Umiditate (%)')
    if pm25s:
        plots['pm25_plot'] = create_plot(dates, pm25s, 'PM2.5 în timp', 'Data și Ora', 'PM2.5 (µg/m3)')
    if pressures:
        plots['pressure_plot'] = create_plot(dates, pressures, 'Presiunea în timp', 'Data și Ora', 'Presiune (hPa)')
    if cos:
        plots['co_plot'] = create_plot(dates, cos, 'CO în timp', 'Data și Ora', 'CO (µg/m3)')
    if no2s:
        plots['no2_plot'] = create_plot(dates, no2s, 'NO2 în timp', 'Data și Ora', 'NO2 (µg/m3)')
    if so2s:
        plots['so2_plot'] = create_plot(dates, so2s, 'SO2 în timp', 'Data și Ora', 'SO2 (µg/m3)')
    if o3s:
        plots['o3_plot'] = create_plot(dates, o3s, 'O3 în timp', 'Data și Ora', 'O3 (µg/m3)')
    if aqi_values:
        plots['aqi_plot'] = create_plot(dates, aqi_values, 'AQI simplificat în timp', 'Data și Ora', 'AQI')

    # Correlation plots
    if len(temps) > 1 and len(hums) > 1: # Need at least 2 points for correlation
        plots['temp_vs_humidity_plot'] = create_plot(temps, hums, 'Temperatură vs. Umiditate', 'Temperatură (°C)', 'Umiditate (%)', plot_type='scatter')
    if len(temps) > 1 and len(pressures) > 1:
        plots['temp_vs_pressure_plot'] = create_plot(temps, pressures, 'Temperatură vs. Presiune', 'Temperatură (°C)', 'Presiune (hPa)', plot_type='scatter')

    # All pollutant correlations
    pollutant_data = {
        'PM2.5': pm25s, 'PM10': pm10s, 'CO': cos, 'NO2': no2s, 'SO2': so2s, 'O3': o3s
    }
    pollutant_names = list(pollutant_data.keys())

    for i in range(len(pollutant_names)):
        for j in range(i + 1, len(pollutant_names)):
            p1_name = pollutant_names[i]
            p2_name = pollutant_names[j]
            p1_values = pollutant_data[p1_name]
            p2_values = pollutant_data[p2_name]

            # Filter out None values and ensure aligned data for correlation
            combined_data = [(data[k][p1_name.lower().replace('.', '')], data[k][p2_name.lower().replace('.', '')])
                             for k in range(len(data))
                             if data[k][p1_name.lower().replace('.', '')] is not None and
                                data[k][p2_name.lower().replace('.', '')] is not None]

            if len(combined_data) > 1:
                x_vals = [item[0] for item in combined_data]
                y_vals = [item[1] for item in combined_data]
                plots[f'{p1_name.lower().replace(".", "")}_vs_{p2_name.lower().replace(".", "")}_plot'] = \
                    create_plot(x_vals, y_vals, f'{p1_name} vs. {p2_name}', p1_name, p2_name, plot_type='scatter')


    response_data = {
        **plots, # Unpack all generated plots
        'average_values': {k: round(v, 2) if v is not None else None for k, v in average_values.items()},
        'deviation_from_standard': {k: round(v, 2) if v is not None else None for k, v in deviation_from_standard.items()}
    }
    return jsonify(response_data)


if __name__ == "__main__":
    app.run(debug=True)
