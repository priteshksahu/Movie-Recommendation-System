from flask import Flask, render_template, jsonify, request, redirect, url_for
import requests
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import random
from pyngrok import ngrok
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)  # or use a fixed string like 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///movies.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)  # Set session lifetime
db = SQLAlchemy(app)

# OMDB API Configuration
OMDB_API_KEY = "44991f2d"
OMDB_BASE_URL = "http://www.omdbapi.com/"
OMDB_POSTER_URL = "http://img.omdbapi.com/"

# Add this line after imports
ngrok.set_auth_token('YOUR_NGROK_AUTH_TOKEN')

# Add after creating Flask app
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))  # Increased length for password hash
    date_registered = db.Column(db.DateTime, default=datetime.utcnow)
    favorites = db.relationship('Favorite', backref='user', lazy=True, cascade="all, delete-orphan")
    watchlist = db.relationship('WatchLater', backref='user', lazy=True, cascade="all, delete-orphan")

    def __init__(self, username, email):
        self.username = username
        self.email = email

    def set_password(self, password):
        if not password:
            raise ValueError("Password cannot be empty")
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

class Favorite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    movie_id = db.Column(db.String(20), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date_added = db.Column(db.DateTime, default=datetime.utcnow)

class WatchLater(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    movie_id = db.Column(db.String(20), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date_added = db.Column(db.DateTime, default=datetime.utcnow)

def fetch_omdb_data(params):
    """Fetch data from OMDB API"""
    try:
        params['apikey'] = OMDB_API_KEY
        response = requests.get(OMDB_BASE_URL, params=params)
        return response.json()
    except Exception as e:
        print(f"OMDB API Error: {str(e)}")
        return None

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/search')
def search():
    return render_template('search.html')

@app.route('/favorites')
@login_required
def favorites():
    return render_template('favorites.html')

@app.route('/watchlist')
@login_required
def watchlist():
    return render_template('watchlist.html')

@app.route('/movies')
def movies_page():
    return render_template('movies.html')

@app.route('/api/movies')
def get_movies():
    # Expanded list of popular movie IDs
    all_movies = [
        "tt0111161", "tt0068646", "tt0071562", "tt0468569", "tt0050083",
        "tt0108052", "tt0167260", "tt0110912", "tt0060196", "tt0137523",
        "tt0120737", "tt0109830", "tt0133093", "tt0080684", "tt0167261",
        "tt0073486", "tt0099685", "tt0047478", "tt0076759", "tt0120815",
        "tt0317248", "tt0114369", "tt0102926", "tt0038650", "tt0118799",
        "tt0110413", "tt0064116", "tt0245429", "tt0120586", "tt0816692"
    ]
    
    # Randomly select 10 movies
    selected_movies = random.sample(all_movies, min(10, len(all_movies)))
    
    movies = []
    for movie_id in selected_movies:
        movie_data = fetch_omdb_data({'i': movie_id, 'plot': 'full'})
        if movie_data:
            streaming = get_streaming_platforms(movie_data.get('Title', ''))
            movies.append({
                'id': movie_id,
                'title': movie_data.get('Title', ''),
                'year': movie_data.get('Year', ''),
                'poster': movie_data.get('Poster', ''),
                'rating': movie_data.get('imdbRating', 'N/A'),
                'plot': movie_data.get('Plot', ''),
                'genre': movie_data.get('Genre', ''),
                'runtime': movie_data.get('Runtime', ''),
                'director': movie_data.get('Director', ''),
                'actors': movie_data.get('Actors', ''),
                'awards': movie_data.get('Awards', ''),
                'metascore': movie_data.get('Metascore', 'N/A'),
                'streaming': streaming
            })
    
    return jsonify(movies)

@app.route('/api/movie/<movie_id>')
def get_movie_details(movie_id):
    movie_data = fetch_omdb_data({'i': movie_id, 'plot': 'full'})
    if movie_data:
        return jsonify(movie_data)
    return jsonify({"error": "Movie not found"})

@app.route('/api/favorite', methods=['POST'])
@login_required
def add_favorite():
    data = request.json
    movie_id = data.get('movie_id')
    new_favorite = Favorite(movie_id=movie_id, user_id=current_user.id)
    db.session.add(new_favorite)
    db.session.commit()
    return jsonify({"status": "success"})

@app.route('/api/search')
def search_movies():
    query = request.args.get('q', '')
    if not query:
        return jsonify([])
    
    try:
        # Search for movies using OMDB API
        search_results = fetch_omdb_data({
            's': query,
            'type': 'movie'
        })
        
        if search_results and 'Search' in search_results:
            movies = search_results['Search']
            formatted_results = []
            
            # Fetch detailed information for each movie
            for movie in movies:
                movie_id = movie.get('imdbID')
                if movie_id:
                    details = fetch_omdb_data({'i': movie_id})
                    if details:
                        formatted_movie = {
                            'id': movie_id,
                            'title': details.get('Title', ''),
                            'year': details.get('Year', ''),
                            'poster': details.get('Poster', ''),
                            'rating': details.get('imdbRating', 'N/A'),
                            'plot': details.get('Plot', ''),
                            'genre': details.get('Genre', ''),
                            'director': details.get('Director', ''),
                            'actors': details.get('Actors', ''),
                            'runtime': details.get('Runtime', '')
                        }
                        formatted_results.append(formatted_movie)
            
            return jsonify(formatted_results)
        return jsonify([])
    except Exception as e:
        print(f"Search error: {str(e)}")
        return jsonify([])

@app.route('/api/watchlist', methods=['POST'])
@login_required
def add_to_watchlist():
    data = request.json
    movie_id = data.get('movie_id')
    new_watchlist = WatchLater(movie_id=movie_id, user_id=current_user.id)
    db.session.add(new_watchlist)
    db.session.commit()
    return jsonify({"status": "success"})

@app.route('/api/favorites')
@login_required
def get_favorites():
    favorites = Favorite.query.filter_by(user_id=current_user.id).all()
    favorite_movies = []
    
    for favorite in favorites:
        movie_data = fetch_omdb_data({'i': favorite.movie_id})
        if movie_data:
            favorite_movies.append({
                'id': favorite.movie_id,
                'title': movie_data.get('Title', ''),
                'year': movie_data.get('Year', ''),
                'poster': movie_data.get('Poster', ''),
                'rating': movie_data.get('imdbRating', 'N/A'),
                'genre': movie_data.get('Genre', ''),
                'plot': movie_data.get('Plot', '')
            })
    
    return jsonify(favorite_movies)

@app.route('/api/favorite/<movie_id>', methods=['DELETE'])
@login_required
def remove_favorite(movie_id):
    Favorite.query.filter_by(user_id=current_user.id, movie_id=movie_id).delete()
    db.session.commit()
    return jsonify({"status": "success"})

@app.route('/api/watchlist')
@login_required
def get_watchlist():
    watchlist = WatchLater.query.filter_by(user_id=current_user.id).all()
    watchlist_movies = []
    
    for item in watchlist:
        movie_data = fetch_omdb_data({'i': item.movie_id})
        if movie_data:
            watchlist_movies.append({
                'id': item.movie_id,
                'title': movie_data.get('Title', ''),
                'year': movie_data.get('Year', ''),
                'poster': movie_data.get('Poster', ''),
                'rating': movie_data.get('imdbRating', 'N/A'),
                'genre': movie_data.get('Genre', ''),
                'plot': movie_data.get('Plot', '')
            })
    
    return jsonify(watchlist_movies)

@app.route('/api/watchlist/<movie_id>', methods=['DELETE'])
@login_required
def remove_from_watchlist(movie_id):
    WatchLater.query.filter_by(user_id=current_user.id, movie_id=movie_id).delete()
    db.session.commit()
    return jsonify({"status": "success"})

@app.route('/api/movies/category/<category>')
def get_movies_by_category(category):
    # Map categories to movie IDs or use an API that supports category filtering
    category_movies = {
        'trending': [
            "tt0468569", "tt1375666", "tt0816692", "tt0133093", 
            "tt0109830", "tt0110912", "tt0114369", "tt0137523"
        ],
        'latest': [
            "tt9362722", "tt1160419", "tt7286456", "tt4154796", 
            "tt6751668", "tt8579674", "tt1877830", "tt2382320"
        ],
        'action': [
            "tt0468569", "tt0133093", "tt0172495", "tt0082971", 
            "tt0083658", "tt0088247", "tt0090605", "tt0093773"
        ],
        'drama': [
            "tt0111161", "tt0068646", "tt0071562", "tt0050083", 
            "tt0108052", "tt0167260", "tt0120737", "tt0109830"
        ],
        'comedy': [
            "tt0118799", "tt0110912", "tt0107290", "tt0116629", 
            "tt0119654", "tt0128445", "tt0151804", "tt0163651"
        ]
    }
    
    movie_ids = category_movies.get(category, [])
    movies = []
    
    for movie_id in movie_ids:
        movie_data = fetch_omdb_data({'i': movie_id, 'plot': 'full'})
        if movie_data:
            streaming = get_streaming_platforms(movie_data.get('Title', ''))
            movies.append({
                'id': movie_id,
                'title': movie_data.get('Title', ''),
                'year': movie_data.get('Year', ''),
                'poster': movie_data.get('Poster', ''),
                'rating': movie_data.get('imdbRating', 'N/A'),
                'plot': movie_data.get('Plot', ''),
                'genre': movie_data.get('Genre', ''),
                'runtime': movie_data.get('Runtime', ''),
                'director': movie_data.get('Director', ''),
                'actors': movie_data.get('Actors', ''),
                'awards': movie_data.get('Awards', ''),
                'metascore': movie_data.get('Metascore', 'N/A'),
                'streaming': streaming
            })
    
    return jsonify(movies)

# Add this function to check streaming availability (you can expand this with real API data)
def get_streaming_platforms(movie_title):
    # This is a mock function - in a real app, you'd want to use a streaming availability API
    # You can use services like Watchmode API or JustWatch API for real data
    platforms = {
        "The Godfather": ["netflix", "prime", "hulu"],
        "Pulp Fiction": ["netflix", "prime"],
        "The Dark Knight": ["hbo", "prime"],
        "Inception": ["netflix", "hbo"],
        # Add more movies and their platforms
    }
    return platforms.get(movie_title, ["prime"])  # Default to Prime if not found

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        data = request.json
        user = User.query.filter_by(email=data.get('email')).first()
        
        if user and user.check_password(data.get('password')):
            login_user(user)
            return jsonify({"status": "success", "redirect": url_for('home')})
        
        return jsonify({"status": "error", "message": "Invalid email or password"}), 401
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        try:
            data = request.json
            
            # Validate required fields
            if not all([data.get('username'), data.get('email'), data.get('password')]):
                return jsonify({
                    "status": "error",
                    "message": "All fields are required"
                }), 400
            
            # Check if email exists
            if User.query.filter_by(email=data.get('email')).first():
                return jsonify({
                    "status": "error",
                    "message": "Email already registered"
                }), 400
            
            # Check if username exists
            if User.query.filter_by(username=data.get('username')).first():
                return jsonify({
                    "status": "error",
                    "message": "Username already taken"
                }), 400
            
            # Create new user
            user = User(
                username=data.get('username'),
                email=data.get('email')
            )
            user.set_password(data.get('password'))
            
            try:
                db.session.add(user)
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f"Database error: {str(e)}")
                return jsonify({
                    "status": "error",
                    "message": "Database error occurred"
                }), 500
            
            login_user(user)
            return jsonify({
                "status": "success",
                "redirect": url_for('home')
            })
            
        except Exception as e:
            print(f"Registration error: {str(e)}")
            return jsonify({
                "status": "error",
                "message": "An error occurred during registration"
            }), 500
    
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

def init_db():
    with app.app_context():
        # Drop all tables
        db.drop_all()
        # Create all tables
        db.create_all()
        print("Database initialized successfully!")

if __name__ == '__main__':
    init_db()  # Initialize database on startup
    app.run(debug=True, host='0.0.0.0', port=5000) 