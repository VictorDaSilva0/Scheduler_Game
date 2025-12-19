import dash
from dash import dcc, html, Input, Output, State, ctx, ALL
import plotly.express as px
import pandas as pd
import random
import base64

# --- CONFIGURATION ---
QUANTUM = 3
MAX_IO_DURATION = 6
INITIAL_LIVES = 3


# --- FONCTIONS UTILITAIRES ---

def parse_uploaded_file(contents):
    """Lit le fichier texte et retourne la liste des processus."""
    try:
        content_type, content_string = contents.split(',')
        decoded = base64.b64decode(content_string)
        text = decoded.decode('utf-8')

        processes = []
        lines = text.strip().split('\n')

        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 6:
                nom = parts[0]
                arr = int(parts[1])
                burst = int(parts[2])
                io_start = int(parts[3])
                io_dur = int(parts[4])
                prio = int(parts[5])

                io_plan = []
                if io_start >= 0:
                    io_plan = [io_start]

                processes.append({
                    "pid": nom,
                    "arrival_time": arr,
                    "burst_time": burst,
                    "remaining_time": burst,
                    "executed_time": 0,
                    "io_plan": io_plan,
                    "io_duration_fixed": io_dur,
                    "priority": prio,
                    "state": "FUTURE",
                    "wait_time_remaining": 0,
                    "consecutive_cpu": 0,
                    "just_finished": False
                })

        if processes:
            min_arr = min(p["arrival_time"] for p in processes)
            for p in processes:
                p["arrival_time"] -= min_arr
                if p["arrival_time"] == 0:
                    p["state"] = "READY"

        return processes
    except Exception as e:
        print(f"Erreur lecture fichier : {e}")
        return None


def generate_random_processes(count=6):
    processes = []
    for i in range(count):
        burst = random.randint(5, 15)
        nb_io = random.choice([0, 0, 1, 1, 2])
        io_plan = []
        if nb_io > 0 and burst > 2:
            possible_ticks = range(1, burst)
            try:
                io_plan = sorted(random.sample(possible_ticks, nb_io))
            except ValueError:
                io_plan = []

        processes.append({
            "pid": f"P{i + 1}",
            "arrival_time": random.randint(0, 5),
            "burst_time": burst,
            "remaining_time": burst,
            "executed_time": 0,
            "io_plan": io_plan,
            "io_duration_fixed": None,
            "priority": random.randint(1, 10),
            "state": "FUTURE",
            "wait_time_remaining": 0,
            "consecutive_cpu": 0,
            "just_finished": False
        })

    if not any(p["arrival_time"] == 0 for p in processes):
        processes[0]["arrival_time"] = 0
    for p in processes:
        if p["arrival_time"] == 0: p["state"] = "READY"

    return processes


def generate_initial_state(processes=None, count=6):
    if processes is None:
        processes = generate_random_processes(count)

    return {
        "processes": processes,
        "initial_setup": processes,  # Sauvegarde pour le Reset exact
        "current_time": 0,
        "history": [],
        "game_over": False,
        "rr_queue": [],
        "score": 0,
        "lives": INITIAL_LIVES,
        "log": [f"⚙️ Nouvelle partie générée avec {len(processes)} processus."],
        "last_pid": None
    }


# --- MOTEUR DE JEU ---

def process_step(game_state, selected_pid=None, mode="MANUAL", rules=[]):
    processes = game_state["processes"]
    current_time = game_state["current_time"]
    history = game_state["history"]
    log = game_state["log"]
    rr_queue = game_state["rr_queue"]
    score = game_state.get("score", 0)
    lives = game_state.get("lives", INITIAL_LIVES)

    # 0. RESET ANIM
    for p in processes: p["just_finished"] = False

    # 1. MISE A JOUR TEMPORELLE (AVANT DÉCISION)
    rr_queue = [pid for pid in rr_queue if any(p['pid'] == pid and p['state'] != "TERMINATED" for p in processes)]

    # a. Arrivées
    for p in processes:
        if p["state"] == "FUTURE" and p["arrival_time"] <= current_time:
            p["state"] = "READY"
            log.append(f"✨ T={current_time}: {p['pid']} est arrivé.")
            if p["pid"] not in rr_queue: rr_queue.append(p["pid"])

    # b. Retours E/S
    for p in processes:
        if p["state"] == "WAITING":
            p["wait_time_remaining"] -= 1
            if p["wait_time_remaining"] > 0:
                history.append({"Processus": p["pid"], "Début": current_time, "Fin": current_time + 1, "Type": "IO"})
            else:
                p["state"] = "READY"
                log.append(f"🔙 T={current_time}: {p['pid']} revient d'E/S.")
                if p["pid"] not in rr_queue: rr_queue.append(p["pid"])

    # c. Reset Running
    for p in processes:
        if p["state"] == "RUNNING": p["state"] = "READY"

    ready_procs_real = [p for p in processes if p["state"] in ["READY"]]
    unfinished = [p for p in processes if p["state"] != "TERMINATED"]
    if not unfinished:
        game_state["game_over"] = True
        log.append(f"🏆 VICTOIRE ! Score Final: {score}")
        return game_state

    # 2. CONFIGURATION REGLES
    use_priority = 'PRIO' in rules
    allow_preemption = 'PREEMPT' in rules
    use_rr = 'RR' in rules

    # 3. DECISION
    chosen_proc = None
    running_proc = next((p for p in processes if p["pid"] == game_state.get('last_pid')), None)
    error_msg = None

    if mode == "MANUAL":
        if not selected_pid:
            if ready_procs_real:
                error_msg = "⛔ INTERDIT : Pas de temps mort (IDLE) autorisé !"
        else:
            candidate = next((p for p in processes if p["pid"] == selected_pid), None)
            if not candidate or candidate not in ready_procs_real:
                error_msg = f"⛔ {selected_pid} non dispo !"
            elif use_rr:
                valid_queue = [pid for pid in rr_queue if pid in [p['pid'] for p in ready_procs_real]]
                if valid_queue and candidate["pid"] != valid_queue[0]:
                    error_msg = f"⛔ ROUND ROBIN : Tour de {valid_queue[0]} !"
            elif use_priority and not use_rr and ready_procs_real:
                max_prio = max([p["priority"] for p in ready_procs_real])
                if candidate["priority"] < max_prio:
                    better = next(p for p in ready_procs_real if p["priority"] == max_prio)
                    error_msg = f"⛔ PRIORITÉ : {better['pid']} est prioritaire ({better['priority']}) !"
            elif not allow_preemption and running_proc and running_proc["state"] == "READY" and candidate["pid"] != \
                    running_proc["pid"]:
                error_msg = f"⛔ NON-PRÉEMPTION : Finissez {running_proc['pid']} !"

            if not error_msg:
                chosen_proc = candidate
                score += 10

    else:  # MODE AUTO
        if ready_procs_real:
            ready_procs_real.sort(key=lambda x: x["arrival_time"])
            if use_priority: ready_procs_real.sort(key=lambda x: x["priority"], reverse=True)

            if use_rr:
                valid_queue = [pid for pid in rr_queue if pid in [p['pid'] for p in ready_procs_real]]
                if valid_queue:
                    next_pid = valid_queue[0]
                    chosen_proc = next((p for p in ready_procs_real if p["pid"] == next_pid), ready_procs_real[0])
                else:
                    chosen_proc = ready_procs_real[0]
            else:
                chosen_proc = ready_procs_real[0]

            if not allow_preemption and running_proc and running_proc in ready_procs_real:
                chosen_proc = running_proc

    if error_msg:
        lives -= 1
        log.append(f"{error_msg} 💔")
        if lives <= 0:
            game_state["game_over"] = True
            log.append("💀 GAME OVER")
        game_state["lives"] = lives
        game_state["log"] = log[-6:]
        return game_state

    # 4. EXECUTION
    if chosen_proc:
        chosen_proc["state"] = "RUNNING"
        chosen_proc["remaining_time"] -= 1
        chosen_proc["executed_time"] += 1
        chosen_proc["consecutive_cpu"] += 1

        history.append({"Processus": chosen_proc["pid"], "Début": current_time, "Fin": current_time + 1, "Type": "CPU"})
        log.append(f"⚡ T={current_time}: {chosen_proc['pid']} exécute.")

        if chosen_proc["remaining_time"] <= 0:
            chosen_proc["state"] = "TERMINATED"
            chosen_proc["just_finished"] = True
            score += 100
            if chosen_proc["pid"] in rr_queue: rr_queue.remove(chosen_proc["pid"])
            log.append(f"🎉 {chosen_proc['pid']} Fini !")

        elif chosen_proc["executed_time"] in chosen_proc["io_plan"]:
            chosen_proc["state"] = "WAITING"
            if chosen_proc.get("io_duration_fixed") and chosen_proc["io_duration_fixed"] > 0:
                chosen_proc["wait_time_remaining"] = chosen_proc["io_duration_fixed"]
            else:
                chosen_proc["wait_time_remaining"] = random.randint(2, MAX_IO_DURATION)
            chosen_proc["consecutive_cpu"] = 0
            if chosen_proc["pid"] in rr_queue: rr_queue.remove(chosen_proc["pid"])
            log.append(f"⚠️ {chosen_proc['pid']} part en E/S.")

        elif use_rr:
            if chosen_proc["pid"] in rr_queue:
                rr_queue.pop(0)
                rr_queue.append(chosen_proc["pid"])
    else:
        log.append("💤 IDLE")
        history.append({"Processus": "IDLE", "Début": current_time, "Fin": current_time + 1, "Type": "IDLE"})

    game_state["current_time"] += 1
    game_state["rr_queue"] = rr_queue
    game_state["score"] = score
    game_state["lives"] = lives
    game_state["log"] = log[-6:]
    game_state["last_pid"] = chosen_proc["pid"] if chosen_proc else None

    return game_state


# --- INTERFACE ---

app = dash.Dash(__name__, external_stylesheets=['https://codepen.io/chriddyp/pen/bWLwgP.css'])
app.title = "Simulateur OS Ultimate"

app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <style>
            @keyframes boom { 0% { transform: scale(0.5); opacity: 1; } 100% { transform: scale(2.5); opacity: 0; } }
            .explosion { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-size: 4rem; animation: boom 0.5s forwards; pointer-events: none; }
            .no-select { user-select: none; }
        </style>
    </head>
    <body>{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body>
</html>
'''

app.layout = html.Div([
    dcc.Store(id='game-store', data=generate_initial_state(count=6)),
    dcc.Interval(id='auto-timer', interval=600, disabled=True),

    html.H1("⚡ Simulateur d'Ordonnancement", style={'textAlign': 'center'}),

    html.Div([
        # Zone Upload
        dcc.Upload(id='upload-data', children=html.Div(['📂 Glissez un fichier .txt']),
                   style={'width': '100%', 'height': '60px', 'lineHeight': '60px', 'borderWidth': '1px',
                          'borderStyle': 'dashed', 'borderRadius': '5px', 'textAlign': 'center', 'margin': '10px 0',
                          'backgroundColor': '#fff', 'cursor': 'pointer'}, multiple=False),

        # Zone Configuration Aléatoire
        html.Div([
            html.Label("Nombre de processus :", style={'fontWeight': 'bold', 'marginRight': '10px'}),
            dcc.Input(id='num-procs', type='number', value=6, min=2, max=20, step=1,
                      style={'width': '60px', 'marginRight': '10px'}),
            html.Button("🎲 Générer", id='btn-generate', className='button-primary')
        ], style={'textAlign': 'center', 'margin': '15px 0', 'padding': '10px', 'backgroundColor': '#f9f9f9',
                  'borderRadius': '5px'}),

        html.Div(id='stats-display',
                 style={'textAlign': 'center', 'fontSize': '1.5em', 'fontWeight': 'bold', 'margin': '10px'}),

        html.Div([
            dcc.Checklist(id='rules-checklist', options=[{'label': ' Priorités', 'value': 'PRIO'},
                                                         {'label': ' Non-Préemption', 'value': 'PREEMPT_OFF'},
                                                         {'label': ' Round Robin', 'value': 'RR'}], value=[],
                          labelStyle={'display': 'inline-block', 'marginRight': '15px'}),
        ], style={'textAlign': 'center', 'marginBottom': '20px'}),

        html.Div([
            html.Button("🔄 Rejouer (Reset)", id='btn-reset', className='button', style={'marginRight': '10px'}),
            html.Button("⏯️ IA Auto", id='btn-auto', className='button'),
            html.Button("▶️ Passer Tick", id='btn-step', className='button', style={'marginLeft': '10px'})
        ], style={'textAlign': 'center', 'marginBottom': '20px'}),

        html.H2(id='time-display', style={'textAlign': 'center', 'color': '#0074D9'}),

        html.Div(id='procs-container',
                 style={'display': 'flex', 'gap': '10px', 'justifyContent': 'center', 'flexWrap': 'wrap',
                        'marginBottom': '20px'}),

        dcc.Graph(id='gantt-chart', config={'displayModeBar': False}),

        html.H6("Logs :"),
        html.Div(id='log-console',
                 style={'backgroundColor': '#222', 'color': '#0f0', 'padding': '10px', 'height': '150px',
                        'overflowY': 'scroll', 'fontFamily': 'monospace'})
    ], style={'maxWidth': '1200px', 'margin': '0 auto'})
])


# --- CALLBACKS ---

@app.callback(
    Output('game-store', 'data'), Output('auto-timer', 'disabled'), Output('btn-auto', 'children'),
    Input('btn-generate', 'n_clicks'), Input('btn-reset', 'n_clicks'), Input('upload-data', 'contents'),
    Input({'type': 'proc-card', 'index': ALL}, 'n_clicks'), Input('auto-timer', 'n_intervals'),
    Input('btn-auto', 'n_clicks'), Input('btn-step', 'n_clicks'),
    State('game-store', 'data'), State('rules-checklist', 'value'), State('auto-timer', 'disabled'),
    State('num-procs', 'value')
)
def game_loop(gen_click, reset_click, upload_content, card_clicks, timer, auto_click, step_click, data, rules,
              is_timer_disabled, num_procs):
    trigger = ctx.triggered_id

    # 1. Génération Nouvelle Partie Aléatoire
    if trigger == 'btn-generate':
        return generate_initial_state(count=num_procs), True, "⏯️ IA Auto"

    # 2. Upload Fichier
    if trigger == 'upload-data' and upload_content:
        procs = parse_uploaded_file(upload_content)
        if procs: return generate_initial_state(processes=procs), True, "⏯️ IA Auto"

    # 3. Reset (Rejouer la même)
    if trigger == 'btn-reset':
        import copy
        initial = copy.deepcopy(data.get("initial_setup"))
        return generate_initial_state(processes=initial), True, "⏯️ IA Auto"

    # 4. Auto Mode
    if trigger == 'btn-auto':
        return data, not is_timer_disabled, "⏸️ Stop" if is_timer_disabled else "⏯️ IA Auto"

    # 5. Game Loop (Tick)
    is_tick = trigger == 'auto-timer' or trigger == 'btn-step' or (
                isinstance(trigger, dict) and trigger.get('type') == 'proc-card')

    if is_tick:
        if data["game_over"]: return data, True, "🏁 Terminé"

        mode = "AUTO" if trigger == 'auto-timer' else "MANUAL"
        logic_rules = []
        if rules and 'PRIO' in rules: logic_rules.append('PRIO')
        if rules and 'RR' in rules: logic_rules.append('RR')
        if not (rules and 'PREEMPT_OFF' in rules): logic_rules.append('PREEMPT')

        selected_pid = trigger['index'] if isinstance(trigger, dict) else None

        new_data = process_step(data, selected_pid, mode, logic_rules)
        return new_data, False if mode == "AUTO" else True, dash.no_update

    return data, True, "⏯️ IA Auto"


@app.callback(
    Output('time-display', 'children'), Output('stats-display', 'children'),
    Output('procs-container', 'children'), Output('gantt-chart', 'figure'), Output('log-console', 'children'),
    Input('game-store', 'data'), State('rules-checklist', 'value')
)
def update_view(data, rules):
    show_prio = rules and 'PRIO' in rules
    cards = []
    state_colors = {"FUTURE": "#BDC3C7", "READY": "#F1C40F", "RUNNING": "#2ECC71", "WAITING": "#3498DB",
                    "TERMINATED": "#E74C3C"}

    for p in data["processes"]:
        bc = state_colors.get(p["state"], "#333")
        border = f"4px solid {bc}" if p["state"] in ["READY", "RUNNING"] else f"1px solid {bc}"
        prio = html.Span(f"★{p['priority']}",
                         style={'float': 'right', 'color': '#E67E22', 'fontWeight': 'bold'}) if show_prio else ""

        io_info = f"E/S: {p['io_duration_fixed']}s" if p.get('io_duration_fixed') else (
            f"E/S: {', '.join(map(str, p['io_plan']))}" if p['io_plan'] else "Pas d'E/S")
        expl = html.Div("💥", className="explosion") if p.get('just_finished') else None

        card = html.Div([
            expl,
            html.Div([html.Span(p['pid'], style={'fontWeight': 'bold'}), prio], style={'marginBottom': '5px'}),
            html.Div(p['state'],
                     style={'backgroundColor': bc, 'color': 'white', 'borderRadius': '3px', 'fontSize': '0.8em'}),
            html.Div(f"Reste: {p['remaining_time']}", style={'fontWeight': 'bold', 'marginTop': '5px'}),
            html.Div(io_info, style={'fontSize': '0.7em', 'color': '#666'}),
            html.Div(f"Attente: {p['wait_time_remaining']}s" if p['state'] == "WAITING" else "",
                     style={'color': '#3498DB', 'fontSize': '0.8em'})
        ], id={'type': 'proc-card', 'index': p['pid']}, className='no-select',
            style={'border': border, 'borderRadius': '8px', 'padding': '10px', 'width': '120px', 'textAlign': 'center',
                   'backgroundColor': 'white', 'cursor': 'pointer', 'position': 'relative', 'overflow': 'hidden'})
        cards.append(card)

    if data["history"]:
        df = pd.DataFrame(data["history"])
        df["Delta"] = df["Fin"] - df["Début"]
        fig = px.bar(df, x="Delta", y="Processus", base="Début", color="Processus",
                     pattern_shape="Type", pattern_shape_map={"CPU": "", "IO": "/", "IDLE": "."},
                     orientation='h', range_x=[0, max(20, data["current_time"] + 2)],
                     title="Diagramme de Gantt (Plein=CPU, Rayé=E/S)")
        fig.update_layout(height=300, margin=dict(l=20, r=20, t=30, b=20), plot_bgcolor='rgba(0,0,0,0)')
        fig.update_traces(marker_line_color='black', marker_line_width=0.5)
    else:
        fig = px.bar(title="En attente...")

    logs = [html.Div(l, style={'color': '#FF4136' if '⛔' in l else '#0f0', 'borderBottom': '1px solid #333'}) for l in
            reversed(data["log"])]
    stats = f"{'❤️' * data.get('lives', 3)} | Score: {data.get('score', 0)}"

    return f"⏱️ T={data['current_time']}", stats, cards, fig, logs


if __name__ == '__main__':
    app.run(debug=True)