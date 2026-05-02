"""
Parse l'en-tête d'un fichier BBL Betaflight.
Lit directement les octets du fichier (pas besoin de blackbox_decode).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FlightConfig:
    # Identification
    firmware_version: str = ""
    board: str = ""
    craft_name: str = ""
    log_datetime: str = ""

    # PIDs [roll=0, pitch=1, yaw=2]
    pid_p: list[int] = field(default_factory=lambda: [0, 0, 0])
    pid_i: list[int] = field(default_factory=lambda: [0, 0, 0])
    pid_d: list[int] = field(default_factory=lambda: [0, 0, 0])
    pid_f: list[int] = field(default_factory=lambda: [0, 0, 0])
    d_min: list[int] = field(default_factory=lambda: [0, 0, 0])

    # Filtres D-term
    dterm_lpf1_hz: int = 0
    dterm_lpf2_hz: int = 0
    dterm_lpf1_dyn_min_hz: int = 0
    dterm_lpf1_dyn_max_hz: int = 0

    # Filtres Gyro
    gyro_lpf1_hz: int = 0
    gyro_lpf2_hz: int = 0

    # Notch dynamique
    dyn_notch_count: int = 0
    dyn_notch_min_hz: int = 100
    dyn_notch_max_hz: int = 600
    dyn_notch_q: int = 300

    # Filtre RPM
    rpm_filter_harmonics: int = 0
    rpm_filter_min_hz: int = 150
    rpm_filter_q: int = 500

    # Hardware
    looptime_us: int = 125
    motor_poles: int = 14
    dshot_bidir: bool = False
    gyro_scale_raw: str = ""
    # Détection chip FC + logging BBL (avril 2026)
    fc_target: str = ""
    fc_mcu: str = ""
    fc_chip_family: str = "UNKNOWN"   # F405 / F411 / F722 / F745 / H743 / H750
    pid_process_denom: int = 1
    blackbox_sample_rate_div: int = 1  # 1/(2^N)
    blackbox_mode: str = ""
    blackbox_disable_acc: bool = False
    blackbox_disable_debug: bool = False
    blackbox_disable_motors: bool = False
    blackbox_disable_rc: bool = False
    blackbox_disable_setpoint: bool = False
    blackbox_disable_gyro: bool = False
    blackbox_disable_pids: bool = False
    blackbox_disable_battery: bool = False

    # Feed-forward
    ff_weight: list[int] = field(default_factory=lambda: [0, 0, 0])
    ff_boost: int = 0
    ff_smooth_factor: int = 25
    ff_jitter_factor: int = 7
    ff_spike_limit: int = 55

    # I-term relax + dshot idle (DeerFlow KB v2)
    iterm_relax_type: str = ""
    iterm_relax_cutoff: int = 15
    dshot_idle_value: int = 550   # échelle 0-10000 (0.1 %), défaut BF 5.5 %

    # Divers
    tpa_rate: int = 65
    tpa_breakpoint: int = 1350
    iterm_windup: int = 85
    anti_gravity_gain: int = 80
    simplified_mode: int = 0
    simplified_master: int = 100
    simplified_pi_gain: int = 100
    simplified_i_gain: int = 100
    simplified_d_gain: int = 100
    simplified_dmax_gain: int = 100
    simplified_feedforward: int = 100
    simplified_pitch_pi_gain: int = 100
    simplified_dterm_filter: int = 1
    simplified_dterm_filter_mult: int = 100
    simplified_gyro_filter: int = 1
    simplified_gyro_filter_mult: int = 100
    debug_mode: int = 0

    # Dict brut pour tout le reste
    raw: dict[str, str] = field(default_factory=dict)

    def is_valid(self) -> bool:
        return any(v > 0 for v in self.pid_p)

    def size_hint(self) -> str:
        """Essaie de deviner la taille depuis le nom du craft/board."""
        s = (self.craft_name + self.board).lower()
        for marker, size in [('10"', '10"'), ('10p', '10"'), ('10inch', '10"'),
                              ('10in', '10"'), ('10pouce', '10"'),
                              ('7"', '7"'), ('7p', '7"'), ('7inch', '7"'),
                              ('7in', '7"'), ('7pouce', '7"'),
                              ('6"', '6"'), ('6p', '6"'), ('6inch', '6"'),
                              ('6in', '6"'), ('6pouce', '6"'),
                              ('5"', '5"'), ('5p', '5"'), ('5inch', '5"'),
                              ('5in', '5"'), ('5pouce', '5"'),
                              ('3"', '3"'), ('3p', '3"'), ('3inch', '3"'),
                              ('3in', '3"'), ('3pouce', '3"'),
                              ('2.5"', '2.5"'), ('2p5', '2.5"'),
                              ('2.5inch', '2.5"'), ('25p', '2.5"'),
                              ('cinewhoop', '2.5"'), ('cinewoop', '2.5"')]:
            if marker in s:
                return size
        return ''


def parse_header(bbl_path: str | Path) -> FlightConfig:
    """Lit les lignes H du BBL et construit un FlightConfig."""
    cfg = FlightConfig()
    raw: dict[str, str] = {}

    with open(bbl_path, 'rb') as f:
        # L'en-tête ne dépasse jamais ~32KB
        chunk = f.read(65536)

    text = chunk.decode('latin-1', errors='replace')

    for line in text.splitlines():
        if not line.startswith('H '):
            # L'en-tête se termine quand les frames binaires commencent
            if line and not line.startswith('H') and len(line) > 2:
                break
            continue
        # Format: "H key:value"
        rest = line[2:]
        if ':' not in rest:
            continue
        key, _, value = rest.partition(':')
        key = key.strip()
        value = value.strip()
        raw[key] = value

    cfg.raw = raw

    def get(k: str, default: str = '') -> str:
        return raw.get(k, default)

    def get_int(k: str, default: int = 0) -> int:
        try:
            return int(get(k, str(default)))
        except ValueError:
            return default

    def get_int_list(k: str, n: int = 3) -> list[int]:
        v = get(k, '')
        try:
            parts = [int(x) for x in v.split(',')]
            return (parts + [0] * n)[:n]
        except ValueError:
            return [0] * n

    # Identification
    cfg.firmware_version = get('Firmware revision', get('Firmware version'))
    cfg.board = get('Board information')
    cfg.craft_name = get('Craft name')
    cfg.log_datetime = get('Log start datetime')

    # PIDs
    roll_pid  = get_int_list('rollPID')
    pitch_pid = get_int_list('pitchPID')
    yaw_pid   = get_int_list('yawPID')
    cfg.pid_p = [roll_pid[0],  pitch_pid[0],  yaw_pid[0]]
    cfg.pid_i = [roll_pid[1],  pitch_pid[1],  yaw_pid[1]]
    cfg.pid_d = [roll_pid[2],  pitch_pid[2],  yaw_pid[2]]
    cfg.d_min = get_int_list('d_min')
    cfg.pid_f = get_int_list('ff_weight')

    # Filtres D-term
    cfg.dterm_lpf1_hz     = get_int('dterm_lpf1_static_hz')
    cfg.dterm_lpf2_hz     = get_int('dterm_lpf2_static_hz')
    dterm_dyn = get_int_list('dterm_lpf1_dyn_hz', 2)
    cfg.dterm_lpf1_dyn_min_hz = dterm_dyn[0]
    cfg.dterm_lpf1_dyn_max_hz = dterm_dyn[1]

    # Filtres Gyro
    cfg.gyro_lpf1_hz = get_int('gyro_lpf1_static_hz')
    cfg.gyro_lpf2_hz = get_int('gyro_lpf2_static_hz')

    # Notch dynamique
    cfg.dyn_notch_count   = get_int('dyn_notch_count')
    cfg.dyn_notch_min_hz  = get_int('dyn_notch_min_hz', 100)
    cfg.dyn_notch_max_hz  = get_int('dyn_notch_max_hz', 600)
    cfg.dyn_notch_q       = get_int('dyn_notch_q', 300)

    # RPM filter
    cfg.rpm_filter_harmonics = get_int('rpm_filter_harmonics')
    cfg.rpm_filter_min_hz    = get_int('rpm_filter_min_hz', 150)
    cfg.rpm_filter_q         = get_int('rpm_filter_q', 500)

    # Hardware
    cfg.looptime_us   = get_int('looptime', 125)
    cfg.motor_poles   = get_int('motor_poles', 14)
    cfg.dshot_bidir   = get('dshot_bidir') == '1'
    cfg.gyro_scale_raw = get('gyro_scale')

    # Détection chip FC (STM32F405/F411/F722/F745/H743/H750)
    cfg.fc_target = get('Firmware target')
    cfg.fc_mcu    = get('MCU') or get('mcu')
    _chip_keys = {
        'STM32F40': 'F405', 'STM32F411': 'F411',
        'STM32F7X2': 'F722', 'STM32F722': 'F722',
        'STM32F745': 'F745', 'STM32F7X5': 'F745',
        'STM32H743': 'H743', 'STM32H750': 'H750', 'STM32H7': 'H743',
    }
    _search = (cfg.fc_mcu + ' ' + cfg.fc_target + ' ' + cfg.board).upper()
    cfg.fc_chip_family = 'UNKNOWN'
    for k, fam in _chip_keys.items():
        if k in _search:
            cfg.fc_chip_family = fam
            break

    # BBL logging
    cfg.pid_process_denom       = get_int('pid_process_denom', 1)
    cfg.blackbox_sample_rate_div = get_int('blackbox_sample_rate', 1)
    cfg.blackbox_mode           = get('blackbox_mode')
    cfg.blackbox_disable_acc      = get('blackbox_disable_acc') == '1'
    cfg.blackbox_disable_debug    = get('blackbox_disable_debug') == '1'
    cfg.blackbox_disable_motors   = get('blackbox_disable_motors') == '1'
    cfg.blackbox_disable_rc       = get('blackbox_disable_rc') == '1'
    cfg.blackbox_disable_setpoint = get('blackbox_disable_setpoint') == '1'
    cfg.blackbox_disable_gyro     = get('blackbox_disable_gyro') == '1'
    cfg.blackbox_disable_pids     = get('blackbox_disable_pids') == '1'
    cfg.blackbox_disable_battery  = get('blackbox_disable_battery') == '1'

    # Feed-forward
    cfg.ff_weight       = get_int_list('ff_weight')
    cfg.ff_boost        = get_int('feedforward_boost', 15)
    cfg.ff_smooth_factor = get_int('feedforward_smooth_factor', 25)
    cfg.ff_jitter_factor = get_int('feedforward_jitter_factor', 7)
    cfg.ff_spike_limit   = get_int('feedforward_spike_limit', 55)

    # I-term relax + DShot idle (DeerFlow KB v2)
    cfg.iterm_relax_type   = get('iterm_relax_type')
    cfg.iterm_relax_cutoff = get_int('iterm_relax_cutoff', 15)
    cfg.dshot_idle_value   = get_int('dshot_idle_value', 550)

    # Divers
    cfg.tpa_rate        = get_int('tpa_rate', 65)
    cfg.tpa_breakpoint  = get_int('tpa_breakpoint', 1350)
    cfg.iterm_windup    = get_int('iterm_windup', 85)
    cfg.anti_gravity_gain = get_int('anti_gravity_gain', 80)
    cfg.simplified_mode             = get_int('simplified_pids_mode')
    cfg.simplified_master           = get_int('simplified_master_multiplier', 100)
    cfg.simplified_pi_gain          = get_int('simplified_pi_gain', 100)
    cfg.simplified_i_gain           = get_int('simplified_i_gain', 100)
    cfg.simplified_d_gain           = get_int('simplified_d_gain', 100)
    cfg.simplified_dmax_gain        = get_int('simplified_dmax_gain', 100)
    cfg.simplified_feedforward      = get_int('simplified_feedforward_gain', 100)
    cfg.simplified_pitch_pi_gain    = get_int('simplified_pitch_pi_gain', 100)
    cfg.simplified_dterm_filter     = get_int('simplified_dterm_filter', 1)
    cfg.simplified_dterm_filter_mult = get_int('simplified_dterm_filter_multiplier', 100)
    cfg.simplified_gyro_filter      = get_int('simplified_gyro_filter', 1)
    cfg.simplified_gyro_filter_mult = get_int('simplified_gyro_filter_multiplier', 100)
    cfg.debug_mode        = get_int('debug_mode')

    return cfg
