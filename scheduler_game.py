import dash
from dash import dcc, html, Input, Output, State, ctx
import plotly.express as px
import pandas as pd
import random

# --- CONFIGURATION ---
QUANTUM = 3  # Temps max par tour si Round Robin activé
IO_PROBABILITY = 0.15
MAX_IO_DURATION = 3


# --- MOTEUR LOGIQUE ---

def generate_initial_state():
    processes = []
    for i in range(6):
        processes.append({
            "pid": f"P{i + 1}",
            "arrival_time": random.randint(0, 5),
            "burst_time": random.randint(4, 10),
            "remaining_time": 0,
            "priority": random.randint(1, 10),
            "state": "FUTURE",
            "wait_time_remaining": 0,
            "consecutive_cpu": 0
        })
        processes[-1]["remaining_time"] = processes[-1]["burst_time"]

    return {
        "processes": processes,
        "current_time": 0,
        "history": [],
        "game_over": False,
        "rr_queue": [],
        "log": ["⚙️ Configurez les règles et jouez !"]
    }


def process_step(game_state, selected_pid=None, mode="MANUAL", rules=[]):
    processes = game_state["processes"]
    current_time = game_state["current_time"]
    history = game_state["history"]
    log = game_state["log"]
    rr_queue = game_state["rr_queue"]

    # --- 0. DECHIFFRAGE DES REGLES ---
    use_priority = 'PRIO' in rules
    allow_preemption = 'PREEMPT' in rules
    use_rr = 'RR' in rules

    # --- 1. GESTION DES ETATS (Mise à jour préliminaire) ---
    # On ne fait avancer le temps que SI l'action est validée.
    # Mais on doit d'abord savoir qui est Ready pour valider le choix.

    # Copie temporaire pour analyse (on ne modifie pas encore l'état réel)
    temp_ready = []
    running_proc = None

    for p in processes:
        # Check running actuel (avant ce tick)
        if p["state"] == "RUNNING":
            running_proc = p

        # Simulation arrivée
        is_ready = p["state"] == "READY"
        if p["state"] == "FUTURE" and p["arrival_time"] <= current_time:
            is_ready = True
        # Simulation retour E/S (Approximation pour la validation)
        if p["state"] == "WAITING" and p["wait_time_remaining"] <= 1:
            is_ready = True

        if is_ready or p["state"] == "RUNNING":
            temp_ready.append(p)

    unfinished = [p for p in processes if p["state"] != "TERMINATED"]
    if not unfinished:
        game_state["game_over"] = True
        log.append("🏆 TOUS LES PROCESSUS SONT TERMINÉS !")
        return game_state

    # --- 2. LOGIQUE DE VALIDATION (MODE MANUEL) ---
    chosen_proc = None
    error_msg = None

    if mode == "MANUAL":
        # Le joueur veut exécuter selected_pid. A-t-il le droit ?

        # Cas 1 : CPU IDLE (Aucun choix)
        if not selected_pid:
            # Si des processus sont prêts, il n'a pas le droit de rien faire (sauf si on considère l'IDLE comme valide, ici on force le travail)
            if any(p["state"] in ["READY", "RUNNING"] for p in processes if p["arrival_time"] <= current_time):
                # On autorise l'IDLE seulement si on veut, mais ici on va juste dire "Rien sélectionné"
                pass
        else:
            candidate = next((p for p in processes if p["pid"] == selected_pid), None)

            # Vérif 1: Le processus est-il prêt ?
            if not candidate or candidate not in temp_ready:
                error_msg = f"⛔ {selected_pid} n'est pas prêt !"

            # Vérif 2: NON-PRÉEMPTION
            elif not allow_preemption and running_proc and running_proc["state"] != "TERMINATED" and running_proc[
                "state"] != "WAITING" and candidate["pid"] != running_proc["pid"]:
                error_msg = f"⛔ NON-PRÉEMPTION : Vous devez finir {running_proc['pid']} !"

            # Vérif 3: PRIORITÉ
            elif use_priority:
                # Trouver la priorité max parmi les prêts
                max_prio = max([p["priority"] for p in temp_ready]) if temp_ready else 0
                if candidate["priority"] < max_prio:
                    # On cherche qui a la max prio pour l'afficher
                    better = next(p for p in temp_ready if p["priority"] == max_prio)
                    error_msg = f"⛔ PRIORITÉ : {better['pid']} est prioritaire ({better['priority']}) !"

            if not error_msg:
                chosen_proc = candidate

    else:  # MODE AUTO (L'IA respecte toujours les règles)
        # (Même logique que précédemment pour l'IA)
        real_ready = []
        # On doit refaire la passe propre des états pour l'IA
        # ... Simplification : l'IA joue après la mise à jour des états ci-dessous
        pass

        # SI ERREUR EN MANUEL : ON STOPPE TOUT
    if error_msg:
        log.append(error_msg)
        game_state["log"] = log[-6:]
        return game_state  # On retourne l'état SANS avancer le temps

    # --- 3. MISE A JOUR REELLE DU TEMPS ET DES ETATS ---
    # Si on arrive ici, l'action est validée (ou c'est l'IA).

    # Mise à jour des arrivées et E/S réelles
    ready_procs_real = []

    for p in processes:
        # Arrivées
        if p["state"] == "FUTURE" and p["arrival_time"] <= current_time:
            p["state"] = "READY"
            log.append(f"✨ T={current_time}: {p['pid']} est arrivé.")
            if p["pid"] not in rr_queue: rr_queue.append(p["pid"])

        # E/S
        if p["state"] == "WAITING":
            p["wait_time_remaining"] -= 1
            if p["wait_time_remaining"] <= 0:
                p["state"] = "READY"
                log.append(f"🔙 T={current_time}: {p['pid']} revient d'E/S.")
                if p["pid"] not in rr_queue: rr_queue.append(p["pid"])
            else:
                history.append({"Processus": p["pid"], "Début": current_time, "Fin": current_time + 1, "Type": "IO"})

        # Reset RUNNING -> READY
        if p["state"] == "RUNNING":
            p["state"] = "READY"

        if p["state"] == "READY":
            ready_procs_real.append(p)

    # SELECTION IA (Si pas manuel)
    if mode == "AUTO":
        if ready_procs_real:
            # 1. Non-Préemption (Force Running)
            # Retrouver l'ancien running (il est maintenant READY dans ready_procs_real)
            # Astuce: on regarde si chosen_proc a déjà été défini par la logique de continuité ? Non.
            # Il faut regarder consecutive_cpu > 0 et !RR pour deviner la continuité si on veut être strict,
            # Mais simplifions : L'IA recalcule le meilleur candidat à chaque fois.

            # Tri de base
            ready_procs_real.sort(key=lambda x: x["arrival_time"])

            if use_priority:
                ready_procs_real.sort(key=lambda x: x["priority"], reverse=True)

            if use_rr:
                valid_pids = [p["pid"] for p in ready_procs_real]
                rr_queue = [pid for pid in rr_queue if pid in valid_pids]
                if rr_queue:
                    next_pid = rr_queue[0]
                    chosen_proc = next((p for p in ready_procs_real if p["pid"] == next_pid), ready_procs_real[0])
                else:
                    chosen_proc = ready_procs_real[0]
            else:
                chosen_proc = ready_procs_real[0]

            # Override Non-Preemption IA : Si un process tournait et n'a pas fini, et Preempt OFF
            if not allow_preemption and running_proc and running_proc in ready_procs_real:
                chosen_proc = running_proc

    # --- 4. EXECUTION ---
    if chosen_proc:
        chosen_proc["state"] = "RUNNING"
        chosen_proc["remaining_time"] -= 1
        chosen_proc["consecutive_cpu"] += 1

        # Logique E/S
        if chosen_proc["remaining_time"] > 0 and random.random() < IO_PROBABILITY:
            chosen_proc["state"] = "WAITING"
            chosen_proc["wait_time_remaining"] = random.randint(1, MAX_IO_DURATION)
            chosen_proc["consecutive_cpu"] = 0
            if use_rr and chosen_proc["pid"] in rr_queue: rr_queue.remove(chosen_proc["pid"])
            log.append(f"⚠️ {chosen_proc['pid']} part en E/S.")

        # Logique Round Robin (Quantum)
        elif use_rr and chosen_proc["consecutive_cpu"] >= QUANTUM:
            log.append(f"🔄 {chosen_proc['pid']} Quantum écoulé (Force Switch).")
            chosen_proc["consecutive_cpu"] = 0
            # Rotation File
            if chosen_proc["pid"] in rr_queue:
                rr_queue.pop(0)
                rr_queue.append(chosen_proc["pid"])
            # NOTE : En mode manuel, l'utilisateur verra que le process s'arrête (devient READY).
            # S'il essaie de le reprendre tout de suite, c'est techniquement possible sauf si on implémente une file stricte.
            # Pour l'instant, on reset juste le CPU, ce qui indique visuellement la fin du tour.

        # Fin
        elif chosen_proc["remaining_time"] <= 0:
            chosen_proc["state"] = "TERMINATED"
            if use_rr and chosen_proc["pid"] in rr_queue: rr_queue.remove(chosen_proc["pid"])
            log.append(f"🎉 {chosen_proc['pid']} a terminé !")

        history.append({"Processus": chosen_proc["pid"], "Début": current_time, "Fin": current_time + 1, "Type": "CPU"})
        if chosen_proc["state"] == "RUNNING":
            log.append(f"⚡ T={current_time}: {chosen_proc['pid']} exécute.")

    else:
        # IDLE
        log.append("💤 CPU Inactif")
        history.append({"Processus": "IDLE", "Début": current_time, "Fin": current_time + 1, "Type": "IDLE"})

    game_state["current_time"] += 1
    game_state["rr_queue"] = rr_queue
    game_state["log"] = log[-6:]

    return game_state


# --- INTERFACE DASH ---

app = dash.Dash(__name__, external_stylesheets=['https://codepen.io/chriddyp/pen/bWLwgP.css'])
app.title = "TP OS - Ordonnanceur"

# Styles
modal_style = {'position': 'fixed', 'zIndex': '1000', 'left': '0', 'top': '0', 'width': '100%', 'height': '100%',
               'overflow': 'auto', 'backgroundColor': 'rgba(0,0,0,0.5)', 'display': 'none'}
modal_content_style = {'backgroundColor': '#fefefe', 'margin': '15% auto', 'padding': '20px',
                       'border': '1px solid #888', 'width': '50%', 'borderRadius': '10px'}

app.layout = html.Div([
    # MODALE
    html.Div(id='rules-modal', style=modal_style, children=[
        html.Div(style=modal_content_style, children=[
            html.H3("Règles du Jeu"),
            html.P("Les règles cochées s'appliquent à l'IA ET au joueur (Mode Manuel) !"),
            html.Ul([
                html.Li("★ Priorité : Impossible de choisir un petit process si un gros attend."),
                html.Li("🚫 Non-Préemption : Impossible de changer de process tant qu'il n'a pas fini (ou E/S)."),
                html.Li("🔄 Round Robin : Au bout de 3 ticks, le process est éjecté."),
            ]),
            html.Button("OK", id='btn-close-modal', className='button')
        ])
    ]),

    # HEADER
    html.Div([
        html.H1("⚡ Jeu de l'Ordonnanceur (Strict Mode)", style={'display': 'inline-block'}),
        html.Button("❓ Règles", id='btn-open-modal', className='button', style={'float': 'right', 'marginTop': '20px'})
    ], style={'borderBottom': '1px solid #ddd', 'marginBottom': '20px'}),

    dcc.Store(id='game-store', data=generate_initial_state()),
    dcc.Interval(id='auto-timer', interval=800, disabled=True),

    # MAIN
    html.Div([
        # GAUCHE
        html.Div([
            html.H5("⚙️ Règles Actives"),
            dcc.Checklist(
                id='rules-checklist',
                options=[
                    {'label': ' Respecter Priorités', 'value': 'PRIO'},
                    {'label': ' Non-Préemption (Strict)', 'value': 'PREEMPT_OFF'},
                    # Changé pour clarifier: si coché, pas de préemption
                    {'label': ' Round Robin (Quantum)', 'value': 'RR'}
                ],
                value=[],
                labelStyle={'display': 'block', 'cursor': 'pointer'}
            ),
            html.Div("Note: Cochez 'Non-Préemption' pour interdire le changement de tâche.",
                     style={'fontSize': '0.8em', 'color': '#666', 'marginBottom': '10px'}),
            html.Hr(),

            html.H5("🕹️ Contrôles"),
            html.Button("🔄 Reset", id='btn-reset', className='button', style={'width': '100%', 'marginBottom': '5px'}),

            html.Label("Joueur (Manuel) :"),
            dcc.Dropdown(id='proc-dropdown', placeholder="Votre choix..."),
            html.Button("▶️ Valider Choix (+1 Tick)", id='btn-step', className='button-primary',
                        style={'width': '100%', 'marginTop': '5px'}),

            html.Hr(),
            html.Label("IA (Auto) :"),
            html.Button("⏯️ Start / Stop Auto", id='btn-auto', className='button', style={'width': '100%'}),

            html.Hr(),
            html.H2(id='time-display', style={'textAlign': 'center', 'color': '#0074D9'})

        ], className='three columns', style={'backgroundColor': '#f1f1f1', 'padding': '20px', 'borderRadius': '8px'}),

        # DROITE
        html.Div([
            html.Div(id='procs-container',
                     style={'display': 'flex', 'gap': '10px', 'flexWrap': 'wrap', 'marginBottom': '20px',
                            'justifyContent': 'center'}),
            dcc.Graph(id='gantt-chart', config={'displayModeBar': False}),
            html.H6("Journal système (Logs) :"),
            html.Div(id='log-console', style={'backgroundColor': '#1e1e1e', 'color': '#00ff00', 'padding': '10px',
                                              'fontFamily': 'Consolas, monospace', 'height': '150px',
                                              'overflowY': 'scroll', 'borderRadius': '5px'})
        ], className='nine columns')
    ], className='row')

], style={'maxWidth': '1400px', 'margin': '0 auto', 'padding': '20px'})


# CALLBACKS
@app.callback(Output('rules-modal', 'style'), Input('btn-open-modal', 'n_clicks'), Input('btn-close-modal', 'n_clicks'),
              State('rules-modal', 'style'))
def toggle_modal(n1, n2, s):
    return {'display': 'block'} if ctx.triggered_id == 'btn-open-modal' else {'display': 'none'}


@app.callback(
    Output('game-store', 'data'),
    Output('auto-timer', 'disabled'),
    Output('btn-auto', 'children'),
    Input('btn-reset', 'n_clicks'),
    Input('btn-step', 'n_clicks'),
    Input('auto-timer', 'n_intervals'),
    Input('btn-auto', 'n_clicks'),
    State('game-store', 'data'),
    State('proc-dropdown', 'value'),
    State('rules-checklist', 'value'),
    State('auto-timer', 'disabled')
)
def update_game_logic(reset, step, timer, auto_click, data, selected_pid, rules, is_timer_disabled):
    trigger = ctx.triggered_id
    if trigger == 'btn-reset': return generate_initial_state(), True, "⏯️ Start Auto"

    if trigger == 'btn-auto':
        return data, not is_timer_disabled, "⏸️ Stop" if is_timer_disabled else "⏯️ Start Auto"

    if trigger == 'btn-step' or trigger == 'auto-timer':
        if data["game_over"]: return data, True, "🏁 Terminé"

        mode = "AUTO" if trigger == 'auto-timer' else "MANUAL"

        # Adaptation des règles pour la fonction logique
        # Dans l'UI j'ai mis "Non-Préemption" (PREEMPT_OFF) pour que ce soit plus clair à cocher
        # Donc si PREEMPT_OFF est coché, allow_preemption = False
        logic_rules = []
        if rules and 'PRIO' in rules: logic_rules.append('PRIO')
        if rules and 'RR' in rules: logic_rules.append('RR')

        # La logique process_step attend 'PREEMPT' pour AUTORISER.
        # Si 'PREEMPT_OFF' est coché, on n'envoie PAS 'PREEMPT'.
        # Si 'PREEMPT_OFF' n'est pas coché, on envoie 'PREEMPT'.
        if not (rules and 'PREEMPT_OFF' in rules):
            logic_rules.append('PREEMPT')

        new_data = process_step(data, selected_pid, mode, logic_rules)
        return new_data, False if mode == "AUTO" else True, dash.no_update

    return data, True, "⏯️ Start Auto"


@app.callback(
    Output('time-display', 'children'),
    Output('procs-container', 'children'),
    Output('gantt-chart', 'figure'),
    Output('proc-dropdown', 'options'),
    Output('log-console', 'children'),
    Input('game-store', 'data'),
    State('rules-checklist', 'value')
)
def update_ui_components(data, rules):
    show_prio = rules and 'PRIO' in rules

    time_txt = f"⏱️ T={data['current_time']}"
    cards, ready_opts = [], []
    state_colors = {"FUTURE": "#BDC3C7", "READY": "#F1C40F", "RUNNING": "#2ECC71", "WAITING": "#3498DB",
                    "TERMINATED": "#E74C3C"}

    for p in data["processes"]:
        b_color = state_colors.get(p["state"], "#333")
        border = f"3px solid {b_color}" if p["state"] == "RUNNING" else "1px solid #ccc"
        prio_html = html.Span(f"★{p['priority']}", style={'float': 'right', 'color': '#E67E22',
                                                          'fontWeight': 'bold'}) if show_prio else html.Span("")

        card = html.Div([
            html.Div([html.Span(p['pid'], style={'fontWeight': 'bold'}), prio_html], style={'marginBottom': '5px'}),
            html.Div(p['state'],
                     style={'color': 'white', 'backgroundColor': b_color, 'borderRadius': '3px', 'padding': '2px',
                            'fontSize': '0.8em'}),
            html.Div(f"Burst: {p['burst_time']}", style={'fontSize': '0.9em'}),
            html.Div(f"Reste: {p['remaining_time']}", style={'fontWeight': 'bold'}),
            html.Div(f"E/S: {p['wait_time_remaining']}s" if p['state'] == "WAITING" else "",
                     style={'color': '#3498DB', 'fontSize': '0.8em'})
        ], style={'border': border, 'borderRadius': '8px', 'padding': '10px', 'width': '100px', 'textAlign': 'center',
                  'backgroundColor': 'white', 'boxShadow': "0 4px 8px 0 rgba(0,0,0,0.2)"})
        cards.append(card)
        if p['state'] == 'READY':
            label = f"{p['pid']} (Prio {p['priority']})" if show_prio else p['pid']
            ready_opts.append({'label': label, 'value': p['pid']})

    if data["history"]:
        df = pd.DataFrame(data["history"])
        # Couleur dynamique selon PID
        fig = px.bar(df, x="Fin", y="Processus", color="Processus", orientation='h', base="Début",
                     range_x=[0, max(15, data["current_time"] + 2)], title="Diagramme de Gantt")
        fig.update_layout(height=300, margin=dict(l=20, r=20, t=30, b=20), plot_bgcolor='rgba(0,0,0,0)')
    else:
        fig = px.bar(title="En attente...")

    logs = []
    for l in reversed(data["log"]):
        style = {'borderBottom': '1px solid #333'}
        if "⛔" in l: style['color'] = '#FF4136'  # Rouge pour erreurs
        logs.append(html.Div(l, style=style))

    return time_txt, cards, fig, ready_opts, logs


if __name__ == '__main__':
    app.run(debug=True)