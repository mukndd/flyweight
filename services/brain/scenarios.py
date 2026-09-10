"""Deterministic scenario library for responsive-controller evaluation."""

SCENARIO_SET_VERSION = "scenario-library-v1"
REWARD_VERSION = "combat-v2-reward-1"


def fighter(x, hp=100, y=0, vx=0, vy=0, face=1, cooldown=0, attack=0, attack_frame=0, block=False):
    return {"x": x, "y": y, "vx": vx, "vy": vy, "hp": hp, "face": face, "cooldown": cooldown,
            "attack": attack, "attackFrame": attack_frame, "block": block}


def scenario(ident, split, family, seed, difficulty, profile, player, opponent, note):
    return {"id": ident, "split": split, "family": family, "seed": seed, "difficulty": difficulty,
            "profile": profile, "player": player, "opponent": opponent, "note": note}


SCENARIOS = [
    scenario("scenario_train_0001", "train", "very_close", 610001, "easy", "standard", fighter(455), fighter(525, face=-1), "Close neutral easy."),
    scenario("scenario_train_0002", "train", "medium_distance", 610002, "easy", "standard", fighter(365), fighter(610, face=-1), "Medium spacing easy."),
    scenario("scenario_train_0003", "train", "far_distance", 610003, "easy", "mobile", fighter(245), fighter(820, face=-1), "Far mobile approach."),
    scenario("scenario_train_0004", "train", "corner_pressure", 610004, "easy", "aggressive", fighter(62), fighter(150, face=-1), "Back near left wall."),
    scenario("scenario_train_0005", "train", "health_advantage", 610005, "easy", "defensive", fighter(430, hp=100), fighter(560, hp=55, face=-1), "Must finish hurt opponent."),
    scenario("scenario_train_0006", "train", "health_disadvantage", 610006, "easy", "counter-focused", fighter(430, hp=48), fighter(560, hp=100, face=-1), "Low-health survival."),
    scenario("scenario_train_0007", "train", "early_attack", 610007, "easy", "aggressive", fighter(470), fighter(545, face=-1, attack=5), "Opponent begins light attack."),
    scenario("scenario_train_0008", "train", "passive_probe", 610008, "easy", "defensive", fighter(390), fighter(560, face=-1, block=True), "Opponent begins guarding."),
    scenario("scenario_train_0009", "train", "very_close", 610009, "medium", "standard", fighter(458), fighter(528, face=-1), "Close neutral medium."),
    scenario("scenario_train_0010", "train", "medium_distance", 610010, "medium", "aggressive", fighter(350), fighter(625, face=-1), "Medium aggressive."),
    scenario("scenario_train_0011", "train", "far_distance", 610011, "medium", "mobile", fighter(220), fighter(825, face=-1), "Far mobile medium."),
    scenario("scenario_train_0012", "train", "corner_pressure", 610012, "medium", "defensive", fighter(72), fighter(168, face=-1), "Corner defensive."),
    scenario("scenario_train_0013", "train", "counter_window", 610013, "medium", "counter-focused", fighter(445), fighter(550, face=-1, cooldown=18), "Opponent recovery window."),
    scenario("scenario_train_0014", "train", "early_attack", 610014, "medium", "aggressive", fighter(466), fighter(540, face=-1, attack=6), "Opponent starts heavy attack."),
    scenario("scenario_train_0015", "train", "health_advantage", 610015, "medium", "mixed", fighter(410), fighter(570, hp=62, face=-1), "Mixed with advantage."),
    scenario("scenario_train_0016", "train", "health_disadvantage", 610016, "medium", "mixed", fighter(410, hp=52), fighter(570, face=-1), "Mixed with disadvantage."),
    scenario("scenario_train_0017", "train", "airborne", 610017, "easy", "mobile", fighter(470, y=80, vy=0), fighter(545, face=-1), "Player starts airborne."),
    scenario("scenario_train_0018", "train", "right_corner", 610018, "medium", "aggressive", fighter(938, face=-1), fighter(850, face=1), "Back near right wall."),

    scenario("scenario_val_0001", "validation", "very_close", 620001, "easy", "aggressive", fighter(462), fighter(535, face=-1), "Validation close rush."),
    scenario("scenario_val_0002", "validation", "medium_distance", 620002, "medium", "standard", fighter(335), fighter(655, face=-1), "Validation medium standard."),
    scenario("scenario_val_0003", "validation", "far_distance", 620003, "medium", "mobile", fighter(190), fighter(845, face=-1), "Validation far mobile."),
    scenario("scenario_val_0004", "validation", "corner_pressure", 620004, "hard", "defensive", fighter(66), fighter(155, face=-1), "Validation corner hard."),
    scenario("scenario_val_0005", "validation", "health_advantage", 620005, "hard", "counter-focused", fighter(430), fighter(560, hp=58, face=-1), "Validation advantage counter."),
    scenario("scenario_val_0006", "validation", "health_disadvantage", 620006, "medium", "aggressive", fighter(430, hp=45), fighter(560, face=-1), "Validation low health."),
    scenario("scenario_val_0007", "validation", "early_attack", 620007, "hard", "aggressive", fighter(468), fighter(542, face=-1, attack=10), "Validation advancing punch already starting."),
    scenario("scenario_val_0008", "validation", "passive_probe", 620008, "easy", "defensive", fighter(360), fighter(565, face=-1, block=True), "Validation passive guard."),
    scenario("scenario_val_0009", "validation", "mixed_profile", 620009, "hard", "mixed", fighter(410), fighter(590, face=-1), "Validation mixed hard."),

    scenario("scenario_test_0001", "test", "very_close", 630001, "easy", "counter-focused", fighter(452), fighter(520, face=-1), "Held-out close counter."),
    scenario("scenario_test_0002", "test", "very_close", 630002, "hard", "aggressive", fighter(460), fighter(532, face=-1), "Held-out hard close rush."),
    scenario("scenario_test_0003", "test", "medium_distance", 630003, "easy", "standard", fighter(345), fighter(635, face=-1), "Held-out easy mid."),
    scenario("scenario_test_0004", "test", "medium_distance", 630004, "hard", "counter-focused", fighter(340), fighter(650, face=-1), "Held-out hard mid counter."),
    scenario("scenario_test_0005", "test", "far_distance", 630005, "medium", "mobile", fighter(205), fighter(840, face=-1), "Held-out medium far mobile."),
    scenario("scenario_test_0006", "test", "far_distance", 630006, "hard", "mixed", fighter(180), fighter(860, face=-1), "Held-out hard far mixed."),
    scenario("scenario_test_0007", "test", "corner_pressure", 630007, "medium", "aggressive", fighter(58), fighter(145, face=-1), "Held-out left corner."),
    scenario("scenario_test_0008", "test", "right_corner", 630008, "hard", "mobile", fighter(940, face=-1), fighter(845, face=1), "Held-out right corner."),
    scenario("scenario_test_0009", "test", "health_advantage", 630009, "easy", "defensive", fighter(425), fighter(565, hp=50, face=-1), "Held-out finish hurt defender."),
    scenario("scenario_test_0010", "test", "health_advantage", 630010, "hard", "mixed", fighter(425), fighter(565, hp=60, face=-1), "Held-out advantage mixed."),
    scenario("scenario_test_0011", "test", "health_disadvantage", 630011, "medium", "counter-focused", fighter(425, hp=42), fighter(565, face=-1), "Held-out low health counter."),
    scenario("scenario_test_0012", "test", "health_disadvantage", 630012, "hard", "aggressive", fighter(425, hp=46), fighter(565, face=-1), "Held-out low health rush."),
    scenario("scenario_test_0013", "test", "early_attack", 630013, "medium", "aggressive", fighter(468), fighter(540, face=-1, attack=5), "Held-out light already active."),
    scenario("scenario_test_0014", "test", "early_attack", 630014, "hard", "counter-focused", fighter(468), fighter(540, face=-1, attack=6), "Held-out heavy already active."),
    scenario("scenario_test_0015", "test", "passive_probe", 630015, "medium", "defensive", fighter(385), fighter(555, face=-1, block=True), "Held-out guard probe."),
    scenario("scenario_test_0016", "test", "counter_window", 630016, "hard", "counter-focused", fighter(440), fighter(550, face=-1, cooldown=22), "Held-out punish recovery."),
    scenario("scenario_test_0017", "test", "airborne", 630017, "medium", "mobile", fighter(470, y=85), fighter(545, face=-1), "Held-out airborne start."),
    scenario("scenario_test_0018", "test", "mixed_profile", 630018, "hard", "mixed", fighter(408), fighter(590, face=-1), "Held-out mixed hard."),
]


def scenarios(split=None):
    values = list(SCENARIOS)
    if split is not None:
        values = [scenario for scenario in values if scenario["split"] == split]
    ids = [scenario["id"] for scenario in values]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate scenario id")
    return values

