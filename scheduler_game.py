import dash
from dash import dcc, html, Input, Output, State, ctx
import plotly.express as px
import pandas as pd
import random
import json


# --- MOTEUR LOGIQUE (Adapté pour être "Stateless") ---

def generate_initial_state():
    """Génère un état de jeu initial aléatoire."""
    processes = []
    for i in range(5):
        processes.append({
            "pid": f"P{i + 1}",
            "arrival_time": random.randint(0, 4),
            "burst_time": random.randint(2, 6),
            "remaining_time": 0,  # Sera défini égal au burst
            "state": "FUTURE",
            "io_time": 0
        })
        processes[-1]["remaining_time"] = processes[-1]["burst_time"]

    return {
        "processes": processes,
        "current_time": 0,
        "history": [],  # Pour le Gantt: {pid, start, duration}
        "game_over": False,
        "log": ["Jeu initialisé. En attente..."]
    }


def process_step(game_state, selected_pid=None, mode="MANUAL"):
    """Exécute un 'tick' d'horloge."""
    processes = game_state["processes"]
    current_time = game_state["current_time"]
    history = game_state["history"]
    log = game_state["log"]

    # 1. Mise à jour des arrivées
    ready_procs = []
    for p in processes:
        if p["state"] == "FUTURE" and p["arrival_time"] <= current_time:
            p["state"] = "READY"
            log.append(f"T={current_time}: {p['pid']} est arrivé.")
        if p["state"] == "READY" or p["state"] == "RUNNING":
            # Si c'était RUNNING au tour d'avant, il redevient READY pour la nouvelle élection
            # sauf si terminé
            p["state"] = "READY"
            ready_procs.append(p)

    if not ready_procs and all(p["state"] == "TERMINATED" for p in processes):
        game_state["game_over"] = True
        log.append("🏁 Tous les processus sont terminés !")
        return game_state

    # 2. Choix du processus
    chosen_proc = None

    if mode == "AUTO":
        # FCFS: On prend le plus ancien arrivé
        if ready_procs:
            ready_procs.sort(key=lambda x: x["arrival_time"])
            chosen_proc = ready_procs[0]
    else:  # MANUAL
        if selected_pid:
            for p in ready_procs:
                if p["pid"] == selected_pid:
                    chosen_proc = p
                    break

    # 3. Exécution
    if chosen_proc:
        chosen_proc["state"] = "RUNNING"
        chosen_proc["remaining_time"] -= 1

        # Ajout à l'historique pour le graphique
        history.append({
            "Processus": chosen_proc["pid"],
            "Début": current_time,
            "Fin": current_time + 1,
            "Type": "CPU"
        })

        log.append(f"T={current_time}: Exécution de {chosen_proc['pid']} (Reste: {chosen_proc['remaining_time']})")

        if chosen_proc["remaining_time"] <= 0:
            chosen_proc["state"] = "TERMINATED"
            log.append(f"🎉 {chosen_proc['pid']} a terminé !")

    else:
        log.append(f"T={current_time}: CPU Inactif (Idle)")
        history.append({
            "Processus": "IDLE",
            "Début": current_time,
            "Fin": current_time + 1,
            "Type": "IDLE"
        })

    game_state["current_time"] += 1
    # On garde seulement les 5 derniers logs
    game_state["log"] = log[-5:]

    return game_state


# --- INTERFACE DASH ---

app = dash.Dash(__name__, external_stylesheets=['https://codepen.io/chriddyp/pen/bWLwgP.css'])
app.title = "Jeu de l'Ordonnanceur"

app.layout = html.Div([
    html.H1("🎮 Simulateur d'Ordonnancement (OS)", style={'textAlign': 'center'}),

    # Stockage de l'état du jeu (invisible)
    dcc.Store(id='game-store', data=generate_initial_state()),
    dcc.Interval(id='auto-timer', interval=1000, disabled=True),  # Timer pour mode auto

    html.Div([
        html.Div([
            html.H3("Contrôles"),
            html.Button("🔄 Nouvelle Partie", id='btn-reset', n_clicks=0, className='button-primary'),
            html.Hr(),
            html.H5("Mode Manuel"),
            dcc.Dropdown(id='proc-dropdown', placeholder="Choisir un processus..."),
            html.Button("▶️ Exécuter 1 Tick", id='btn-step', n_clicks=0),
            html.Hr(),
            html.H5("Mode Auto (FCFS)"),
            html.Button("⏯️ Start/Stop Auto", id='btn-auto', n_clicks=0),
        ], className='three columns', style={'backgroundColor': '#f9f9f9', 'padding': '20px', 'borderRadius': '10px'}),

        html.Div([
            html.H3(id='time-display', style={'color': '#0074D9'}),

            # Affichage des processus (Cartes)
            html.Div(id='procs-container',
                     style={'display': 'flex', 'gap': '10px', 'flexWrap': 'wrap', 'marginBottom': '20px'}),

            # Diagramme de Gantt
            dcc.Graph(id='gantt-chart'),

            # Logs
            html.Div(id='log-console',
                     style={'backgroundColor': '#333', 'color': '#0f0', 'padding': '10px', 'fontFamily': 'monospace'})
        ], className='nine columns')
    ], className='row')
], style={'maxWidth': '1200px', 'margin': '0 auto'})


# --- CALLBACKS ---

@app.callback(
    Output('game-store', 'data'),
    Output('auto-timer', 'disabled'),
    Input('btn-reset', 'n_clicks'),
    Input('btn-step', 'n_clicks'),
    Input('auto-timer', 'n_intervals'),
    Input('btn-auto', 'n_clicks'),
    State('game-store', 'data'),
    State('proc-dropdown', 'value'),
    State('auto-timer', 'disabled')  # Pour savoir si on toggle
)
def update_game(reset_click, step_click, timer_tick, auto_click, data, selected_pid, is_timer_disabled):
    trigger = ctx.triggered_id

    # 1. Reset
    if trigger == 'btn-reset':
        return generate_initial_state(), True

    # 2. Toggle Auto Mode
    if trigger == 'btn-auto':
        return data, not is_timer_disabled

    # 3. Step Logic (Manuel ou Timer)
    if trigger == 'btn-step' or trigger == 'auto-timer':
        if data["game_over"]:
            return data, True  # Stop timer if game over

        mode = "AUTO" if trigger == 'auto-timer' else "MANUAL"
        new_state = process_step(data, selected_pid, mode)
        return new_state, False if mode == "AUTO" else True

    return data, True


@app.callback(
    Output('time-display', 'children'),
    Output('procs-container', 'children'),
    Output('gantt-chart', 'figure'),
    Output('proc-dropdown', 'options'),
    Output('log-console', 'children'),
    Input('game-store', 'data')
)
def update_ui(data):
    # 1. Update Time
    time_text = f"⏱️ Temps Actuel : {data['current_time']}"

    # 2. Update Process Cards
    cards = []
    ready_options = []

    colors = {"FUTURE": "#999", "READY": "#FFDC00", "RUNNING": "#2ECC40", "TERMINATED": "#FF4136"}

    for p in data["processes"]:
        # Création de la carte visuelle
        card_style = {
            'border': f'2px solid {colors.get(p["state"], "#333")}',
            'padding': '10px',
            'borderRadius': '5px',
            'width': '120px',
            'textAlign': 'center',
            'backgroundColor': '#fff'
        }
        card = html.Div([
            html.H5(p['pid'], style={'margin': '0'}),
            html.Div(f"{p['state']}", style={'fontWeight': 'bold', 'color': colors.get(p["state"])}),
            html.Div(f"Burst: {p['burst_time']}"),
            html.Div(f"Reste: {p['remaining_time']}")
        ], style=card_style)
        cards.append(card)

        # Remplissage du menu déroulant seulement avec les READY
        if p['state'] == 'READY':
            ready_options.append({'label': f"{p['pid']} (Reste {p['remaining_time']})", 'value': p['pid']})

    # 3. Update Gantt Chart
    if data["history"]:
        df = pd.DataFrame(data["history"])
        # Astuce pour Gantt: Bar chart horizontal
        fig = px.bar(df, x="Fin", y="Processus", color="Processus", orientation='h',
                     base="Début", range_x=[0, max(10, data["current_time"] + 2)],
                     title="Diagramme de Gantt (Historique CPU)")
        fig.update_layout(xaxis_title="Temps", yaxis_title="PID")
    else:
        fig = px.bar(title="En attente de démarrage...")

    # 4. Logs
    logs = [html.Div(line) for line in data["log"]]

    return time_text, cards, fig, ready_options, logs


if __name__ == '__main__':
    app.run_server(debug=True)