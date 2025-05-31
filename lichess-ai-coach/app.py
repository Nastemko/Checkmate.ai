# app.py
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS # Import CORS
import requests
import google.generativeai as genai
import chess.pgn
import io
import json # Import json for json.loads

app = Flask(__name__, static_folder='static', static_url_path='') # Configure static folder
CORS(app) # Enable CORS for all routes

# --- Configuration (replace with your actual API key) ---
# It's highly recommended to use environment variables for API keys
# For development, you can put it here, but for deployment, use .env or similar
# For demonstration purposes, I'll hardcode, but please use os.getenv() in real app
GOOGLE_API_KEY = "YOUR_GEMINI_API_KEY" # <--- REPLACE WITH YOUR ACTUAL GEMINI API KEY
genai.configure(api_key=GOOGLE_API_KEY)

# --- Lichess API Integration ---
# You'll likely need to parse the streamed response
def get_lichess_games(username):
    # Lichess streams data as NDJSON (Newline Delimited JSON)
    url = f"https://lichess.org/api/games/user/{username}?tags=true&clocks=false&evals=false&opening=false&literate=false"
    headers = {"Accept": "application/x-ndjson"}
    try:
        response = requests.get(url, headers=headers, stream=True)
        response.raise_for_status() # Raise an exception for HTTP errors

        games_data = []
        # Iterate over lines for streamed NDJSON response
        for line in response.iter_lines():
            if line:
                try:
                    game_json = json.loads(line.decode('utf-8'))
                    games_data.append(game_json)
                except json.JSONDecodeError:
                    print(f"Error decoding JSON line from Lichess API: {line}")
        return games_data
    except requests.exceptions.RequestException as e:
        print(f"Error fetching games from Lichess: {e}")
        return None

# --- Gemini LLM Integration ---
def analyze_games_with_gemini(games_list):
    model = genai.GenerativeModel('gemini-1.5-flash') # Or 'gemini-1.5-flash-latest'

    # Convert a subset of game data into a textual format for the LLM
    # You might want to be selective about what data you send to keep token usage down
    # and focus on the most relevant information for trends.
    # Limiting to a reasonable number of games for the prompt
    selected_games = games_list[:20] # Adjust this number based on token limits and desired depth

    if not selected_games:
        return "No recent games found to analyze. Play some more games on Lichess!"

    game_summaries = []
    for i, game in enumerate(selected_games):
        moves = game.get('moves', '')
        # Determine outcome from Lichess API response structure
        # 'winner' field might be 'white' or 'black'
        # 'status' might be 'draw', 'timeout', 'resign', 'mate', etc.
        # This part might need adjustment based on the exact Lichess API JSON structure for specific outcomes.
        outcome_detail = game.get('status', 'unknown')
        winner_id = game.get('winner') # 'white' or 'black'

        # Simplified outcome for LLM
        if outcome_detail == 'draw':
            outcome_str = "draw"
        elif winner_id == game['players']['white']['user']['id']:
             outcome_str = f"White ({game['players']['white']['user']['id']}) won"
        elif winner_id == game['players']['black']['user']['id']:
             outcome_str = f"Black ({game['players']['black']['user']['id']}) won"
        else:
            outcome_str = "undetermined"

        game_summaries.append(f"Game {i+1} (ID: {game.get('id', 'N/A')}, Rating: {game['players']['white'].get('rating', 'N/A') if game['players']['white']['user']['id'] else 'N/A'} vs {game['players']['black'].get('rating', 'N/A') if game['players']['black']['user']['id'] else 'N/A'}): Result: {outcome_str}. First 50 moves: {moves[:200]}...") # Truncate moves for brevity


    prompt = f"""You are a personalized chess coach. I have played many games on Lichess.org.
    I want to understand the general themes and trends in my gameplay in simple, colloquial terms.
    Do not use technical chess jargon like specific opening names (e.g., "Sicilian Defense," "Ruy Lopez") or complex tactical terms.
    Instead, focus on broad strategic patterns, common mistakes, and areas for improvement.
    
    Here is a summary of some of my recent games (first 20 games are provided):
    {'\n'.join(game_summaries)}

    Based on these games, what are some observable patterns in my play?
    Suggest high-level strategic approaches I could consider to improve, explained simply.
    Keep the analysis concise and actionable, focusing on 2-3 main points.
    """

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        return "Sorry, I couldn't analyze your games right now due to an issue with the AI service. Please try again later."

# --- API Endpoints ---

# Route for the root URL, serving your index.html
@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/analyze_chess', methods=['POST'])
def analyze_chess():
    data = request.json
    username = data.get('username')

    if not username:
        return jsonify({"error": "Lichess username is required."}), 400

    games = get_lichess_games(username)
    if not games:
        return jsonify({"error": "Could not retrieve games from Lichess. Check username, privacy settings, or try again later."}), 500

    # You'd typically want to preprocess and select the most relevant games
    # and data points before sending to the LLM to manage token limits and focus the analysis.
    # For now, we'll send a subset as defined in analyze_games_with_gemini.

    llm_analysis = analyze_games_with_gemini(games)
    return jsonify({"analysis": llm_analysis})

if __name__ == '__main__':
    # When deploying, ensure debug is False and host is '0.0.0.0' for external access
    app.run(debug=True, host='0.0.0.0')
