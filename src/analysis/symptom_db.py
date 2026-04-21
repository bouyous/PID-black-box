"""
Base de connaissances symptomatique pour le diagnostic Betaflight.
Intègre les matrices de diagnostic des fichiers de référence :
  - Gelo  : oscillations nez à basse altitude / flutter
  - Geno  : mouvements erratiques / jitter toutes directions
  - Slug  : drone mou, réponse lente
  - Over  : overshoot / dépassement excessif
  - Vib   : vibrations mécaniques non filtrées
  - Elec  : problèmes électriques (tension, ESC, MOSFET)

Structure : chaque SymptomRule décode un symptôme en causes potentielles,
tests quantifiables et actions correctives.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CauseVector(str, Enum):
    SOFTWARE  = "Software / Filtres"
    PID       = "PID Theory"
    ELECTRICAL= "Électrique / Moteur"
    MECHANICAL= "Mécanique"
    GYRO      = "Capteur Gyroscopique"


class RiskLevel(str, Enum):
    LOW    = "Faible"
    MEDIUM = "Moyen"
    HIGH   = "Élevé"
    NA     = "N/A (matériel)"


@dataclass
class CauseDiagnosis:
    vector:          CauseVector
    details:         str
    params_to_adjust: list[str]
    risk:            RiskLevel
    risk_reason:     str
    test_quantifiable: str = ""
    action:          str = ""


@dataclass
class DiagnosticFlow:
    step:       int
    condition:  str
    action:     str
    result:     str = ""


@dataclass
class SymptomRule:
    symptom_id:   str
    label_fr:     str
    label_en:     str
    description:  str
    severity:     str          # "Haute", "Moyenne", etc.
    causes:       list[CauseDiagnosis] = field(default_factory=list)
    flow:         list[DiagnosticFlow] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Base de connaissances
# ---------------------------------------------------------------------------

SYMPTOM_DB: dict[str, SymptomRule] = {}


def _add(rule: SymptomRule) -> None:
    SYMPTOM_DB[rule.symptom_id] = rule


_add(SymptomRule(
    symptom_id  = "gelo",
    label_fr    = "Oscillations nez à basse altitude (Gelo / Flutter)",
    label_en    = "Low-altitude nose oscillations / Flutter",
    description = (
        "Mouvement de va-et-vient horizontal (pitch/roll) excessif et rapide, "
        "typiquement observé près du sol ou en vol stationnaire lent. "
        "Le drone ne maintient pas un angle stable malgré des commandes nulles."
    ),
    severity = "Haute",
    causes = [
        CauseDiagnosis(
            vector    = CauseVector.SOFTWARE,
            details   = (
                "Réaction PID excessive ou mal amortie : terme D qui réagit trop "
                "fortement aux micro-vibrations, ou filtre non adapté à la fréquence de vol."
            ),
            params_to_adjust = ["P_Gain (Roll/Pitch)", "Dterm (Rate Filter)", "Gyro DLPF"],
            risk        = RiskLevel.MEDIUM,
            risk_reason = "Réduire trop D ou les filtres peut rendre le drone mou.",
            test_quantifiable = "Settling time doit être < 0.3 s sur un échelon de setpoint.",
            action      = "Réduire D progressivement (-5%). Tester filtres passe-bas plus agressifs.",
        ),
        CauseDiagnosis(
            vector    = CauseVector.ELECTRICAL,
            details   = (
                "Ripple Voltage élevé sur le bus principal (condensateurs défaillants) "
                "ou EMI de commutation des ESC."
            ),
            params_to_adjust = ["Remplacement condensateurs"],
            risk        = RiskLevel.NA,
            risk_reason = "Problème matériel — régler les PID ne corrigera pas ceci.",
            test_quantifiable = "Vripple > 1.2 × V_nominal lors d'un cycle de commutation rapide.",
            action      = "Remplacer les condensateurs principaux. Vérifier blindage câbles signal.",
        ),
        CauseDiagnosis(
            vector    = CauseVector.MECHANICAL,
            details   = "Jeu excessif dans les roulements ou désalignement moteur/ESC.",
            params_to_adjust = ["Ajustement physique"],
            risk        = RiskLevel.NA,
            risk_reason = "Problème mécanique. Le réglage PID ne peut pas compenser.",
            test_quantifiable = "Déplacement angulaire en régime nul doit être < 0.5° sur 1m.",
            action      = "Serrer les vis, vérifier les roulements, contrôler l'équilibre des hélices.",
        ),
        CauseDiagnosis(
            vector    = CauseVector.ELECTRICAL,
            details   = (
                "Le moteur manque de couple à basse vitesse ou l'ESC introduit "
                "une latence spécifique en bas régime."
            ),
            params_to_adjust = ["ESC Timing", "Current Limit"],
            risk        = RiskLevel.LOW,
            risk_reason = "Régler l'ESC timing plutôt que les PIDs.",
            action      = "Vérifier la capacité des ESC à bas RPM. Tester un timing plus agressif.",
        ),
    ],
    flow = [
        DiagnosticFlow(1, "Si Vripple > seuil critique",
                       "Diagnostiquer PANNE ÉLECTRIQUE (priorité 1). Ajuster PID est inutile.",
                       "Panne condensateur / EMI."),
        DiagnosticFlow(2, "Si Vripple OK ET signal EMI fort",
                       "Diagnostiquer INTERFÉRENCE (priorité 2). Augmenter filtrage ou améliorer blindage.",
                       "Panne système / câblage."),
        DiagnosticFlow(3, "Si Vripple OK ET EMI faible",
                       "Diagnostiquer PROBLÈME LOGICIEL/MÉCANIQUE. Tester impact gain P pour isoler la source.",
                       "P trop élevé, D inadapté, ou vibration mécanique."),
    ],
))

_add(SymptomRule(
    symptom_id  = "geno",
    label_fr    = "Mouvements erratiques / Jitter (Geno)",
    label_en    = "Erratic movement / Jittering in all directions",
    description = (
        "Le drone vibre ou bouge de manière imprévisible et désordonnée dans "
        "toutes les directions, souvent sans cause externe apparente. "
        "Le système oscille en boucle et ne peut pas atteindre d'état stable."
    ),
    severity = "Haute",
    causes = [
        CauseDiagnosis(
            vector    = CauseVector.SOFTWARE,
            details   = (
                "PID trop agressif (P, I ou D trop élevés) entraînant un "
                "dépassement de consigne constant."
            ),
            params_to_adjust = ["P_Gain", "I_Gain", "Dterm"],
            risk        = RiskLevel.HIGH,
            risk_reason = "Instabilité totale. Réduction progressive des gains obligatoire.",
            test_quantifiable = "Mesure de la bande passante BW — doit correspondre à la fréquence de réponse souhaitée.",
            action      = "Réduire P de 10–15% en premier. Si jitter haute fréquence : réduire D.",
        ),
        CauseDiagnosis(
            vector    = CauseVector.GYRO,
            details   = (
                "Bruit de fond trop élevé du capteur gyroscopique ou dérive "
                "de biais thermique — le système réagit au bruit comme à un vrai mouvement."
            ),
            params_to_adjust = ["Remplacement capteur gyro", "Calibration statique"],
            risk        = RiskLevel.NA,
            risk_reason = "Réglage ne peut pas compenser un bruit physique trop élevé.",
            test_quantifiable = "Densité de bruit doit être < 10 deg/s/√Hz en statique.",
            action      = "Remplacer le gyroscope. Effectuer des vols stationnaires pour mesurer la dérive.",
        ),
        CauseDiagnosis(
            vector    = CauseVector.ELECTRICAL,
            details   = (
                "Défaillance partielle d'un ESC (MOSFET qui s'éteint/rallume) "
                "créant des pics de courant irréguliers."
            ),
            params_to_adjust = ["Inspection pistes cuivre et soudures"],
            risk        = RiskLevel.NA,
            risk_reason = "Panne matérielle. L'ajustement PID ne corrigera pas une défaillance ESC.",
            test_quantifiable = "Pics d'énergie non linéaires dans la forme d'onde du courant moteur.",
            action      = "Tester les ESC individuellement. Vérifier les soudures à la loupe.",
        ),
        CauseDiagnosis(
            vector    = CauseVector.SOFTWARE,
            details   = "Filtrage insuffisant des vibrations haute fréquence (moteur ou cadre).",
            params_to_adjust = ["DLPF / Notch Filter", "Gyro/Accel Fusion"],
            risk        = RiskLevel.MEDIUM,
            risk_reason = "Un filtre trop agressif peut masquer une défaillance réelle.",
            action      = "Ajuster fréquences de coupure pour filtrer la source vibratoire identifiée par FFT.",
        ),
    ],
    flow = [
        DiagnosticFlow(1, "Si jitter haute fréquence très rapide (>150Hz visible FFT)",
                       "Suspicion EMI ou défaut MOSFET/ESC. Priorité : vérification électrique.",
                       "Défaillance du commutateur ou EMI."),
        DiagnosticFlow(2, "Si jitter lente (<80Hz) et oscille en boucle",
                       "PID trop agressif. Réduire P de 10% et observer. Répéter jusqu'à stabilité.",
                       "Gains PID excessifs."),
        DiagnosticFlow(3, "Si jitter en statique (drone posé)",
                       "Bruit gyro ou DLPF trop ouvert. Vérifier le capteur et les filtres gyro.",
                       "Capteur ou filtre gyro."),
    ],
))

_add(SymptomRule(
    symptom_id  = "slug",
    label_fr    = "Drone mou / Réponse lente",
    label_en    = "Sluggishness / Lack of responsiveness",
    description = (
        "Le drone met trop de temps à changer d'angle ou la réponse est faible "
        "par rapport aux commandes du pilote. Rise time trop élevé."
    ),
    severity = "Moyenne",
    causes = [
        CauseDiagnosis(
            vector    = CauseVector.PID,
            details   = (
                "Terme Proportionnel P insuffisant pour générer assez de couple "
                "au démarrage, surtout sur les grands formats (10\")."
            ),
            params_to_adjust = ["PID P Gain"],
            risk        = RiskLevel.HIGH,
            risk_reason = "Un P trop élevé rend le drone hyper-réactif et provoque des oscillations.",
            test_quantifiable = "Rise time moyen > 80ms (freestyle) ou > 55ms (racing).",
            action      = "Augmenter P progressivement (+5%). Vérifier rise time après chaque ajustement.",
        ),
        CauseDiagnosis(
            vector    = CauseVector.ELECTRICAL,
            details   = "Perte de puissance globale ou faible autorité moteur (KV inadapté).",
            params_to_adjust = ["Vérification propulsion"],
            risk        = RiskLevel.NA,
            risk_reason = "Problème matériel — les PIDs ne peuvent pas compenser un manque de puissance.",
            action      = "Vérifier l'état des moteurs, des hélices et la tension de la batterie.",
        ),
        CauseDiagnosis(
            vector    = CauseVector.SOFTWARE,
            details   = "Filtres trop agressifs qui lissent trop les corrections.",
            params_to_adjust = ["Gyro LPF", "Dterm LPF"],
            risk        = RiskLevel.MEDIUM,
            risk_reason = "Relâcher trop les filtres peut réintroduire du bruit.",
            action      = "Vérifier que les fréquences de coupure LPF ne sont pas trop basses.",
        ),
    ],
    flow = [
        DiagnosticFlow(1, "Rise time > seuil ET pas d'oscillation",
                       "Augmenter P de 5–10% progressivement.",
                       "P trop faible."),
        DiagnosticFlow(2, "Rise time > seuil ET moteurs saturés (max output)",
                       "Problème de propulsion. Vérifier moteurs et batterie.",
                       "Puissance insuffisante."),
    ],
))

_add(SymptomRule(
    symptom_id  = "over",
    label_fr    = "Overshoot / Dépassement excessif",
    label_en    = "Excessive overshoot",
    description = (
        "Le drone dépasse la valeur de consigne avant de se stabiliser. "
        "Overshoot moyen > 25% (freestyle) ou > 18% (racing)."
    ),
    severity = "Moyenne",
    causes = [
        CauseDiagnosis(
            vector    = CauseVector.PID,
            details   = "P trop élevé ou I_relax mal réglé.",
            params_to_adjust = ["P_Gain", "iterm_relax"],
            risk        = RiskLevel.MEDIUM,
            risk_reason = "Réduire trop P peut rendre le drone mou.",
            action      = "Réduire P de 8%. Vérifier la valeur d'iterm_relax.",
        ),
        CauseDiagnosis(
            vector    = CauseVector.PID,
            details   = "Feed-forward trop élevé crée un dépassement sur les inputs rapides.",
            params_to_adjust = ["ff_weight", "feedforward_smooth_factor"],
            risk        = RiskLevel.LOW,
            risk_reason = "Réduire FF réduit la réactivité sur les inputs rapides.",
            action      = "Réduire ff_weight de 10–15%. Augmenter feedforward_smooth_factor.",
        ),
    ],
    flow = [
        DiagnosticFlow(1, "Overshoot > seuil sur inputs rapides uniquement",
                       "Réduire feed-forward (ff_weight).",
                       "FF trop agressif."),
        DiagnosticFlow(2, "Overshoot > seuil sur tous les inputs",
                       "Réduire P de 8% et observer.",
                       "P trop élevé."),
    ],
))

_add(SymptomRule(
    symptom_id  = "vib_mech",
    label_fr    = "Vibrations mécaniques non filtrées",
    label_en    = "Unfiltered mechanical vibrations",
    description = (
        "Pics de résonance détectés dans le gyro brut, non couverts par le filtre RPM. "
        "Peuvent indiquer un cadre fatigué, des vis desserrées ou des hélices déséquilibrées."
    ),
    severity = "Moyenne",
    causes = [
        CauseDiagnosis(
            vector    = CauseVector.MECHANICAL,
            details   = "Résonance cadre, hélices déséquilibrées ou vis desserrées.",
            params_to_adjust = ["Inspection physique"],
            risk        = RiskLevel.NA,
            risk_reason = "Le filtre seul ne règle pas un problème mécanique.",
            action      = "Serrer toutes les vis. Équilibrer/remplacer les hélices. Vérifier anti-vibrations.",
        ),
        CauseDiagnosis(
            vector    = CauseVector.SOFTWARE,
            details   = "Filtre notch dynamique non activé ou mal configuré.",
            params_to_adjust = ["dyn_notch_count", "dyn_notch_min_hz", "dyn_notch_max_hz"],
            risk        = RiskLevel.LOW,
            risk_reason = "Filtres supplémentaires ajoutent de la latence.",
            action      = "Activer dyn_notch ou ajouter un notch statique sur la fréquence détectée.",
        ),
    ],
    flow = [
        DiagnosticFlow(1, "Pics < 100Hz",
                       "Prop wash probable. Augmenter d_min légèrement.",
                       "Prop wash."),
        DiagnosticFlow(2, "Pics 100–300Hz",
                       "Résonance cadre probable. Inspection mécanique + notch statique.",
                       "Résonance cadre."),
        DiagnosticFlow(3, "Pics 300–600Hz",
                       "Résonance hélice probable. Changer/équilibrer les hélices.",
                       "Résonance hélice."),
    ],
))


# ---------------------------------------------------------------------------
# API publique
# ---------------------------------------------------------------------------

def get_symptom(symptom_id: str) -> SymptomRule | None:
    return SYMPTOM_DB.get(symptom_id)


def match_symptoms(
    has_oscillation: bool = False,
    oscillation_freq_hz: float = 0.0,
    high_d_noise: bool = False,
    slow_response: bool = False,
    high_overshoot: bool = False,
    unfiltered_vibrations: bool = False,
    jitter_score: float = 0.0,
) -> list[SymptomRule]:
    """
    Retourne les règles symptomatiques correspondant au profil de vol analysé.
    """
    matched: list[SymptomRule] = []

    # Gelo : oscillations structurées à basse-moyenne fréquence
    if has_oscillation and 40 < oscillation_freq_hz < 200:
        matched.append(SYMPTOM_DB['gelo'])

    # Geno : bruit multi-axe élevé ou D très bruité
    if has_oscillation and (oscillation_freq_hz > 150 or high_d_noise) and jitter_score > 0.4:
        matched.append(SYMPTOM_DB['geno'])

    # Slug : réponse lente
    if slow_response:
        matched.append(SYMPTOM_DB['slug'])

    # Over : overshoot
    if high_overshoot:
        matched.append(SYMPTOM_DB['over'])

    # Vibrations mécaniques
    if unfiltered_vibrations:
        matched.append(SYMPTOM_DB['vib_mech'])

    # Déduplique
    seen: set[str] = set()
    result: list[SymptomRule] = []
    for r in matched:
        if r.symptom_id not in seen:
            seen.add(r.symptom_id)
            result.append(r)
    return result
