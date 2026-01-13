from flask import Flask, render_template, request, session, redirect, url_for, jsonify
import json
import random
import os
import time

app = Flask(__name__)
app.secret_key = 'super_tajny_klucz_projektu_io'

# Konfiguracja progów pieniężnych dla trybu klasycznego
PROGI = [500, 1000, 2000, 5000, 10000, 20000, 40000, 75000, 125000, 250000, 500000, 1000000]
GWARANTOWANE = {1: 1000, 6: 40000}  # Indeksy progów gwarantowanych (0-indexed logic)


# --- FUNKCJE POMOCNICZE DO OBSŁUGI PLIKÓW JSON ---
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
    # Tryb nauki nie zapisuje wyników do rankingu
    if session.get('mode') == 'learning':
        return
    scores = load_json("wyniki.json")
    scores.append({
        "nick": nick,
        "wynik": score,
        "odznaki": badges,
        "data": time.strftime("%Y-%m-%d %H:%M")
    })
    # Sortowanie po wyniku (malejąco) i zachowanie top 20
    scores.sort(key=lambda x: x["wynik"], reverse=True)
    save_json("wyniki.json", scores[:20])


def calculate_badges(is_winner):
    badges = []
    if is_winner:
        badges.append("🏆 MISTRZ ARCHITEKTURY")

    total_time = time.time() - session.get('start_time', time.time())
    q_passed = session.get('current_index', 1)

    # Odznaka za szybkość (średnio poniżej 8 sek na pytanie)
    if q_passed > 0 and (total_time / q_passed) < 8:
        badges.append("⚡ SZYBKI BILL")

    # Odznaka za poziom wiedzy
    if session.get('money', 0) >= 40000:
        badges.append("🧠 SENIOR DEV")

    return badges


# --- ROUTING (TRASY) ---

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/start', methods=['POST'])
def start():
    nick = request.form.get('nick')
    mode = request.form.get('mode', 'classic')
    if not nick: return redirect(url_for('index'))

    all_questions = load_json("pytania.json")

    # Liczba pytań zależna od trybu (Bet: 8, Reszta: 12)
    num_q = 8 if mode == 'bet' else 12
    if len(all_questions) < num_q:
        return f"Błąd: Za mało pytań w bazie danych! (Posiadasz {len(all_questions)}, wymagane {num_q})", 500

    # Inicjalizacja sesji gry
    session.clear()
    session['nick'] = nick
    session['mode'] = mode
    session['questions'] = random.sample(all_questions, num_q)
    session['current_index'] = 0
    # Inicjalizacja kół ratunkowych (nawet jeśli tryb ich nie używa, inicjalizujemy dla bezpieczeństwa)
    session['lifelines'] = {"5050": True, "phone": True, "audience": True}
    session['money'] = 1000000 if mode == 'bet' else 0
    session['start_time'] = time.time()

    return redirect(url_for('game'))


@app.route('/game')
def game():
    if 'questions' not in session:
        return redirect(url_for('index'))

    idx = session['current_index']
    if idx >= len(session['questions']):
        return redirect(url_for('result'))

    q_data = session['questions'][idx]

    # Zabezpieczenie przed zmianą kolejności odpowiedzi przy odświeżaniu strony
    if 'current_options' not in session or session.get('last_q_index') != idx:
        options = q_data['odp'].copy()
        random.shuffle(options)
        session['current_options'] = options
        session['correct_answer'] = q_data['odp'][0]  # Pierwsza w JSON zawsze poprawna
        session['explanation'] = q_data.get('info', 'Brak dodatkowego wyjaśnienia.')
        session['last_q_index'] = idx

    return render_template('game.html',
                           question=q_data['p'],
                           options=session['current_options'],
                           money=session['money'] if session['mode'] == 'bet' else PROGI[idx],
                           q_num=idx + 1,
                           total_q=len(session['questions']),
                           mode=session['mode'],
                           lifelines=session['lifelines'],
                           thresholds=PROGI)  # Przekazanie listy progów do szablonu


@app.route('/check', methods=['POST'])
def check():
    mode = session.get('mode')
    correct = session.get('correct_answer')
    explanation = session.get('explanation')

    # --- LOGIKA DLA TRYBU: POSTAW NA MILION ---
    if mode == 'bet':
        data = request.get_json()
        bets = data.get('bets', {})
        win_amount = int(bets.get(correct, 0))
        session['money'] = win_amount
        session['current_index'] += 1

        if win_amount <= 0:
            save_score(session['nick'], 0, [])
            return jsonify({
                'status': 'fail',
                'info': f"Straciłeś cały kapitał! Poprawna odpowiedź to: <b>{correct}</b>",
                'redirect': url_for('result')
            })

        if session['current_index'] >= len(session['questions']):
            save_score(session['nick'], win_amount, ["💰 STRATEG"])
            return jsonify({
                'status': 'win',
                'info': f"GRATULACJE! Ukończyłeś wyzwanie z kwotą {win_amount} PLN!",
                'redirect': url_for('result')
            })

        return jsonify({
            'status': 'ok',
            'info': f"Dobrze! Na Twoim koncie zostaje <b>{win_amount} PLN</b>.",
            'redirect': None
        })

    # --- LOGIKA DLA TRYBU: KLASYCZNY / NAUKA ---
    answer = request.form.get('answer')
    if answer == correct:
        session['money'] = PROGI[session['current_index']]
        session['current_index'] += 1
        is_end = session['current_index'] >= 12

        if is_end:
            badges = calculate_badges(True)
            save_score(session['nick'], 1000000, badges)
            session['earned_badges'] = badges

        return jsonify({
            'status': 'win' if is_end else 'ok',
            'info': explanation,
            'redirect': url_for('result') if is_end else None
        })
    else:
        # Przegrana lub Tryb Nauki
        if mode == 'learning':
            session['current_index'] += 1
            is_end = session['current_index'] >= 12
            msg = f"<span style='color:red'>BŁĄD!</span> Poprawna odpowiedź to: <b>{correct}</b>.<br><br>{explanation}"
            return jsonify({
                'status': 'ok',
                'info': msg,
                'redirect': url_for('result') if is_end else None
            })
        else:
            # Klasyczna przegrana - obliczanie kwoty gwarantowanej
            idx = session['current_index']
            win_amount = 0

            # Progi gwarantowane: 1000 (po 2 pyt) i 40000 (po 7 pyt)
            if idx > 6:
                win_amount = 40000
            elif idx > 1:
                win_amount = 1000

            badges = calculate_badges(False)
            save_score(session['nick'], win_amount, badges)
            session['money'] = win_amount
            session['earned_badges'] = badges

            return jsonify({
                'status': 'fail',
                'info': f"Błędna odpowiedź! Poprawna to: <b>{correct}</b>.<br><br>{explanation}",
                'redirect': url_for('result')
            })


@app.route('/lifeline/<type>')
def lifeline(type):
    # Blokada kół ratunkowych w trybach innych niż klasyczny
    if session.get('mode') != 'classic':
        return jsonify({'status': 'error', 'msg': 'Koła niedostępne w tym trybie'})

    if not session.get('lifelines', {}).get(type):
        return jsonify({'status': 'used'})

    lifelines = session['lifelines']
    lifelines[type] = False
    session['lifelines'] = lifelines

    if type == '5050':
        correct = session['correct_answer']
        wrong = [o for o in session['current_options'] if o != correct]
        # Zwracamy 2 błędne do ukrycia
        return jsonify({'status': 'ok', 'remove': random.sample(wrong, 2)})
    elif type == 'phone':
        # Symulacja telefonu - 80% szans na poprawną
        is_correct = random.random() < 0.8
        ans = session['correct_answer'] if is_correct else random.choice(session['current_options'])

        # Nowa treść wiadomości
        msg_text = (
            f"Dzwonisz do eksperta...<br><br>"
            f"<b>dr hab. Viktoriia Onyshchenko:</b><br>"
            f"<i>\"Przeanalizowałam strukturę tego problemu. "
            f"Biorąc pod uwagę zasady inżynierii oprogramowania, "
            f"wskazałabym na odpowiedź: <b>{ans}</b>.\"</i>"
        )

        return jsonify({'status': 'ok', 'msg': msg_text})
    elif type == 'audience':
        return jsonify({'status': 'ok',
                        'msg': f"Głosowanie publiczności zakończone.<br>Większość (65%) wskazuje na: <b>{session['correct_answer']}</b>"})

    return jsonify({'status': 'error'})


@app.route('/result')
def result():
    return render_template('result.html',
                           score=session.get('money', 0),
                           nick=session.get('nick', 'Agent'),
                           badges=session.get('earned_badges', []),
                           mode=session.get('mode'))


@app.route('/ranking')
def ranking():
    return render_template('ranking.html', scores=load_json("wyniki.json"))


@app.route('/add_question', methods=['GET', 'POST'])
def add_question():
    if request.method == 'POST':
        propozycje = load_json("propozycje.json")
        nowe = {
            "p": request.form.get('question'),
            "odp": [request.form.get('good_answer'), request.form.get('bad1'), request.form.get('bad2'),
                    request.form.get('bad3')],
            "ok": request.form.get('good_answer'),
            "info": request.form.get('info')
        }
        propozycje.append(nowe)
        save_json("propozycje.json", propozycje)
        return render_template('add_question.html', success=True)
    return render_template('add_question.html', success=False)


@app.route('/reset_scores', methods=['POST'])
def reset_scores():
    if request.form.get('admin_pass') == 'admin':
        save_json("wyniki.json", [])
    return redirect(url_for('ranking'))


if __name__ == '__main__':
    # Uruchomienie serwera
    app.run(debug=True, host='0.0.0.0', port=5000)