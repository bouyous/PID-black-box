"""
Conversion des recommandations PID brutes en ajustements sliders Betaflight 4.5.

Les sliders du Simplified Tune manipulent P/I/D/FF de façon cohérente via des
ratios prédéfinis par le firmware. Les utiliser a plusieurs avantages :
  - Les ratios internes BF restent cohérents (moins de risque de "PID désaccordé")
  - Le réglage suit les évolutions du firmware
  - C'est ce que font les tuners expérimentés dans Configurator

Approche : on agrège les delta_pct des recos roll+pitch par type de paramètre,
puis on applique ces deltas aux sliders (base = valeur actuelle, défaut 100).
Les sliders sont bornés 20-200 (0-200 pour dmax/FF).
"""
from __future__ import annotations

from dataclasses import dataclass

from analysis.header_parser import FlightConfig


SLIDER_MIN = 20
SLIDER_MAX = 200
SLIDER_DMAX_MIN = 0
SLIDER_FF_MIN = 0


@dataclass
class SliderAdjustments:
    master_multiplier: int = 100
    pi_gain: int = 100
    i_gain: int = 100
    d_gain: int = 100
    dmax_gain: int = 100
    feedforward_gain: int = 100
    pitch_pi_gain: int = 100
    dterm_filter_mult: int = 100
    gyro_filter_mult: int = 100
    # Deltas bruts pour diagnostic
    notes: list[str] = None
    # Sliders qui ont été clampés à leur min/max (= reco non appliquée
    # complètement par le slider — il faut un fallback en PID brut).
    saturated: set[str] = None

    def __post_init__(self):
        if self.notes is None:
            self.notes = []
        if self.saturated is None:
            self.saturated = set()


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(round(v))))


def _avg(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def compute_sliders(recommendations: list, cfg: FlightConfig,
                    filter_reco_lines: list[str]) -> SliderAdjustments:
    """Agrège les recos PID en ajustements sliders BF 4.5.

    v1.9.6 : DÉDUPLIQUE par paramètre exact avant d'agréger. Auparavant,
    deux recos sur le même `d_pitch` (oscillation + propwash) faisaient
    grimper le slider de la somme des deltas → saturation à 200.
    Maintenant on prend le MAX absolu par paramètre distinct.
    """
    # Étape 1 : dédupliquer par nom exact (un seul delta par param)
    by_param: dict[str, float] = {}
    for r in recommendations:
        if r.current == 0 or r.suggested == r.current:
            continue
        d = (r.suggested - r.current) / r.current
        # Si plusieurs recos sur le même param : on garde celle de plus
        # grande amplitude (en valeur absolue) — c'est la plus représentative.
        if r.param in by_param:
            if abs(d) > abs(by_param[r.param]):
                by_param[r.param] = d
        else:
            by_param[r.param] = d

    # Étape 2 : agrégation par catégorie
    deltas: dict[str, list[float]] = {'p': [], 'i': [], 'd': [], 'd_min': [], 'f': []}
    pitch_specific: dict[str, list[float]] = {'p': [], 'i': []}
    for param, d in by_param.items():
        if param.startswith('p_roll') or param.startswith('p_pitch'):
            deltas['p'].append(d)
            if param.startswith('p_pitch'):
                pitch_specific['p'].append(d)
        elif param.startswith('i_roll') or param.startswith('i_pitch'):
            deltas['i'].append(d)
            if param.startswith('i_pitch'):
                pitch_specific['i'].append(d)
        elif param.startswith('d_min'):
            deltas['d_min'].append(d)
        elif param.startswith('d_roll') or param.startswith('d_pitch'):
            deltas['d'].append(d)
        elif param.startswith('f_roll') or param.startswith('f_pitch'):
            deltas['f'].append(d)

    adj = SliderAdjustments(
        master_multiplier=cfg.simplified_master or 100,
        pi_gain=cfg.simplified_pi_gain,
        i_gain=cfg.simplified_i_gain,
        d_gain=cfg.simplified_d_gain,
        dmax_gain=cfg.simplified_dmax_gain,
        feedforward_gain=cfg.simplified_feedforward,
        pitch_pi_gain=cfg.simplified_pitch_pi_gain,
        dterm_filter_mult=cfg.simplified_dterm_filter_mult,
        gyro_filter_mult=cfg.simplified_gyro_filter_mult,
    )

    p_delta = _avg(deltas['p'])
    i_delta = _avg(deltas['i'])
    d_delta = _avg(deltas['d'])
    f_delta = _avg(deltas['f'])
    dmin_delta = _avg(deltas['d_min'])

    # Stratégie PI :
    #   - Si P et I bougent dans le même sens et magnitude proche → pi_gain
    #   - Sinon : pi_gain suit P, i_gain compense l'écart
    if p_delta != 0 or i_delta != 0:
        both_same_direction = (p_delta * i_delta) >= 0
        similar_magnitude = abs(p_delta - i_delta) < 0.04
        if both_same_direction and similar_magnitude:
            combo = (p_delta + i_delta) / 2
            adj.pi_gain = _clamp(adj.pi_gain * (1 + combo), SLIDER_MIN, SLIDER_MAX)
            adj.notes.append(f"pi_gain : P et I bougent ensemble ({combo*100:+.0f}%)")
        else:
            if p_delta != 0:
                adj.pi_gain = _clamp(adj.pi_gain * (1 + p_delta), SLIDER_MIN, SLIDER_MAX)
            if i_delta != 0:
                # i_gain est un multiplicateur de I au-dessus de pi_gain
                # Ratio cible = (1+i_delta) / (1+p_delta)
                ratio = (1 + i_delta) / (1 + p_delta) if (1 + p_delta) != 0 else 1
                adj.i_gain = _clamp(adj.i_gain * ratio, SLIDER_MIN, SLIDER_MAX)
                adj.notes.append(f"i_gain ajusté séparément ({i_delta*100:+.0f}% vs P {p_delta*100:+.0f}%)")

    # D
    if d_delta != 0:
        target = adj.d_gain * (1 + d_delta)
        clamped = _clamp(target, SLIDER_MIN, SLIDER_MAX)
        if abs(target - clamped) >= 1.0:
            adj.saturated.add('simplified_d_gain')
        adj.d_gain = clamped

    # D_min / D_max : augmenter D_min = réduire l'écart D_max - D_min
    # dmax_gain élevé = beaucoup de D dynamique (D_max >> D_min)
    # Si on veut remonter D_min (plus de D permanent en virage), on baisse dmax_gain
    if dmin_delta > 0:
        adj.dmax_gain = _clamp(adj.dmax_gain * (1 - dmin_delta * 0.7), SLIDER_DMAX_MIN, SLIDER_MAX)
        adj.notes.append(f"dmax_gain réduit pour remonter D_min (prop wash)")
    elif dmin_delta < 0:
        adj.dmax_gain = _clamp(adj.dmax_gain * (1 + abs(dmin_delta) * 0.7), SLIDER_DMAX_MIN, SLIDER_MAX)

    # FF
    if f_delta != 0:
        target = adj.feedforward_gain * (1 + f_delta)
        clamped = _clamp(target, SLIDER_FF_MIN, SLIDER_MAX)
        if abs(target - clamped) >= 1.0:
            adj.saturated.add('simplified_feedforward_gain')
        adj.feedforward_gain = clamped

    # Pitch vs roll : si les recos pitch ne vont pas dans le même sens que roll global,
    # on tire pitch_pi_gain dans la direction du pitch spécifique
    pitch_p = _avg(pitch_specific['p'])
    roll_only_p = [x for x in deltas['p'] if x not in pitch_specific['p']]
    roll_p_avg = _avg(roll_only_p) if roll_only_p else p_delta
    if pitch_specific['p'] and roll_only_p and abs(pitch_p - roll_p_avg) > 0.06:
        # pitch bouge différemment de roll → ajuster pitch_pi_gain
        ratio = (1 + pitch_p) / (1 + roll_p_avg) if (1 + roll_p_avg) != 0 else 1
        adj.pitch_pi_gain = _clamp(adj.pitch_pi_gain * ratio, SLIDER_MIN, SLIDER_MAX)
        adj.notes.append(f"pitch_pi_gain : pitch {pitch_p*100:+.0f}% vs roll {roll_p_avg*100:+.0f}%")

    # Filtres : on regarde les recos de filtres globaux
    dterm_factor = _extract_filter_factor(filter_reco_lines, 'dterm_lpf1', cfg.dterm_lpf1_dyn_max_hz or cfg.dterm_lpf1_hz)
    if dterm_factor != 1.0:
        adj.dterm_filter_mult = _clamp(adj.dterm_filter_mult * dterm_factor, SLIDER_MIN, SLIDER_MAX)

    gyro_factor = _extract_filter_factor(filter_reco_lines, 'gyro_lpf1', cfg.gyro_lpf1_hz)
    if gyro_factor != 1.0:
        adj.gyro_filter_mult = _clamp(adj.gyro_filter_mult * gyro_factor, SLIDER_MIN, SLIDER_MAX)

    return adj


def _extract_filter_factor(lines: list[str], keyword: str, current_hz: int) -> float:
    """Trouve la première reco filtre contenant keyword et retourne le ratio new/current."""
    if current_hz <= 0:
        return 1.0
    for line in lines:
        if keyword in line and 'set ' in line and '=' in line:
            try:
                rhs = line.split('=', 1)[1].strip().split()[0]
                new_hz = int(rhs)
                return new_hz / current_hz
            except (ValueError, IndexError):
                continue
    return 1.0


def dump_sliders_cli(adj: SliderAdjustments, cfg: FlightConfig,
                     health_score: int, drone_size: str, flying_style: str,
                     filter_reco_lines: list[str] = None,
                     recommendations: list = None) -> str:
    """Génère le dump CLI en mode sliders PID (filtres gardés en raw).

    v1.9.6 : si un slider sature (= 20 ou = 200), on bascule sur le PID
    BRUT pour ce paramètre — le slider ne pourrait pas appliquer la
    recommandation jusqu'au bout. Évite la confusion 'simplified_d_gain=200'
    qui semble énorme alors que ça reflète juste la saturation.
    """
    filter_reco_lines = filter_reco_lines or []
    recommendations = recommendations or []

    lines = [
        "# ============================================================",
        "# BlackBox Analyzer — mode SLIDERS PID (filtres en raw)",
        f"# Profil : {drone_size}  |  Style : {flying_style}",
        f"# Score santé : {health_score}/100",
        "# Les sliders écrasent les PIDs bruts — c'est le comportement BF.",
        "# Les filtres restent pilotés manuellement (plus précis).",
        "# ============================================================",
        "",
        "# Activer les sliders PID (roll + pitch + yaw)",
        "set simplified_pids_mode = RPY",
        "",
        "# Désactiver les sliders filtres (on gère les filtres à la main)",
        "set simplified_dterm_filter = OFF",
        "set simplified_gyro_filter = OFF",
        "",
        "# --- Sliders PID (valeur CLI = 100 × position du curseur) ---",
    ]

    def _fmt(v: int) -> str:
        return f"{v/100:.2f}"

    # Map slider → familles de recos qu'il pilote (pour le fallback brut)
    SATURATED_FALLBACK = {
        'simplified_d_gain':           ('d_roll', 'd_pitch'),
        'simplified_dmax_gain':        ('d_min_roll', 'd_min_pitch'),
        'simplified_feedforward_gain': ('f_roll', 'f_pitch', 'f_yaw'),
        'simplified_pi_gain':          ('p_roll', 'p_pitch'),
        'simplified_i_gain':           ('i_roll', 'i_pitch'),
    }

    changes: list[tuple[str, int, int, str]] = []
    saturated: set[str] = set(adj.saturated)

    def _emit(name: str, cur: int, new: int, why: str = ""):
        if new == cur:
            return
        if name in saturated:
            # Slider clampé : on n'émet PAS la ligne slider — le fallback
            # PID brut sera émis plus bas pour traduire la reco.
            return
        changes.append((name, cur, new, why))

    _emit('simplified_master_multiplier', cfg.simplified_master or 100,
          adj.master_multiplier, "Multiplicateur Maître")
    _emit('simplified_pi_gain', cfg.simplified_pi_gain, adj.pi_gain,
          "Suivi (Gains P & I)")
    _emit('simplified_i_gain', cfg.simplified_i_gain, adj.i_gain,
          "Dérive - Oscillations (Gains I)")
    _emit('simplified_d_gain', cfg.simplified_d_gain, adj.d_gain,
          "Atténuation (D Gains)")
    _emit('simplified_dmax_gain', cfg.simplified_dmax_gain, adj.dmax_gain,
          "Atténuation dynamique (D Max)")
    _emit('simplified_feedforward_gain', cfg.simplified_feedforward,
          adj.feedforward_gain, "Réponse des sticks (Gains FF)")
    _emit('simplified_pitch_pi_gain', cfg.simplified_pitch_pi_gain,
          adj.pitch_pi_gain, "Suivi du Pitch (Pitch:Roll P,I,FF)")

    # Helper : déduplique recos par param (garde la plus grande amplitude).
    def _dedup_recos(recos: list) -> list:
        by_param: dict[str, object] = {}
        for r in recos:
            cur = by_param.get(r.param)
            if cur is None or abs(r.suggested - r.current) > abs(cur.suggested - cur.current):
                by_param[r.param] = r
        return list(by_param.values())

    # Pour chaque slider saturé, on ajoute les recos PID brutes pour les
    # paramètres qu'il était censé piloter (dédupliquées).
    raw_fallback_lines: list[str] = []
    emitted_params: set[str] = set()
    for slider_name in saturated:
        prefixes = SATURATED_FALLBACK.get(slider_name, ())
        matched = [r for r in recommendations
                   if any(r.param == pre or r.param.startswith(pre + '_')
                          for pre in prefixes)
                   and r.suggested != r.current]
        matched = _dedup_recos(matched)
        if not matched:
            continue
        raw_fallback_lines.append(
            f"# Slider {slider_name} sature — bascule en PID brut :"
        )
        for r in matched:
            raw_fallback_lines.append(r.to_cli_line())
            emitted_params.add(r.param)

    # Recos sur YAW (d_yaw, f_yaw) : non couvertes par les sliders P&I/D
    # qui ne s'appliquent qu'à roll+pitch. À émettre toujours en brut.
    yaw_recos = [r for r in recommendations
                 if r.param.endswith('_yaw') and r.suggested != r.current
                 and r.param not in emitted_params]
    yaw_recos = _dedup_recos(yaw_recos)
    if yaw_recos:
        raw_fallback_lines.append("# YAW (non couvert par les sliders) :")
        for r in yaw_recos:
            raw_fallback_lines.append(r.to_cli_line())
            emitted_params.add(r.param)

    if not changes and not raw_fallback_lines:
        lines.append("# Aucun ajustement slider nécessaire.")
    else:
        for name, cur, new, why in changes:
            # Indication du saut effectif sur l'effective PID (estimation)
            jump_pct = (new - cur) / max(cur, 1) * 100
            lines.append(
                f"set {name} = {new}    # slider {_fmt(cur)} → {_fmt(new)} "
                f"({jump_pct:+.0f}% effectif sur le PID) — {why}"
            )

    if raw_fallback_lines:
        lines += ["", "# --- PID brut (sliders saturés) ---"]
        lines += raw_fallback_lines

    if filter_reco_lines:
        lines += ["", "# --- Filtres (valeurs brutes) ---"]
        for line in filter_reco_lines:
            lines.append(line)

    if adj.notes:
        lines += ["", "# --- Notes ---"]
        for n in adj.notes:
            lines.append(f"# {n}")

    lines += ["", "save"]
    return "\n".join(lines)
