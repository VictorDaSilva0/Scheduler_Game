import time
import random
import json
import copy
import os


# --- Classes & Structures ---

class Process:
    def __init__(self, pid, arrival_time, burst_time, io_time=0):
        self.pid = pid
        self.arrival_time = arrival_time
        self.burst_time = burst_time  # Temps CPU total nécessaire
        self.io_time = io_time  # Temps E/S (optionnel)

        # État dynamique
        self.remaining_time = burst_time
        self.state = "FUTURE"  # FUTURE, READY, RUNNING, WAITING, TERMINATED
        self.wait_time = 0
        self.last_active_time = -1

    def __repr__(self):
        return f"[P{self.pid} | Arr:{self.arrival_time} | Burst:{self.remaining_time}/{self.burst_time} | State:{self.state}]"

    def to_dict(self):
        return {
            "pid": self.pid,
            "arrival_time": self.arrival_time,
            "burst_time": self.burst_time,
            "io_time": self.io_time
        }


class SchedulerGame:
    def __init__(self):
        self.initial_processes = []
        self.processes = []
        self.current_time = 0
        self.history = []  # Pour le replay (snapshots)
        self.quantum = 2  # Pour le Round Robin

    def load_from_file(self, filepath):
        """Charge la configuration depuis un fichier JSON."""
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
                self.initial_processes = [Process(**p) for p in data]
            print(f"✅ Chargé {len(self.initial_processes)} processus depuis {filepath}")
        except FileNotFoundError:
            print("❌ Fichier non trouvé.")

    def generate_random(self, count=5):
        """Génère une partie aléatoire."""
        self.initial_processes = []
        for i in range(count):
            p = Process(
                pid=i + 1,
                arrival_time=random.randint(0, 5),
                burst_time=random.randint(2, 8),
                io_time=random.choice([0, 0, 2])  # 1 chance sur 3 d'avoir des E/S
            )
            self.initial_processes.append(p)
        print(f"🎲 Généré {count} processus aléatoires.")

    def reset_game(self):
        """Remet le jeu à zéro pour rejouer."""
        self.processes = copy.deepcopy(self.initial_processes)
        self.current_time = 0
        self.history = []
        # Reset states
        for p in self.processes:
            p.state = "FUTURE" if p.arrival_time > 0 else "READY"

    def get_ready_processes(self):
        return [p for p in self.processes if p.state == "READY"]

    def update_arrivals(self):
        """Vérifie les nouveaux arrivants."""
        for p in self.processes:
            if p.state == "FUTURE" and p.arrival_time <= self.current_time:
                p.state = "READY"
                print(f"📢 Processus P{p.pid} est arrivé (READY) !")

    def check_io(self):
        """Simule la fin des E/S."""
        # Note simple: ici on assume que si un process est WAITING, il revient en READY au prochain tick
        # Une implémentation complexe gérerait un compteur E/S distinct.
        for p in self.processes:
            if p.state == "WAITING":
                # Simulation simple: 1 tick d'E/S ramène en READY
                p.state = "READY"

    def is_game_over(self):
        return all(p.state == "TERMINATED" for p in self.processes)

    def print_status(self):
        print(f"\n--- ⏱️ TEMPS: {self.current_time} ---")
        print(f"{'PID':<5} {'State':<10} {'Reste':<8} {'Arrivée':<8}")
        print("-" * 35)
        for p in self.processes:
            print(f"{p.pid:<5} {p.state:<10} {p.remaining_time:<8} {p.arrival_time:<8}")
        print("-" * 35)

    def auto_play(self, algo="FCFS"):
        """Mode automatique pour voir comment l'IA jouerait[cite: 22]."""
        print(f"\n🤖 Lancement de la simulation automatique ({algo})...")
        self.reset_game()

        rq = []  # Queue interne pour Round Robin

        while not self.is_game_over():
            self.update_arrivals()
            ready_procs = self.get_ready_processes()

            chosen_p = None

            if not ready_procs:
                print(f"T={self.current_time}: CPU Idle")
            else:
                if algo == "FCFS":
                    # First Come First Served: tri par arrivée
                    ready_procs.sort(key=lambda x: x.arrival_time)
                    chosen_p = ready_procs[0]

                elif algo == "RR":
                    # Round Robin simplifié
                    # Ajouter les nouveaux à la queue
                    for p in ready_procs:
                        if p not in rq:
                            rq.append(p)
                    if rq:
                        chosen_p = rq.pop(0)  # Prend le premier
                        # (La logique RR complète nécessiterait de gérer le quantum ici)

                # Exécution
                if chosen_p:
                    chosen_p.remaining_time -= 1
                    if chosen_p.remaining_time == 0:
                        chosen_p.state = "TERMINATED"
                    elif algo == "RR":
                        rq.append(chosen_p)  # Remet à la fin

            self.current_time += 1
            time.sleep(0.1)  # Petit délai pour l'effet visuel

        print(f"🏁 Simulation {algo} terminée en {self.current_time} ticks.")

    def start_manual_game(self):
        """Boucle principale du jeu manuel."""
        if not self.initial_processes:
            print("⚠️ Aucun processus chargé. Génération aléatoire...")
            self.generate_random()

        self.reset_game()
        print("\n🎮 DÉBUT DU JEU DE L'ORDONNANCEUR")
        print("Votre but : Minimiser le temps total en choisissant le bon processus.")

        while not self.is_game_over():
            self.update_arrivals()
            self.check_io()
            self.print_status()

            ready = self.get_ready_processes()

            if not ready:
                print("💤 Aucun processus prêt (CPU Idle).")
                input("Pressez Entrée pour avancer le temps...")
                self.current_time += 1
                continue

            # Demande à l'utilisateur
            print("Processus prêts (PID): ", [p.pid for p in ready])
            choice = input(f"Quel PID exécuter (ou 'r' pour restart) ? > ")

            if choice.lower() == 'r':
                print("🔄 Redémarrage de la partie...")
                self.reset_game()
                continue

            try:
                pid_choice = int(choice)
                selected_p = next((p for p in ready if p.pid == pid_choice), None)

                if selected_p:
                    # Exécution
                    selected_p.state = "RUNNING"
                    print(f"⚡ Exécution de P{selected_p.pid}...")
                    selected_p.remaining_time -= 1

                    # Logique simple E/S ou Terminaison
                    if selected_p.remaining_time <= 0:
                        selected_p.state = "TERMINATED"
                        print(f"🎉 P{selected_p.pid} a terminé !")
                    elif selected_p.io_time > 0 and random.random() < 0.2:
                        # Simulation aléatoire d'une interruption E/S [cite: 22]
                        selected_p.state = "WAITING"
                        print(f"⚠️ P{selected_p.pid} part en E/S (Waiting).")
                    else:
                        selected_p.state = "READY"  # Retourne en ready (Préemption implicite)

                    self.current_time += 1
                else:
                    print("❌ PID invalide ou processus non prêt.")
            except ValueError:
                print("❌ Entrée invalide.")

        print(f"\n🏆 VICTOIRE ! Tous les processus sont terminés au temps {self.current_time}.")


# --- Main Menu ---

def main():
    game = SchedulerGame()

    while True:
        print("\n=== 🖥️ MENU ORDONNANCEUR ===")
        print("1. Générer partie aléatoire ")
        print("2. Charger fichier JSON ")
        print("3. Jouer (Manuel) ")
        print("4. Simulation IA (FCFS) ")
        print("5. Quitter")

        choix = input("Choix > ")

        if choix == "1":
            game.generate_random()
        elif choix == "2":
            path = input("Chemin du fichier (ex: game.json) : ")
            game.load_from_file(path)
        elif choix == "3":
            game.start_manual_game()
        elif choix == "4":
            game.auto_play("FCFS")
        elif choix == "5":
            break


if __name__ == "__main__":
    main()