from flask import Flask, render_template, request, session, redirect, url_for, jsonify
import json
import random
import os
import time

app = Flask(__name__)
app.secret_key = 'super_tajny_klucz_projektu_io'

PROGI = [500, 1000, 2000, 5000, 10000, 20000, 40000, 75000, 125000, 250000, 500000, 1000000]
GWARANTOWANE = {1: 1000, 6: 40000}

# --- FUNKCJE POMOCNICZE ---
def load_json(filename):
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []
    return []

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def save_score(nick, score, badges):
    scores = load_json("wyniki.json")
    scores.append({"nick": nick, "wynik": score, "odznaki": badges})
    scores.sort(key=lambda x: x["wynik"], reverse=True)
    save_json("wyniki.json", scores[:20])

def add_proposal(pytanie, odp_a, odp_b, odp_c, odp_d, poprawna, info):
    propozycje = load_json("propozycje.json")
    nowe = {
        "p": pytanie,
        "odp": [odp_a, odp_b, odp_c, odp_d],
        "ok": poprawna,
        "info": info
    }
    propozycje.append(nowe)
    save_json("propozycje.json", propozycje)

def calculate_badges(is_winner):
    badges = []
    # Odznaka 1: Milioner
    if is_winner: badges.append("🏆 MISTRZ ARCHITEKTURY")
    
    # Odznaka 2: Speedrun (jeśli średnio < 5 sek na pytanie)
    total_time = time.time() - session.get('start_time', time.time())
    questions_passed = session.get('current_index', 1)
    if questions_passed > 0 and (total_time / questions_passed) < 8:
        badges.append("⚡ SZYBKI BILL")

    # Odznaka 3: Wiedza (jeśli doszedł do 40k)
    money = session.get('money', 0)
    if money >= 40000:
        badges.append("🧠 SENIOR DEV")

    return badges

# --- ROUTING (TRASY) ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start', methods=['POST'])
def start():
    nick = request.form.get('nick')
    if not nick: return redirect(url_for('index'))
    
    all_questions = load_json("pytania.json")
    if len(all_questions) < 12:
        return f"Błąd: Za mało pytań w pliku pytania.json ({len(all_questions)}). Potrzeba minimum 12!", 500

    game_questions = random.sample(all_questions, 12)

    session['nick'] = nick
    session['questions'] = game_questions
    session['current_index'] = 0
    session['lifelines'] = {"5050": True, "phone": True, "audience": True}
    session['money'] = 0
    session['start_time'] = time.time()
    
    # Czyścimy bufory
    session.pop('current_options', None)
    session.pop('last_q_index', None)
    session.pop('final_money', None)
    session.pop('earned_badges', None)
    
    return redirect(url_for('game'))

@app.route('/game')
def game():
    if 'questions' not in session: return redirect(url_for('index'))
    
    idx = session['current_index']
    if idx >= 12: return redirect(url_for('result', win=1))

    q_data = session['questions'][idx]
    
    # Mieszanie odpowiedzi
    if 'current_options' not in session or session.get('last_q_index') != idx:
        options = q_data['odp'].copy()
        random.shuffle(options)
        session['current_options'] = options
        session['correct_answer'] = q_data['odp'][0] 
        session['explanation'] = q_data.get('info', 'Brak dodatkowego wyjaśnienia.')
        session['last_q_index'] = idx

    return render_template('game.html', 
                           question=q_data['p'],
                           options=session['current_options'],
                           money=PROGI[idx],
                           q_num=idx+1,
                           lifelines=session['lifelines'])

@app.route('/check', methods=['POST'])
def check():
    answer = request.form.get('answer')
    correct = session.get('correct_answer')
    explanation = session.get('explanation')
    
    if answer == correct:
        session['money'] = PROGI[session['current_index']]
        session['current_index'] += 1
        
        status = 'win' if session['current_index'] >= 12 else 'ok'
        
        if status == 'win': 
            badges = calculate_badges(True)
            session['earned_badges'] = badges
            save_score(session['nick'], 1000000, badges)
            
        return jsonify({
            'status': status, 
            'info': explanation,
            'redirect': url_for('result') if status == 'win' else None
        })
    else:
        # Przegrana
        idx = session['current_index']
        win_amount = 0
        for threshold_idx, amount in GWARANTOWANE.items():
            if idx > threshold_idx: win_amount = amount
        
        badges = calculate_badges(False)
        session['earned_badges'] = badges
        save_score(session['nick'], win_amount, badges)
        session['final_money'] = win_amount
        
        return jsonify({
            'status': 'fail', 
            'correct': correct, 
            'info': explanation,
            'redirect': url_for('result')
        })

@app.route('/lifeline/<type>')
def lifeline(type):
    if not session['lifelines'].get(type):
        return jsonify({'status': 'used'})
    
    lifelines = session['lifelines']
    lifelines[type] = False
    session['lifelines'] = lifelines
    
    if type == '5050':
        correct = session['correct_answer']
        opts = session['current_options']
        wrong = [o for o in opts if o != correct]
        to_remove = random.sample(wrong, 2) if len(wrong) >= 2 else wrong
        return jsonify({'status': 'ok', 'remove': to_remove})
        
    elif type == 'phone':
        correct = session['correct_answer']
        opts = session['current_options']
        if random.random() < 0.85:
            hint = correct
        else:
            wrong_opts = [o for o in opts if o != correct]
            hint = random.choice(wrong_opts) if wrong_opts else correct
        return jsonify({'status': 'ok', 'msg': f"Cześć! Jestem na wykładzie, ale wydaje mi się, że to: {hint}"})
        
    elif type == 'audience':
        correct = session['correct_answer']
        opts = session['current_options']
        stats = {}
        points_left = 100
        correct_share = random.randint(50, 80)
        stats[correct] = correct_share
        points_left -= correct_share
        
        remaining_opts = [o for o in opts if o != correct]
        for i, o in enumerate(remaining_opts):
            if i == len(remaining_opts) - 1:
                share = points_left
            else:
                share = random.randint(0, points_left)
                points_left -= share
            stats[o] = share
        return jsonify({'status': 'ok', 'stats': stats})
    
    return jsonify({'status': 'error'})

@app.route('/result')
def result():
    final_score = session.get('final_money', session.get('money', 0))
    badges = session.get('earned_badges', [])
    return render_template('result.html', score=final_score, nick=session.get('nick', 'Gracz'), badges=badges)

@app.route('/ranking')
def ranking():
    return render_template('ranking.html', scores=load_json("wyniki.json"))

@app.route('/reset_scores', methods=['POST'])
def reset_scores():
    haslo = request.form.get('admin_pass')
    if haslo == 'Teraz_mnie_nie_zgadniesz!420': # HASŁO DO RESETU
        save_json("wyniki.json", [])
        return redirect(url_for('ranking'))
    else:
        return "Błędne hasło!", 403

@app.route('/add_question', methods=['GET', 'POST'])
def add_question():
    if request.method == 'POST':
        p = request.form.get('question')
        good = request.form.get('good_answer')
        bad1 = request.form.get('bad1')
        bad2 = request.form.get('bad2')
        bad3 = request.form.get('bad3')
        info = request.form.get('info')
        
        if p and good and bad1:
            add_proposal(p, good, bad1, bad2, bad3, good, info)
            return render_template('add_question.html', success=True)
            
    return render_template('add_question.html', success=False)

if __name__ == '__main__':

    app.run(host='0.0.0.0', port=5000, debug=True)
