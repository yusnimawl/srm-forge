"""ctypes mirrors of the structs in c/sim/srm_sim.h."""

from __future__ import annotations

import ctypes as C

SRM_SIM_ABI = 3
MAX_PHASES = 8

_d, _i32, _u32, _i64 = C.c_double, C.c_int32, C.c_uint32, C.c_int64
_pd, _pf, _pb = C.POINTER(C.c_double), C.POINTER(C.c_float), C.POINTER(C.c_uint8)


class ParamStep(C.Structure):
    _fields_ = [("t", _d), ("value", C.c_float), ("name", C.c_char * 24)]


class Config(C.Structure):
    _fields_ = [(n, _d) for n in (
        "resistance", "bus_voltage", "dt", "speed", "theta0", "inertia", "friction", "load", "load_step",
        "load_step_time", "pwm_hz", "isr_hz", "compute_delay", "command_value", "v_switch", "v_diode", "dead_time",
        "turn_on_delay", "turn_off_delay", "adc_amps_per_count", "encoder_offset", "encoder_ecc_amp",
        "resolver_gain_mismatch", "resolver_phase_error", "adc_offset_error", "adc_gain_error", "adc_noise",
        "adc_rc_tau", "sensor_delay", "volt_full_scale", "volt_rc_tau")] + [
        ("n_steps", _i64), ("trace_stride", _i64), ("param_steps", C.POINTER(ParamStep)),
        ("n_phases", _i32), ("n_rotor_poles", _i32), ("mode", _i32),
        ("command_mode", _i32), ("encoder_cpr", _u32), ("adc_bits", _i32), ("adc_offset_counts", _i32),
        ("seed", _u32), ("encoder_ecc_harmonic", _i32),
        ("resolver", _i32), ("resolver_pole_pairs", _i32), ("resolver_bits", _i32), ("n_param_steps", _i32)]


class Tables(C.Structure):
    _fields_ = [("theta_step", _d), ("psi_step", _d), ("psi_max", _d), ("i_max", _d), ("n_theta", _i64),
                ("n_psi", _i64), ("current", _pd), ("torque", _pd), ("w_field", _pd)]


class Trace(C.Structure):
    _fields_ = [("n_samples", _i64), ("t", _pd), ("theta", _pd), ("omega", _pd), ("torque", _pd), ("encoder", _pd),
                ("resolver_sin", _pd), ("resolver_cos", _pd),
                ("i", _pf), ("psi", _pf), ("v", _pf), ("adc_i", _pf), ("adc_v", _pf), ("gate_u", _pb), ("gate_l", _pb)]


class Summary(C.Structure):
    _fields_ = [("beyond_map_steps", _i64), ("window_steps", _i64)] + [(n, _d) for n in (
        "energy_in", "energy_mech", "energy_copper", "w_field_start", "w_field_end", "torque_sum", "torque_min",
        "torque_max", "copper_sum", "power_in_sum", "power_mech_sum")] + [("i2_sum", _d * MAX_PHASES),
                                                                    ("refused", _i32), ("refused_code", _i32)]


def bind_tables(lib: C.CDLL) -> None:
    """Check the ABI and the Config, Tables and Summary sizes of a library that lacks the controller entry points."""
    lib.srm_sim_abi.restype = C.c_int
    if lib.srm_sim_abi() != SRM_SIM_ABI:
        raise RuntimeError(f"simulator ABI {lib.srm_sim_abi()} does not match {SRM_SIM_ABI}")
    for name, st in (("config", Config), ("tables", Tables), ("summary", Summary)):
        fn = getattr(lib, f"srm_sim_sizeof_{name}")
        fn.restype = C.c_size_t
        if fn() != C.sizeof(st):
            raise RuntimeError(f"simulator {name} struct is {fn()} bytes in C and {C.sizeof(st)} in ctypes")


def bind(lib: C.CDLL) -> None:
    """Declare the library's entry points and check that both sides agree on the ABI and the struct sizes."""
    lib.srm_sim_abi.restype = C.c_int
    lib.srm_sim_param.argtypes = [C.c_char_p, C.c_float]
    lib.srm_sim_param.restype = C.c_int
    lib.srm_sim_run.argtypes = [C.POINTER(Config), C.POINTER(Tables), C.POINTER(Trace), C.POINTER(Summary)]
    lib.srm_sim_run.restype = C.c_int
    if lib.srm_sim_abi() != SRM_SIM_ABI:
        raise RuntimeError(f"simulator ABI {lib.srm_sim_abi()} does not match {SRM_SIM_ABI}")
    for name, st in (("config", Config), ("tables", Tables), ("trace", Trace), ("summary", Summary)):
        fn = getattr(lib, f"srm_sim_sizeof_{name}")
        fn.restype = C.c_size_t
        if fn() != C.sizeof(st):
            raise RuntimeError(f"simulator {name} struct is {fn()} bytes in C and {C.sizeof(st)} in ctypes")
